"""Studio 66 (@studio.66_) Instagram event scraper.

Studio 66 is a Tulsa LGBTQIA+ nonprofit / roving events collective — dance parties,
RuPaul's Drag Race watch parties, fashion shows, and multi-day festivals (Bimbo
Summit, Bunny Ball). It has NO fixed venue and NO working website (s66tulsa.com is
a dead domain / NXDOMAIN as of 2026). Events live on Instagram only.

How it reads Instagram (auth-free):
Logged-out Instagram no longer embeds captions in the page HTML (lazy-loaded), but
Instagram's public web-profile JSON endpoint still returns the most recent posts WITH
captions for a public account when called with the web App-ID header — no login, no
session, no @tulsagays credentials. That is the primary path here and it needs nothing
from William. If that endpoint is ever rate-limited or blocked, the scraper falls back
to the authenticated instagrapi session shared with @tulsagays engagement
(~/.credentials/ig_settings_tulsagays.json) when one happens to be valid. Either way it
degrades to an empty list (never crashes) if both paths fail.

Event extraction: post captions are free text (dates like "THIS SATURDAY" or
"6/14 @ 9pm"), so we use Claude (SITES_ANTHROPIC_KEY) to pull structured events when a
key is present, with a regex / parse_date_flexible fallback otherwise. Only events
dated in the current Mon–Sun week are returned. Studio 66 is a trusted LGBTQ source,
so no keyword relevance filter is applied — but a parseable in-week date IS required.

Run standalone:  python scraper/studio66.py
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

USERNAME = "studio.66_"
PROFILE_URL = "https://www.instagram.com/studio.66_/"
# Public web App-ID — lets the logged-out web_profile_info JSON endpoint return posts.
IG_WEB_APP_ID = "936619743392459"
WEB_PROFILE_URL = (
    "https://www.instagram.com/api/v1/users/web_profile_info/?username={user}"
)
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36")
# Roving collective: never publish a fabricated street address (see VENUE_FACTS.md).
# No em dash in this event-facing string (preflight voice check bans them).
DEFAULT_VENUE = "Studio 66 (location varies, see @studio.66_)"
PRIORITY = 1            # primary LGBTQ nonprofit — fun one-off events, good featured/EOTW
POSTS_TO_SCAN = 12      # most recent posts to read each run

# A caption must look like an event announcement before we bother date-parsing it.
EVENT_KEYWORDS = [
    "join us", "come out", "tonight", "this week", "this saturday", "this friday",
    "this sunday", "this thursday", "tickets", "doors", "doors open", "rsvp",
    "party", "drag", "watch party", "show", "fashion", "ball", "summit", "festival",
    "fundraiser", "market", "bingo", "happy hour", "dance", "live", "performance",
    "lineup", "line up", "presale", "pre-sale", "@", "pm", "doors @",
]


class Studio66Scraper(BaseScraper):
    """Read @studio.66_ Instagram posts and extract this-week events."""

    source_name = "studio_66"

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
        """Strip em dashes (banned in William's voice / blocked by preflight) and
        collapse whitespace so caption-derived names are safe for slides + website."""
        if not name:
            return ""
        name = name.replace("—", ", ").replace("–", "-")  # em/en dash
        name = name.replace("“", '"').replace("”", '"')   # curly quotes
        name = name.replace("‘", "'").replace("’", "'")
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
        """Read recent @studio.66_ posts via Instagram's public web-profile JSON.

        No login / session / credentials. Returns a list of
        {caption, url, posted_on} dicts, or [] on any failure.
        """
        import requests
        headers = {
            "User-Agent": _UA,
            "X-IG-App-ID": IG_WEB_APP_ID,
            "Accept": "*/*",
            "Referer": PROFILE_URL,
        }
        try:
            r = requests.get(WEB_PROFILE_URL.format(user=USERNAME),
                             headers=headers, timeout=20)
        except Exception as e:
            logger.warning("[studio_66] public profile request failed: %s %s",
                           type(e).__name__, str(e)[:120])
            return []
        if r.status_code != 200:
            logger.warning("[studio_66] public profile HTTP %s (logged-out endpoint "
                           "may be rate-limited) — will try session fallback", r.status_code)
            return []
        try:
            user = (r.json().get("data", {}) or {}).get("user") or {}
            edges = (user.get("edge_owner_to_timeline_media") or {}).get("edges", [])
        except Exception as e:
            logger.warning("[studio_66] public profile JSON parse failed: %s", type(e).__name__)
            return []

        posts = []
        for e in edges[:POSTS_TO_SCAN]:
            node = e.get("node", {}) or {}
            cap_edges = (node.get("edge_media_to_caption") or {}).get("edges", [])
            caption = cap_edges[0]["node"]["text"].strip() if cap_edges else ""
            if not caption:
                continue
            code = node.get("shortcode") or node.get("code")
            post_url = f"https://www.instagram.com/p/{code}/" if code else PROFILE_URL
            ts = node.get("taken_at_timestamp")
            posted_on = ""
            if ts:
                try:
                    posted_on = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
                except (ValueError, OverflowError, OSError):
                    posted_on = ""
            posts.append({"caption": caption, "url": post_url, "posted_on": posted_on})

        logger.info("[studio_66] public endpoint returned %d captioned posts", len(posts))
        return posts

    # ── instagrapi session (read-only fallback, never a fresh login) ────────────
    def _fetch_via_session(self) -> List[Dict]:
        cl = self._client()
        if cl is None:
            return []
        try:
            uid = cl.user_id_from_username(USERNAME)
            medias = cl.user_medias(uid, amount=POSTS_TO_SCAN)
        except Exception as e:
            logger.warning("[studio_66] session fetch failed: %s %s",
                           type(e).__name__, str(e)[:160])
            return []
        posts = []
        for m in medias:
            caption = (getattr(m, "caption_text", "") or "").strip()
            if not caption:
                continue
            code = getattr(m, "code", None)
            post_url = f"https://www.instagram.com/p/{code}/" if code else PROFILE_URL
            taken = getattr(m, "taken_at", None)
            posted_on = taken.strftime("%Y-%m-%d") if isinstance(taken, datetime) else ""
            posts.append({"caption": caption, "url": post_url, "posted_on": posted_on})
        logger.info("[studio_66] session fallback returned %d captioned posts", len(posts))
        return posts

    def _client(self):
        if not SETTINGS_FILE.exists():
            logger.warning(
                "[studio_66] No @tulsagays IG session at %s — run "
                "scripts/ig_login_api.py once to enable Studio 66 scraping.",
                SETTINGS_FILE,
            )
            return None
        try:
            from instagrapi import Client
        except ImportError:
            logger.warning("[studio_66] instagrapi not installed — cannot read Instagram.")
            return None
        cl = Client()
        try:
            cl.load_settings(str(SETTINGS_FILE))
            cl.get_timeline_feed()  # cheap authenticated call to validate the session
            return cl
        except Exception as e:
            logger.warning(
                "[studio_66] @tulsagays IG session expired (%s) — re-auth once with "
                "scripts/ig_login_api.py to enable Studio 66 scraping.",
                type(e).__name__,
            )
            return None

    def _fetch_via_web_session(self) -> List[Dict]:
        """Tier 3 (gap G7): the proven fb_auto_profile web-session reader used by
        instagram_orgs. When the public endpoint is 429'd AND the instagrapi
        session is missing/expired, this drives the dedicated real-Chrome
        profile headlessly and reads the same public web API from an
        authenticated browser context. Re-auth (when the profile session
        lapses) is `python tools/ig_profile_login.py` — a human 'Log in with
        Facebook' click, NOT scripts/ig_login_api.py (bloks-challenge wall)."""
        try:
            from scraper import instagram_web
            raw = instagram_web.posts_for("studio_66", [USERNAME]) or []
        except Exception as e:
            logger.warning("[studio_66] web-session fetch failed: %s %s",
                           type(e).__name__, str(e)[:160])
            return []
        posts = []
        for p in raw:
            caption = (p.get("caption") or "").strip()
            if not caption:
                continue
            posts.append({
                "caption": caption,
                "url": p.get("url") or PROFILE_URL,
                "posted_on": (p.get("posted_on") or p.get("date") or ""),
            })
        logger.info("[studio_66] web-session fallback returned %d captioned posts", len(posts))
        return posts

    def scrape(self) -> List[Dict]:
        # Tier 1 auth-free public endpoint, tier 2 instagrapi session, tier 3
        # fb_auto_profile web session — first non-empty path wins (gap G7:
        # public 429 + missing instagrapi session left this dark with no
        # third path to fall through to).
        posts = self._fetch_public()
        if not posts:
            posts = self._fetch_via_session()
        if not posts:
            posts = self._fetch_via_web_session()
        if not posts:
            logger.info("[studio_66] No captioned posts from any of the 3 paths — 0 events.")
            return []

        events = self._extract_with_llm(posts)
        if events is None:
            events = self._extract_with_regex(posts)

        # Keep only events with a parseable date inside the current Mon–Sun week.
        in_week = [e for e in events if self._in_week(e.get("date", ""))]
        logger.info("[studio_66] %d candidate events, %d in current week",
                    len(events), len(in_week))
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
            "You extract concrete, dated events from an LGBTQ+ events collective's "
            "Instagram captions. Studio 66 is a roving Tulsa nonprofit with no fixed "
            "venue. Return ONLY events that have an identifiable calendar date. Resolve "
            "relative dates ('this Saturday', 'tonight', '6/14') against the post date "
            "and today's date. Output STRICT JSON only."
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
            logger.warning("[studio_66] LLM extraction failed (%s) — using regex fallback",
                           type(e).__name__)
            return None

        # Tolerate code fences / stray prose around the JSON.
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            logger.warning("[studio_66] LLM returned no JSON — using regex fallback")
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            logger.warning("[studio_66] LLM JSON parse error — using regex fallback")
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
            url = posts[idx]["url"] if 0 <= idx < len(posts) else PROFILE_URL
            venue = (item.get("venue") or "").strip() or DEFAULT_VENUE
            events.append(self.make_event(
                name=self._clean_name(name),
                date=date,
                time=(item.get("time") or "").strip(),
                venue=venue,
                description=f"Studio 66 event. Details and location on Instagram @{USERNAME}.",
                url=url,
                priority=PRIORITY,
            ))
        logger.info("[studio_66] LLM extracted %d dated events", len(events))
        return events

    # ── regex fallback (no API key / LLM unavailable) ───────────────────────────
    def _extract_with_regex(self, posts: List[Dict]) -> List[Dict]:
        events = []
        time_rx = re.compile(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b", re.I)
        # explicit numeric dates: 6/14, 06-14, 6/14/2026
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
            first_line = self._clean_name(caption.split("\n")[0])[:80] or "Studio 66 Event"

            events.append(self.make_event(
                name=first_line,
                date=date_str,
                time=time_str,
                venue=DEFAULT_VENUE,
                description=f"Studio 66 event. Details and location on Instagram @{USERNAME}.",
                url=p["url"],
                priority=PRIORITY,
            ))
        logger.info("[studio_66] Regex fallback extracted %d dated events", len(events))
        return events


def scrape() -> List[Dict]:
    """Module-level entry point (matches the runner's scraper contract)."""
    return Studio66Scraper().safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    monday, sunday = Studio66Scraper._week_range()
    print(f"Studio 66 scraper — week {monday.date()} to {sunday.date()}")
    print("=" * 64)
    results = scrape()
    print(f"\nTOTAL IN-WEEK EVENTS: {len(results)}")
    for e in results:
        print(f"  {e['date']} {e.get('time',''):8s} | {e['name'][:50]:50s} | {e.get('venue','')[:30]}")
    if not results:
        print("\n(0 events — either no Studio 66 events are dated in this week, or the "
              "public endpoint was rate-limited. It needs no login; just re-run.)")
