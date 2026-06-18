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
        "alt_usernames": ["ybrtulsa"],
        "source_name": "ybr_ig",
        "default_venue": "Yellow Brick Road, 2630 E 15th St",
        "priority": 2,
        "blurb": "Yellow Brick Road, Oklahoma's lesbian bar. "
                 "Details on Instagram @tulsaybr.",
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

    def scrape(self) -> List[Dict]:
        # Auth-free public endpoint first; authenticated session only as a fallback.
        posts = self._fetch_public()
        if not posts:
            posts = self._fetch_via_session()
        if not posts:
            logger.info("[%s] No captioned posts from either path — 0 events.",
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
        if not config.ANTHROPIC_API_KEY:
            return None
        try:
            from anthropic import Anthropic
        except ImportError:
            return None

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
        try:
            client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
            msg = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=1500,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            raw = msg.content[0].text.strip()
        except Exception as e:
            logger.warning("[%s] LLM extraction failed (%s) — using regex fallback",
                           self.source_name, type(e).__name__)
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
                continue  # no concrete date — skip (relative dates need the LLM path)

            tmatch = time_rx.search(caption)
            time_str = tmatch.group(1).upper() if tmatch else ""
            first_line = self._clean_name(caption.split("\n")[0])[:80] or f"@{self.username} event"

            events.append(self.make_event(
                name=first_line,
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


if __name__ == "__main__":
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
