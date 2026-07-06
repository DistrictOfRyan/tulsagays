"""Instagram-only org event scraper (generalized).

Some Tulsa LGBTQ+ / queer-cultural orgs publish their parties ONLY on Instagram —
no website, no calendar, no Eventbrite. This module reads their public IG profiles
and extracts this-week events, using the exact same robust engine proven on Studio 66
(scraper/studio66.py):

  1. Auth-free public web-profile JSON endpoint (primary, needs no login).
  2. Authenticated instagrapi session shared with @tulsagays (fallback only).
  3. Claude (SITES_ANTHROPIC_KEY) to pull structured dated events from free-text
     captions, with a regex / parse_date_flexible fallback when no key is present.

Each configured org is a trusted LGBTQ source (its key lives in config.LGBTQ_SOURCES),
so no keyword relevance filter is applied — but a parseable in-week date IS required.
Every path degrades to an empty list (never crashes) if Instagram blocks the request.

To add another IG-only org: append a dict to ORGS below and add its `source_name`
to config.LGBTQ_SOURCES (and, optionally, name keywords to COMMUNITY_PARTNER_KEYWORDS
so the org's events also pass when they surface in FB groups / aggregators).

Run standalone:  python scraper/instagram_orgs.py
"""

import os
import sys
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper
import config

logger = logging.getLogger(__name__)

# Same session file the @tulsagays engagement tasks use (off the synced drive).
SETTINGS_FILE = Path.home() / ".credentials" / "ig_settings_tulsagays.json"

# Public web App-ID — lets the logged-out web_profile_info JSON endpoint return posts.
IG_WEB_APP_ID = "936619743392459"
WEB_PROFILE_URL = "https://www.instagram.com/api/v1/users/web_profile_info/?username={user}"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36")
POSTS_TO_SCAN = 12      # most recent posts to read each run

# Emoji / pictographic symbol ranges + ZWJ / variation selectors. Stripped from
# caption-derived event names so the regex fallback path is as clean as the LLM path.
_EMOJI_RX = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF\U0000FE00-\U0000FE0F\U0000200D]",
    flags=re.UNICODE,
)

# A caption must look like an event announcement before we bother date-parsing it.
EVENT_KEYWORDS = [
    "join us", "come out", "tonight", "this week", "this saturday", "this friday",
    "this sunday", "this thursday", "tickets", "doors", "doors open", "rsvp",
    "party", "drag", "watch party", "show", "fashion", "ball", "summit", "festival",
    "fundraiser", "market", "bingo", "happy hour", "dance", "live", "performance",
    "lineup", "line up", "presale", "pre-sale", "celebration", "yoga", "brunch",
    "tour", "bash", "@", "pm", "doors @",
]

# ── Configured IG-only orgs ──────────────────────────────────────────────────
# username      : IG handle without the @
# source_name   : must also be added to config.LGBTQ_SOURCES to be trusted
# default_venue : used when a caption names no explicit location (NEVER fabricate
#                 a street address — these orgs rove)
# priority      : 1 = primary LGBTQ org (fun one-offs, good featured/EOTW)
# blurb         : short event-facing description suffix (no em dashes — preflight bans)
ORGS: List[Dict] = [
    {
        "username": "upflykai",
        "source_name": "klassic",
        "default_venue": "Tulsa (location by DM, see @upflykai)",
        "priority": 1,
        "blurb": "Black queer Tulsa events collective (KLASSIC). "
                 "Details and location on Instagram @upflykai.",
    },
    {
        "username": "goff_fest",
        "source_name": "goff_center",
        "default_venue": "Tulsa (see @goff_fest for venue)",
        "priority": 2,
        "blurb": "Goff Center / Goff Fest. Architecture, art, and Pride programming "
                 "celebrating Tulsa's queer cultural legacy. Details on Instagram @goff_fest.",
    },
    # Gay bars (added 2026-06-12). Their websites are DNS-dead; IG is the only
    # place they announce events. W24 missed every Eagle/Majestic Pride event
    # because nothing scraped them.
    {
        "username": "tulsaeagle",
        # The Eagle's handle has been documented both ways (config comment says
        # @tulsaeagleok). Try both so a rename/typo never silently zeroes the
        # main gay bar — the W24 Pride miss class of failure.
        "alt_usernames": ["tulsaeagleok"],
        "source_name": "tulsa_eagle_ig",
        "default_venue": "Tulsa Eagle, 1338 E 3rd St",
        "priority": 2,
        "blurb": "Tulsa Eagle, Tulsa's levi-leather LGBTQ+ bar. "
                 "Details on Instagram @tulsaeagle.",
    },
    {
        "username": "clubmajestictulsa",
        "alt_usernames": ["majestictulsa", "clubmajestic"],
        "source_name": "club_majestic_ig",
        "default_venue": "Club Majestic, 124 N Boston Ave",
        "priority": 2,
        "blurb": "Club Majestic, Tulsa's flagship LGBTQ+ nightclub downtown. "
                 "Details on Instagram @clubmajestictulsa.",
    },
    {
        "username": "tulsaybr",
        # @imvalpal added 2026-06-24 per William: Val Pal books/promotes YBR's
        # events and posts them on her IG, often before the venue account does, so
        # she's a reliable second feed for YBR nights. Handles are walked in order
        # until one returns posts, so this also covers a venue-account rename.
        "alt_usernames": ["ybrtulsa", "imvalpal"],
        "source_name": "ybr_ig",
        "default_venue": "Yellow Brick Road, 2630 E 15th St",
        # priority 1 (top tier, 2026-06-20 per William): YBR is Tulsa's only lesbian
        # bar and one of the last in the US — under-loved by the gay-guy crowd, so we
        # FEATURE it and frame it as a welcome-all space every chance we get.
        "priority": 1,
        "blurb": "Yellow Brick Road is Tulsa's only lesbian bar and one of the last "
                 "left in the whole country, and here's the thing the boys keep "
                 "missing: everyone is welcome at the cave, not just the girls. Roll "
                 "up, the whole community is invited. Details on Instagram @tulsaybr.",
    },
    {
        # DVL Club & Lounge (added 2026-06-18). Woman-owned LGBTQ+ bar in the
        # Blue Dome District. Its dvltulsa.com calendar is JS-rendered (unreadable
        # by the static scraper); FB events are wired in facebook_events.py, and
        # this IG path adds a second, durable feed for its queer socials/parties.
        "username": "dvltulsa",
        "source_name": "dvl_ig",
        "default_venue": "DVL Club & Lounge, 302 S Frankfort Ave",
        "priority": 1,
        "blurb": "DVL Club & Lounge, the woman-owned LGBTQ+ bar in Tulsa's Blue "
                 "Dome District. Details on Instagram @dvltulsa.",
    },
    {
        # HotMess Sports Tulsa (added 2026-07-01 per William: "these are cool").
        # LGBTQ+ rec sports league (kickball, dodgeball, sand volleyball, cornhole,
        # bowling, tennis, flag football). Their hotmesssports.com/tulsa site is a
        # JS-rendered SportsEngine page that lists league SEASONS, not single dated
        # events, so the static HotMessSportsScraper (specific_orgs.py) returns 0.
        # The Tulsa IG @hotmesssportstulsa is where they post the actual dated game
        # days, socials, tournaments, and registration pushes. IMPORTANT: use the
        # Tulsa handle, NOT the national @hotmesssports (that mixes every city's
        # events and returns nothing Tulsa-dated). source_name already trusted in
        # config.LGBTQ_SOURCES.
        "username": "hotmesssportstulsa",
        "source_name": "hotmess_sports",
        "default_venue": "Various venues, Tulsa (see @hotmesssportstulsa)",
        "priority": 1,
        "blurb": "HotMess Sports Tulsa, the LGBTQ+ rec sports league (kickball, "
                 "dodgeball, sand volleyball, and more). All skill levels welcome, "
                 "the whole point is showing up and having a blast. Details and "
                 "registration on Instagram @hotmesssportstulsa.",
    },
]


class InstagramOrgScraper(BaseScraper):
    """Read one org's public IG posts and extract this-week dated events."""

    def __init__(self, org: Dict):
        super().__init__()
        self.username = org["username"]
        # Primary handle first, then any documented alternates. Every fetch path
        # walks this list until one returns posts, so a renamed/mistyped handle
        # degrades to the alternate instead of a silent 0 events.
        self.usernames = [org["username"]] + [u for u in org.get("alt_usernames", []) if u]
        self.source_name = org["source_name"]
        self.default_venue = org.get("default_venue", f"Tulsa (see @{org['username']})")
        self.priority = int(org.get("priority", 2))
        self.blurb = org.get("blurb", f"Event from @{org['username']}.")
        self.profile_url = f"https://www.instagram.com/{self.username}/"

    # ── week helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _week_range():
        today = datetime.now()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        return (monday.replace(hour=0, minute=0, second=0, microsecond=0),
                sunday.replace(hour=23, minute=59, second=59, microsecond=999999))

    @staticmethod
    def _clean_name(name: str) -> str:
        """Strip em dashes (banned in William's voice / blocked by preflight),
        emoji, and hashtags, and collapse whitespace so caption-derived names are
        safe for slides + website even on the regex fallback path."""
        if not name:
            return ""
        name = name.replace("—", ", ").replace("–", "-")  # em/en dash
        name = name.replace("“", '"').replace("”", '"')   # curly quotes
        name = name.replace("‘", "'").replace("’", "'")
        name = _EMOJI_RX.sub("", name)                    # drop emoji/symbols
        name = re.sub(r"#\w+", "", name)                  # drop trailing hashtags
        return re.sub(r"\s+", " ", name).strip(" ,-")

    # Event-type cues → a clean display label. Ordered: first match wins, so list
    # the more specific phrases before the generic ones. Lets the regex path emit
    # "Dance Party at YBR" instead of the raw hype header "HEADS UP". (2026-06-20)
    _EVENT_TYPE_CUES = [
        ("drag brunch", "Drag Brunch"), ("drag show", "Drag Show"),
        ("drag", "Drag Night"),
        ("b&b", "B&B Dance Party"), ("dance party", "Dance Party"),
        ("dance floor", "Dance Party"), ("dance", "Dance Night"),
        ("talent", "Talent Night"), ("open mic", "Open Mic"),
        ("karaoke", "Karaoke Night"), ("bingo", "Bingo Night"),
        ("trivia", "Trivia Night"), ("watch party", "Watch Party"),
        ("happy hour", "Happy Hour"), ("brunch", "Drag Brunch"),
        ("tea party", "Tea Party"), ("tea time", "Tea Time"),
        ("class", "Craft Class"), ("market", "Market"),
        ("fundraiser", "Fundraiser"), ("pride", "Pride Party"),
        ("party", "Party"), ("show", "Live Show"),
    ]
    # Lines that are pure hype banners, never the real event name.
    _HYPE_RX = re.compile(
        r"^\W*(heads?\s*up|this\s+(mon|tues?|wed|thurs?|fri|sat|sun)\w*|tonight|"
        r"tomorrow|today|come\s+(get|on)|reminder|now\s+open|attention|psa|"
        r"this\s+week(end)?|next\s+(week|sun\w*|sat\w*)|mark\s+your)\W*$", re.I)

    @classmethod
    def _venue_short(cls, venue: str) -> str:
        """First clause of a venue string ('Yellow Brick Road, 2630 ...' -> 'YBR')."""
        head = (venue or "").split(",")[0].strip()
        if "yellow brick" in head.lower():
            return "YBR"
        return head

    @classmethod
    def _derive_event_name(cls, caption: str, venue: str) -> str:
        """Turn a bar caption into a presentable event name.

        Prefers an event-type cue ('Dance Party at YBR') over the raw first line,
        because bar posts open with an emoji hype banner ('HEADS UP', 'THIS
        SATURDAY'), not the event title. Falls back to the first non-hype line.
        """
        low = caption.lower()
        venue_short = cls._venue_short(venue)
        for cue, label in cls._EVENT_TYPE_CUES:
            if cue in low:
                return f"{label} at {venue_short}" if venue_short else label
        # No cue — first substantive (non-hype, non-empty) line.
        for line in caption.split("\n"):
            cleaned = cls._clean_name(line)
            if cleaned and len(cleaned) >= 4 and not cls._HYPE_RX.match(line.strip()):
                return cleaned[:80]
        return f"Event at {venue_short}" if venue_short else "Community Event"

    @classmethod
    def _in_week(cls, date_str: str) -> bool:
        if not date_str:
            return False
        try:
            dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        except ValueError:
            return False
        monday, sunday = cls._week_range()
        return monday <= dt <= sunday

    # ── auth-free public fetch (primary) ────────────────────────────────────────
    def _fetch_public(self) -> List[Dict]:
        """Read recent posts via Instagram's public web-profile JSON.

        Walks every candidate handle (primary + alts) and returns the first that
        yields captioned posts, so a renamed/mistyped handle never silently
        zeroes the venue. No login / session / credentials.
        """
        for user in self.usernames:
            posts = self._fetch_public_one(user)
            if posts:
                if user != self.username:
                    logger.info("[%s] primary @%s returned nothing — used alt handle @%s",
                                self.source_name, self.username, user)
                return posts
        return []

    def _fetch_public_one(self, user: str) -> List[Dict]:
        """Fetch one handle's recent captioned posts, or [] on any failure."""
        import requests
        headers = {
            "User-Agent": _UA,
            "X-IG-App-ID": IG_WEB_APP_ID,
            "Accept": "*/*",
            "Referer": f"https://www.instagram.com/{user}/",
        }
        try:
            r = requests.get(WEB_PROFILE_URL.format(user=user),
                             headers=headers, timeout=20)
        except Exception as e:
            logger.warning("[%s] @%s public profile request failed: %s %s",
                           self.source_name, user, type(e).__name__, str(e)[:120])
            return []
        if r.status_code != 200:
            logger.warning("[%s] @%s public profile HTTP %s (logged-out endpoint may be "
                           "rate-limited) — will try next handle / session fallback",
                           self.source_name, user, r.status_code)
            return []
        try:
            user = (r.json().get("data", {}) or {}).get("user") or {}
            edges = (user.get("edge_owner_to_timeline_media") or {}).get("edges", [])
        except Exception as e:
            logger.warning("[%s] public profile JSON parse failed: %s",
                           self.source_name, type(e).__name__)
            return []

        posts = []
        for e in edges[:POSTS_TO_SCAN]:
            node = e.get("node", {}) or {}
            cap_edges = (node.get("edge_media_to_caption") or {}).get("edges", [])
            caption = cap_edges[0]["node"]["text"].strip() if cap_edges else ""
            if not caption:
                continue
            code = node.get("shortcode") or node.get("code")
            post_url = f"https://www.instagram.com/p/{code}/" if code else self.profile_url
            ts = node.get("taken_at_timestamp")
            posted_on = ""
            if ts:
                try:
                    posted_on = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
                except (ValueError, OverflowError, OSError):
                    posted_on = ""
            posts.append({"caption": caption, "url": post_url, "posted_on": posted_on})

        logger.info("[%s] public endpoint returned %d captioned posts",
                    self.source_name, len(posts))
        return posts

    # ── instagrapi session (read-only fallback, never a fresh login) ────────────
    def _fetch_via_session(self) -> List[Dict]:
        cl = self._client()
        if cl is None:
            return []
        for user in self.usernames:
            try:
                uid = cl.user_id_from_username(user)
                medias = cl.user_medias(uid, amount=POSTS_TO_SCAN)
            except Exception as e:
                logger.warning("[%s] @%s session fetch failed: %s %s",
                               self.source_name, user, type(e).__name__, str(e)[:160])
                continue
            posts = []
            for m in medias:
                caption = (getattr(m, "caption_text", "") or "").strip()
                if not caption:
                    continue
                code = getattr(m, "code", None)
                post_url = f"https://www.instagram.com/p/{code}/" if code else self.profile_url
                taken = getattr(m, "taken_at", None)
                posted_on = taken.strftime("%Y-%m-%d") if isinstance(taken, datetime) else ""
                posts.append({"caption": caption, "url": post_url, "posted_on": posted_on})
            if posts:
                if user != self.username:
                    logger.info("[%s] session: primary @%s empty — used alt @%s",
                                self.source_name, self.username, user)
                logger.info("[%s] session fallback returned %d captioned posts",
                            self.source_name, len(posts))
                return posts
        return []

    def _client(self):
        if not SETTINGS_FILE.exists():
            logger.warning(
                "[%s] No @tulsagays IG session at %s — run scripts/ig_login_api.py "
                "once to enable session fallback.", self.source_name, SETTINGS_FILE,
            )
            return None
        try:
            from instagrapi import Client
        except ImportError:
            logger.warning("[%s] instagrapi not installed — cannot use session fallback.",
                           self.source_name)
            return None
        cl = Client()
        try:
            cl.load_settings(str(SETTINGS_FILE))
            cl.get_timeline_feed()  # cheap authenticated call to validate the session
            return cl
        except Exception as e:
            logger.warning(
                "[%s] @tulsagays IG session expired (%s) — re-auth once with "
                "scripts/ig_login_api.py.", self.source_name, type(e).__name__,
            )
            return None

    def _fetch_via_web(self) -> List[Dict]:
        """Tier 3 (2026-07-06): logged-in WEB session in the automation Chrome
        profile. The only tier that reaches personal accounts (@tulsaybr,
        @imvalpal) now that the public endpoint 429s and the instagrapi login is
        bloks-walled. One-time human setup: tools/ig_profile_login.py."""
        try:
            from scraper import instagram_web
            return instagram_web.posts_for(self.source_name, self.usernames)
        except Exception as e:
            logger.warning("[%s] web-session tier failed: %s %s",
                           self.source_name, type(e).__name__, str(e)[:120])
            return []

    def scrape(self) -> List[Dict]:
        # Auth-free public endpoint first; authenticated session, then the
        # logged-in web-session browser tier as the last resort.
        posts = self._fetch_public()
        if not posts:
            posts = self._fetch_via_session()
        if not posts:
            posts = self._fetch_via_web()
        if not posts:
            logger.info("[%s] No captioned posts from any path — 0 events.",
                        self.source_name)
            return []

        events = self._extract_with_llm(posts)
        if events is None:
            events = self._extract_with_regex(posts)

        # Keep only events with a parseable date inside the current Mon–Sun week.
        in_week = [e for e in events if self._in_week(e.get("date", ""))]
        logger.info("[%s] %d candidate events, %d in current week",
                    self.source_name, len(events), len(in_week))
        return in_week

    # ── LLM extraction (preferred) ──────────────────────────────────────────────
    def _extract_with_llm(self, posts: List[Dict]) -> Optional[List[Dict]]:
        """Return events parsed by Claude, or None if no key / call failed."""
        import os
        if not config.ANTHROPIC_API_KEY and not os.environ.get("WORKER_API_KEY"):
            return None  # no LLM available at all -> regex fallback

        monday, sunday = self._week_range()
        today = datetime.now().strftime("%Y-%m-%d (%A)")
        blob = []
        for i, p in enumerate(posts):
            blob.append(f"POST {i} (posted {p['posted_on']}):\n{p['caption'][:900]}")
        captions_text = "\n\n---\n\n".join(blob)

        system = (
            "You extract concrete, dated events from a Tulsa LGBTQ+ / queer-cultural "
            "org's Instagram captions. The org may rove between venues. Return ONLY "
            "events that have an identifiable calendar date. Resolve relative dates "
            "('this Saturday', 'tonight', '6/14') against the post date and today's "
            "date. Output STRICT JSON only."
        )
        user = (
            f"Today is {today}. The current week runs {monday.strftime('%Y-%m-%d')} "
            f"(Monday) through {sunday.strftime('%Y-%m-%d')} (Sunday).\n\n"
            "From the captions below, extract every distinct event that has a real "
            "date. For each, output an object with keys:\n"
            '  "name"  - short event title (no hashtags/emoji, no em dashes)\n'
            '  "date"  - YYYY-MM-DD (resolve relative dates; year is the current year)\n'
            '  "time"  - like "9:00 PM" or "" if none stated\n'
            '  "venue" - the venue/address ONLY if explicitly named in the caption, '
            'else "" (do NOT invent a location)\n'
            '  "post"  - the POST number it came from\n'
            "Skip generic promo with no date, recaps of past events, and merch/donation "
            "posts. Return a JSON object: {\"events\": [ ... ]}. No prose.\n\n"
            f"CAPTIONS:\n{captions_text}"
        )
        raw = None
        if config.ANTHROPIC_API_KEY:
            try:
                from anthropic import Anthropic
                client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
                msg = client.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=1500,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                raw = msg.content[0].text.strip()
            except Exception as e:
                logger.warning("[%s] Anthropic extraction failed (%s) — trying DeepSeek",
                               self.source_name, type(e).__name__)
        if raw is None:
            # DeepSeek worker fallback (2026-07-06): SITES_ANTHROPIC_KEY was never
            # set, so extraction silently ran regex-only forever. Structured JSON
            # extraction is squarely cheap-worker work; sanity + preflight gates
            # guard quality downstream. (Key dead as of 2026-07-06, gap G35 —
            # kept wired so it self-heals when William renews it.)
            raw = self._deepseek_complete(system, user)
        if raw is None:
            # claude CLI fallback: runs on the subscription auth the fleet already
            # uses; haiku + hard timeout so a hang can never wedge the scrape.
            raw = self._claude_cli_complete(system, user)
        if raw is None:
            logger.warning("[%s] no LLM produced output — using regex fallback",
                           self.source_name)
            return None

        # Tolerate code fences / stray prose around the JSON.
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            logger.warning("[%s] LLM returned no JSON — using regex fallback", self.source_name)
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            logger.warning("[%s] LLM JSON parse error — using regex fallback", self.source_name)
            return None

        events = []
        for item in data.get("events", []):
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or "").strip()
            date = (item.get("date") or "").strip()
            if not name or not date:
                continue
            try:
                idx = int(item.get("post", -1))
            except (TypeError, ValueError):
                idx = -1
            url = posts[idx]["url"] if 0 <= idx < len(posts) else self.profile_url
            venue = (item.get("venue") or "").strip() or self.default_venue
            events.append(self.make_event(
                name=self._clean_name(name),
                date=date,
                time=(item.get("time") or "").strip(),
                venue=venue,
                description=self.blurb,
                url=url,
                priority=self.priority,
            ))
        logger.info("[%s] LLM extracted %d dated events", self.source_name, len(events))
        return events

    @staticmethod
    def _deepseek_complete(system: str, user: str):
        """OpenAI-compatible DeepSeek call using the standing WORKER_API_KEY."""
        import os
        import urllib.request
        key = os.environ.get("WORKER_API_KEY", "")
        if not key:
            return None
        body = json.dumps({
            "model": "deepseek-chat",
            "max_tokens": 1500,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {key}"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                j = json.loads(r.read().decode("utf-8"))
            return (j["choices"][0]["message"]["content"] or "").strip()
        except Exception as e:
            logger.warning("[deepseek] extraction call failed: %s %s",
                           type(e).__name__, str(e)[:120])
            return None

    @staticmethod
    def _claude_cli_complete(system: str, user: str):
        """claude -p (haiku) with a hard timeout. Resolved by absolute path so it
        works under the pythonw scheduled runner too (the 2026-05-25 'claude CLI
        not found in PATH' failure mode)."""
        import os
        import shutil
        import subprocess
        exe = shutil.which("claude")
        if not exe:
            for cand in (os.path.expanduser("~/.local/bin/claude"),
                         os.path.expanduser("~/.local/bin/claude.exe"),
                         os.path.expanduser("~/AppData/Roaming/npm/claude.cmd")):
                if os.path.exists(cand):
                    exe = cand
                    break
        if not exe:
            logger.warning("[claude-cli] not found — skipping CLI extraction tier")
            return None
        # Dual-token failover, same mechanism as the runner's claude-tier tasks:
        # the primary account token 401s as of 2026-07 and the fleet succeeds via
        # the secondary ("[account: personal, FALLBACK]" in runner.log). Try the
        # CLI's own auth first, then each stored token.
        tokens = [None]
        try:
            vals = {}
            for line in (Path.home() / ".credentials" / "claude_tokens.env").read_text(
                    encoding="utf-8").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip()
            for key in ("CLAUDE_TOKEN_PRIMARY", "CLAUDE_TOKEN_SECONDARY"):
                if vals.get(key):
                    tokens.append(vals[key])
        except Exception:
            pass
        for tok in tokens:
            try:
                env = os.environ.copy()
                env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
                # Nested-session vars make claude -p 401 when invoked from inside a
                # live Claude Code session; strip them, then inject the token.
                for k in list(env):
                    if k.startswith("CLAUDE_CODE_") or k in ("CLAUDECODE", "CLAUDE_EFFORT",
                                                              "CLAUDE_CHROME_PERMISSION_MODE"):
                        env.pop(k, None)
                if tok:
                    env["CLAUDE_CODE_OAUTH_TOKEN"] = tok
                r = subprocess.run(
                    [exe, "-p", "--model", "claude-haiku-4-5-20251001"],
                    input=system + "\n\n" + user,
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=180, env=env)
                out = (r.stdout or "").strip()
                if r.returncode == 0 and out and "Failed to authenticate" not in out:
                    return out
                logger.warning("[claude-cli] rc=%s (%s): %s — trying next token",
                               r.returncode, "stored-token" if tok else "default-auth",
                               (out or r.stderr or "")[:100])
            except subprocess.TimeoutExpired:
                logger.warning("[claude-cli] timed out after 180s — trying next token")
            except Exception as e:
                logger.warning("[claude-cli] failed: %s %s", type(e).__name__, str(e)[:120])
        return None

    # ── relative-date resolution (works WITHOUT the LLM) ────────────────────────
    _WEEKDAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1,
                 "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3, "thur": 3,
                 "thurs": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5,
                 "sunday": 6, "sun": 6}

    @classmethod
    def _resolve_relative_date(cls, low_caption: str, posted_on: str) -> str:
        """Resolve a relative date phrase against the post date.

        Bars post in relative time ("THIS SATURDAY", "tomorrow", "THURSDAY",
        "tonight"). Anchor on the day the post went up (falling back to today),
        and resolve the FIRST relative cue found. A bare weekday resolves to its
        next occurrence on/after the post date (within the next 7 days), which is
        exactly how a "come THURSDAY" promo reads. Returns YYYY-MM-DD or "".
        """
        try:
            base = datetime.strptime(posted_on, "%Y-%m-%d") if posted_on else datetime.now()
        except (ValueError, TypeError):
            base = datetime.now()

        # tonight / today  → the post date itself
        if re.search(r"\b(tonight|today)\b", low_caption):
            return base.strftime("%Y-%m-%d")
        # tomorrow / tmrw / tmw  → +1 day
        if re.search(r"\b(tomorrow|tmrw|tmw|2morrow)\b", low_caption):
            return (base + timedelta(days=1)).strftime("%Y-%m-%d")

        # "this saturday" / "saturday" / "sat" → next occurrence on/after the post
        # date. Match longest weekday tokens first so "thurs" isn't shadowed by "thu".
        for token in sorted(cls._WEEKDAYS, key=len, reverse=True):
            if re.search(r"\b" + token + r"\b", low_caption):
                target = cls._WEEKDAYS[token]
                delta = (target - base.weekday()) % 7
                # A weekday named on its own day means that day (delta 0), not +7.
                return (base + timedelta(days=delta)).strftime("%Y-%m-%d")
        return ""

    # ── regex fallback (no API key / LLM unavailable) ───────────────────────────
    def _extract_with_regex(self, posts: List[Dict]) -> List[Dict]:
        events = []
        time_rx = re.compile(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b", re.I)
        num_rx = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")
        month_rx = re.compile(
            r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b",
            re.I,
        )
        months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                  "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
        year = datetime.now().year

        for p in posts:
            caption = p["caption"]
            low = caption.lower()
            if not any(kw in low for kw in EVENT_KEYWORDS):
                continue

            date_str = ""
            m = num_rx.search(caption)
            if m:
                mo, da = int(m.group(1)), int(m.group(2))
                yr = m.group(3)
                yr = int(yr) + 2000 if yr and len(yr) == 2 else (int(yr) if yr else year)
                try:
                    date_str = datetime(yr, mo, da).strftime("%Y-%m-%d")
                except ValueError:
                    date_str = ""
            if not date_str:
                mm = month_rx.search(caption)
                if mm:
                    mo = months[mm.group(1)[:3].lower()]
                    da = int(mm.group(2))
                    try:
                        date_str = datetime(year, mo, da).strftime("%Y-%m-%d")
                    except ValueError:
                        date_str = ""

            if not date_str:
                # Relative dates resolved against the POST date (bars almost never
                # write "6/20" — they write "THIS SATURDAY", "TOMORROW", "THURSDAY",
                # "tonight"). Without this, every IG-only bar source (YBR, Eagle,
                # Majestic, Studio 66) silently yields 0 events whenever the LLM key
                # is unset and the regex path runs. (2026-06-20, per William.)
                date_str = self._resolve_relative_date(low, p.get("posted_on", ""))

            if not date_str:
                continue  # genuinely no resolvable date — skip

            tmatch = time_rx.search(caption)
            time_str = tmatch.group(1).upper() if tmatch else ""
            ev_name = self._derive_event_name(caption, self.default_venue)

            events.append(self.make_event(
                name=ev_name,
                date=date_str,
                time=time_str,
                venue=self.default_venue,
                description=self.blurb,
                url=p["url"],
                priority=self.priority,
            ))
        logger.info("[%s] Regex fallback extracted %d dated events",
                    self.source_name, len(events))
        return events


def scrape() -> List[Dict]:
    """Module-level entry point (matches the runner's scraper contract).

    Runs every configured IG-only org independently so one failure never aborts
    the rest, and returns the combined in-week event list.
    """
    all_events = []
    for org in ORGS:
        try:
            events = InstagramOrgScraper(org).safe_scrape()
            logger.info("[instagram_orgs] %s: %d events", org["source_name"], len(events))
            all_events.extend(events)
        except Exception as e:
            logger.error("[instagram_orgs] %s crashed: %s", org["source_name"], e)
    return all_events


def _selftest() -> int:
    """Offline regression test for the no-LLM extraction path.

    Locks the 2026-06-20 fix: bar captions written in relative time + hype banners
    must still resolve to dated, presentably-named events without any network or
    API key. A silent regression here re-zeroes every IG-only bar source.
    """
    S = InstagramOrgScraper
    fails = []

    def _a(s):  # console (cp1252) safe — selftest must never crash on emoji
        return str(s).encode("ascii", "ignore").decode("ascii")

    # 1. Relative-date resolution anchored on the post date.
    cases = [
        ("come dance tonight!", "2026-06-20", "2026-06-20"),  # tonight = post day
        ("party tomorrow at 9", "2026-06-19", "2026-06-20"),  # tomorrow = +1
        ("THIS SATURDAY join us", "2026-06-17", "2026-06-20"),  # Wed post -> Sat
        ("come THURSDAY for talent", "2026-06-16", "2026-06-18"),  # Tue -> Thu
        ("see you sunday", "2026-06-20", "2026-06-21"),  # Sat -> next Sun
        ("no date here at all", "2026-06-17", ""),  # nothing resolvable
    ]
    for cap, posted, expect in cases:
        got = S._resolve_relative_date(cap.lower(), posted)
        tag = "OK" if got == expect else "FAIL"
        if got != expect:
            fails.append(f"reldate {cap!r}@{posted}: got {got!r} expected {expect!r}")
        print(f"[selftest] reldate {cap[:28]:28s} -> {got or '(none)':12s} {tag}")

    # 2. Smart name derivation — hype banners must NOT become the event name.
    venue = "Yellow Brick Road, 2630 E 15th St"
    name_cases = [
        ("‼️HEADS UP‼️\nWe're opening the back for our dance party tomorrow!",
         "Dance Party at YBR"),
        ("THIS SATURDAY\nsummer pride edition of B&B y'all!", "B&B Dance Party at YBR"),
        ("🎤THURSDAY🎤\nCome show us what you got, we're ready to see your talents!",
         "Talent Night at YBR"),
        ("Next Sunday making little queer donuts in a craft class!", "Craft Class at YBR"),
    ]
    for cap, expect in name_cases:
        got = S._derive_event_name(cap, venue)
        tag = "OK" if got == expect else "FAIL"
        if got != expect:
            fails.append(f"name {_a(cap[:25])!r}: got {got!r} expected {expect!r}")
        print(f"[selftest] name -> {_a(got):24s} {tag}")

    if fails:
        print("\n[selftest] FAILURES:")
        for f in fails:
            print("  -", _a(f))
        print("[selftest] FAILED")
        return 1
    print("[selftest] ALL PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    monday, sunday = InstagramOrgScraper._week_range()
    print(f"Instagram-org scraper — week {monday.date()} to {sunday.date()}")
    print("=" * 64)
    results = scrape()
    print(f"\nTOTAL IN-WEEK EVENTS: {len(results)}")

    def _ascii(s):  # console (cp1252) safe — diagnostics must never crash on emoji
        return str(s).encode("ascii", "ignore").decode("ascii")

    for e in results:
        print(f"  {e['date']} {_ascii(e.get('time','')):8s} | "
              f"{_ascii(e['name'])[:50]:50s} | {_ascii(e.get('venue',''))[:30]}")
    if not results:
        print("\n(0 events — either no configured org has an event dated this week, or the "
              "public endpoint was rate-limited. It needs no login; just re-run.)")
