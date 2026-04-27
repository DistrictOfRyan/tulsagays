"""Facebook Events scraper using Playwright with saved browser session.

REQUIRES: A saved Facebook session at data/fb_session.json
Run tools/fb_save_session.py once to authenticate and save the session.

Three source types:
  SEARCH_URLS  -- facebook.com/events/search?q=... (LGBTQ + broad Tulsa)
  PAGE_URLS    -- specific venue/org Facebook page event tabs
  GROUP_URLS   -- Tulsa LGBTQ+ Facebook group event tabs

tulsagays.com covers all Tulsa events of interest to the queer community,
not just explicitly LGBTQ events. Live music, brunches, art openings, drag,
comedy, dance parties -- all of it.
"""

import os
import sys
import re
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper.playwright_scrapers import PlaywrightBaseScraper, _parse_iso_datetime

logger = logging.getLogger(__name__)

SESSION_FILE = os.path.join(config.DATA_DIR, "fb_session.json")

# ── Event searches ─────────────────────────────────────────────────────────────
# All always_include=True: the blog covers all Tulsa community events, not just LGBTQ.
SEARCH_URLS = [
    # Explicitly queer
    ("https://www.facebook.com/events/search?q=lgbtq+tulsa", True),
    ("https://www.facebook.com/events/search?q=queer+tulsa", True),
    ("https://www.facebook.com/events/search?q=drag+tulsa", True),
    ("https://www.facebook.com/events/search?q=gay+tulsa", True),
    ("https://www.facebook.com/events/search?q=trans+tulsa", True),
    ("https://www.facebook.com/events/search?q=pride+tulsa", True),
    # Broad Tulsa community events (no keyword filter -- we want it all)
    ("https://www.facebook.com/events/search?q=tulsa+live+music", True),
    ("https://www.facebook.com/events/search?q=tulsa+brunch", True),
    ("https://www.facebook.com/events/search?q=tulsa+dance+party", True),
    ("https://www.facebook.com/events/search?q=tulsa+comedy", True),
    ("https://www.facebook.com/events/search?q=tulsa+karaoke", True),
    ("https://www.facebook.com/events/search?q=tulsa+trivia", True),
    ("https://www.facebook.com/events/search?q=tulsa+art", True),
    ("https://www.facebook.com/events/search?q=tulsa+open+mic", True),
    ("https://www.facebook.com/events/search?q=tulsa+happy+hour", True),
    ("https://www.facebook.com/events/search?q=tulsa+concert", True),
    ("https://www.facebook.com/events/search?q=tulsa+festival", True),
    ("https://www.facebook.com/events/search?q=tulsa", True),
]

# ── Known LGBTQ+ venue & org Facebook page event tabs ─────────────────────────
PAGE_URLS = [
    # Bars & nightlife
    "https://www.facebook.com/TheTulsaEagle/events",
    "https://www.facebook.com/YBRTulsa/events",
    "https://www.facebook.com/clubmajestictulsa/events",
    "https://www.facebook.com/dvltulsa/events",
    # Arts & culture
    "https://www.facebook.com/TwistedArtsTulsa/events",
    "https://www.facebook.com/queerlitcollective/events",
    "https://www.facebook.com/CouncilOakMensChorus/events",
    # Community orgs
    "https://www.facebook.com/allnations2S/events",          # All Nations Two-Spirit Society
    "https://www.facebook.com/tulsalambdaleague/events",     # Lambda Bowling
    "https://www.facebook.com/queerwomenscollectivetulsa/events",
    "https://www.facebook.com/p/Urban-Lgbt-Tulsa-inc-100085937172262/events",
    "https://www.facebook.com/people/Tulsa-House-of-Drag/61557097803540/events",
]

# ── Tulsa LGBTQ+ Facebook group event tabs ─────────────────────────────────────
GROUP_URLS = [
    # LGBTQ-specific groups
    "https://www.facebook.com/groups/161646500587551/events",          # Gay Men of Tulsa (1.3K)
    "https://www.facebook.com/groups/2612250565491228/events",         # Okie Gays (6K)
    "https://www.facebook.com/groups/715281449025002/events",          # Tulsa LGBTQ+ Scene (2.8K)
    "https://www.facebook.com/groups/472710852857064/events",          # LGBTQ Hot List
    "https://www.facebook.com/groups/220878821301627/events",          # LGBT Nightlife Tulsa
    # General Tulsa community / entertainment groups — goldmines for local events
    "https://www.facebook.com/groups/InterestingThingsToDoInTulsa/events",  # Interesting Things To Do In Tulsa (72K)
    "https://www.facebook.com/groups/funstufftodointulsa/events",      # Fun Stuff to Do in Tulsa!
    "https://www.facebook.com/groups/tulsaartists/events",             # Tulsa Artists
    # Music & shows groups
    "https://www.facebook.com/groups/1996680830384050/events",         # Tulsa Concerts and Music Events
    "https://www.facebook.com/groups/862121663843106/events",          # Tulsa Events and Music Promotions
    # General events / community
    "https://www.facebook.com/groups/114530202225051/events",          # Tulsa Events (TULSA EVENT)
    "https://www.facebook.com/groups/2974145312757018/events",         # Tulsa Conscious Community and Events
]

LGBTQ_KEYWORDS = [
    "lgbtq", "queer", "gay", "lesbian", "bi", "trans", "drag", "pride",
    "rainbow", "dyke", "nonbinary", "non-binary", "gender", "equality",
    "affirming", "inclusive", "homo", "sapphic",
]


def _get_week_range(week_offset: int = 0) -> Tuple[datetime, datetime]:
    today = datetime.now()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    sunday = monday + timedelta(days=6)
    return (
        monday.replace(hour=0, minute=0, second=0, microsecond=0),
        sunday.replace(hour=23, minute=59, second=59, microsecond=999999),
    )


def _is_in_week(date_str: str, week_offset: int = 0) -> bool:
    if not date_str:
        return False
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        monday, sunday = _get_week_range(week_offset)
        return monday <= dt <= sunday
    except ValueError:
        return False


def _is_lgbtq_relevant(name: str, description: str = "") -> bool:
    combined = (name + " " + description).lower()
    return any(kw in combined for kw in LGBTQ_KEYWORDS)


class FacebookEventsScraper(PlaywrightBaseScraper):
    """Playwright-based Facebook Events scraper using a saved browser session."""

    source_name = "facebook_events"
    PRIORITY = 2

    def __init__(self, week_offset: int = 0):
        super().__init__()
        self.week_offset = week_offset
        self._context = None

    def _start_browser(self):
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()

        if not os.path.exists(SESSION_FILE):
            logger.warning(
                "[facebook_events] No session file found at %s. "
                "Run tools/fb_login.py first to authenticate.",
                SESSION_FILE,
            )
            self._browser = None
            self._context = None
            return

        logger.info(f"[facebook_events] Loading saved session from {SESSION_FILE}")
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        self._context = self._browser.new_context(
            storage_state=SESSION_FILE,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/134.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )

    def _stop_browser(self):
        try:
            if self._context:
                self._context.close()
                self._context = None
        except Exception:
            pass
        super()._stop_browser()

    def _fetch_with_session(self, url: str, wait_for: str = None, timeout: int = 20000) -> Optional[str]:
        if not self._context:
            return None
        try:
            page = self._context.new_page()
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            if wait_for:
                try:
                    page.wait_for_selector(wait_for, timeout=timeout)
                except Exception:
                    pass
            else:
                try:
                    page.wait_for_load_state("networkidle", timeout=min(timeout, 10000))
                except Exception:
                    pass
            html = page.content()
            page.close()
            return html
        except Exception as e:
            logger.error(f"[facebook_events] fetch failed for {url}: {e}")
            return None

    def _scrape_search_page(self, url: str, always_include: bool) -> List[Dict]:
        """Fetch a search results page and extract events from the visible page text.

        Facebook's event search renders each card as:
          Date/time line
          Event name
          Venue
          X interested · Y going

        We parse that repeating block from page.innerText and pair each event
        name with the event URL found nearby in the DOM.
        """
        if not self._context:
            return []
        try:
            page = self._context.new_page()
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            try:
                page.wait_for_selector("a[href*='/events/']", timeout=15000)
            except Exception:
                pass
            import time as _time
            _time.sleep(2)
            page.evaluate("window.scrollTo(0, 800)")
            _time.sleep(2)

            if self._is_login_wall(page.content()):
                logger.warning(f"[facebook_events] Login wall at {url} -- re-run tools/fb_save_session.py")
                page.close()
                return []

            # Get visible text and map of event ID -> link text (event name in link)
            data = page.evaluate("""
                () => {
                    const text = document.body.innerText || '';
                    const seen = new Set();
                    const linkNames = {};
                    const orderedIds = [];
                    for (const link of document.querySelectorAll('a[href*="/events/"]')) {
                        const m = link.href.match(/\\/events\\/(\\d{8,})\\//);
                        if (!m) continue;
                        const eid = m[1];

                        // FB event cards often have TWO links per event: image link (empty
                        // innerText) followed by title link (has the event name). We keep the
                        // BEST (longest) text seen for each ID rather than deduping on first.
                        let t = (link.innerText || link.textContent || '').trim();
                        if (!t) t = link.getAttribute('aria-label') || '';
                        if (!t) t = link.getAttribute('title') || '';

                        const existing = linkNames[eid] || '';
                        const better = t.length > existing.length ? t : existing;
                        linkNames[eid] = better.slice(0, 200);

                        if (!seen.has(eid)) {
                            seen.add(eid);
                            orderedIds.push(eid);
                        }
                    }
                    return { text, linkNames, orderedIds };
                }
            """)
            page.close()
        except Exception as e:
            logger.error(f"[facebook_events] search page scrape failed for {url}: {e}")
            return []

        full_text = data.get("text", "")
        link_names = data.get("linkNames", {})
        ordered_ids = data.get("orderedIds", [])
        logger.debug(f"[facebook_events] {len(ordered_ids)} event links, sample: {dict(list(link_names.items())[:5])}")
        return self._parse_text_blocks(full_text, link_names, ordered_ids, always_include)

    def _parse_text_blocks(self, full_text: str, link_names: Dict[str, str], ordered_ids: List[str], always_include: bool) -> List[Dict]:
        """Parse events from Facebook's visible page text.

        Parses the repeating block structure (date, name, venue, engagement)
        and matches each event name to an event URL via link_names -- a dict
        mapping event ID to the link's own text content (usually the event name).

        link_names is used purely for URL lookup: find the ID whose link text
        best matches the parsed event name.
        """
        lines = [l.strip().replace("\u202f", " ").replace("\xa0", " ")
                 for l in full_text.split("\n") if l.strip()]

        DATE_PATTERNS = [
            r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),',
            r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d',
            r'(?:Today|Tomorrow|This (?:Mon|Tue|Wed|Thu|Fri|Sat|Sun))',
            r'\d{1,2}/\d{1,2}',
        ]
        JUNK = {"interested", "share", "going", "more", "events", "search results",
                "online", "paid", "dates", "categories", "load more"}

        def is_date_line(line: str) -> bool:
            return any(re.search(p, line, re.IGNORECASE) for p in DATE_PATTERNS)

        events: List[Dict] = []
        i = 0

        while i < len(lines):
            line = lines[i]
            if not is_date_line(line):
                i += 1
                continue

            date_line = line
            name = ""
            venue = "Tulsa, OK"

            # Scan next lines for name and venue
            j = i + 1
            while j < min(i + 7, len(lines)):
                candidate = lines[j]
                lower = candidate.lower()
                j += 1
                if lower in JUNK:
                    continue
                if re.search(r'\d[\d.,]*[KM]?\s+(?:interested|going)', candidate, re.IGNORECASE):
                    break
                if not name:
                    name = candidate
                elif venue == "Tulsa, OK" and not re.search(r'interested|going', lower):
                    venue = candidate
                    break

            i = j  # advance past consumed lines

            if not name or len(name) < 5 or name.lower() in JUNK:
                continue
            if re.search(r'\d+\s+(?:interested|going)', name, re.IGNORECASE):
                continue

            date_str, time_str = self._parse_fb_date(date_line)

            if not always_include and not _is_lgbtq_relevant(name, ""):
                continue

            # Find best-matching event URL by word-overlap ratio against link text.
            # Recurring events (same name, multiple dates) intentionally reuse the same URL.
            url = ""
            best_ratio = 0.0
            best_id = None
            name_lower = name.lower()
            name_words = set(w for w in re.findall(r'\w+', name_lower) if len(w) > 1)

            for eid, link_text in link_names.items():
                lt = link_text.lower()
                # Exact normalized match -- highest priority
                if re.sub(r'\W+', '', name_lower) == re.sub(r'\W+', '', lt) and lt:
                    best_ratio = 1.0
                    best_id = eid
                    break
                if not name_words:
                    continue
                link_words = set(w for w in re.findall(r'\w+', lt) if len(w) > 1)
                shared = len(name_words & link_words)
                ratio = shared / len(name_words)
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_id = eid

            if best_id and best_ratio >= 0.5:
                url = f"https://www.facebook.com/events/{best_id}/"

            if re.search(r'\d+\s+(?:interested|going)', venue, re.IGNORECASE):
                venue = "Tulsa, OK"

            events.append(self.make_event(
                name=name,
                date=date_str,
                time=time_str,
                venue=venue,
                url=url,
                priority=self.PRIORITY,
            ))

        return events

    def _parse_fb_date(self, date_line: str) -> Tuple[str, str]:
        """Parse Facebook's human-readable date strings into (YYYY-MM-DD, time_str)."""
        if not date_line:
            return "", ""

        # Normalize narrow no-break spaces
        date_line = date_line.replace("\u202f", " ").replace("\xa0", " ").strip()
        today = datetime.now()

        # Relative: "Today at 7 PM", "Tomorrow at 10 PM"
        dl = date_line.lower()
        time_match = re.search(r'at\s+(\d+(?::\d+)?\s*[AP]M)', date_line, re.IGNORECASE)
        time_str = time_match.group(1).strip() if time_match else ""

        if dl.startswith("today"):
            return today.strftime("%Y-%m-%d"), time_str
        if dl.startswith("tomorrow"):
            return (today + timedelta(days=1)).strftime("%Y-%m-%d"), time_str

        # "This Sunday at 8 AM", "This Saturday at 6 PM"
        day_names = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
        for i, day in enumerate(day_names):
            if f"this {day}" in dl:
                days_ahead = (i - today.weekday()) % 7
                dt = today + timedelta(days=days_ahead)
                return dt.strftime("%Y-%m-%d"), time_str

        # Absolute: "Fri, Apr 24 at 6 PM" or "Apr 24 at 6 PM"
        # Strip recurring-event suffix: "at 6 PM and 34 more" -> "at 6 PM"
        date_line = re.sub(r'\s+and\s+\d+\s+more.*$', '', date_line, flags=re.IGNORECASE)
        m = re.match(r'(?:\w+,\s+)?(\w+\s+\d+)(?:\s+at\s+(.+))?', date_line)
        if m:
            date_part = m.group(1).strip()   # "Apr 24"
            time_part = (m.group(2) or "").strip()
            for fmt in ("%b %d", "%B %d"):
                try:
                    dt = datetime.strptime(date_part, fmt).replace(year=today.year)
                    return dt.strftime("%Y-%m-%d"), time_part
                except ValueError:
                    continue

        return "", time_str

    def _is_login_wall(self, html: str) -> bool:
        markers = [
            'id="loginbutton"',
            'name="login"',
            "log in to facebook",
            "you must log in",
            "create new account",
        ]
        sample = html[:5000].lower()
        return any(m in sample for m in markers)

    def _extract_event_ids(self, html: str) -> List[str]:
        """Pull unique Facebook event IDs from raw HTML -- matches relative and absolute URLs."""
        seen = set()
        result = []
        for pattern in [
            r'/events/(\d{8,})(?:[/?&]|$)',   # relative: /events/123/ or /events/123?
            r'facebook\.com/events/(\d{8,})',  # absolute: facebook.com/events/123
        ]:
            for eid in re.findall(pattern, html):
                if eid not in seen:
                    seen.add(eid)
                    result.append(eid)
        return result

    def _parse_event_page(self, url: str) -> Optional[Dict]:
        """Visit a single FB event page and extract structured data."""
        html = self._fetch_with_session(url, timeout=15000)
        if not html:
            return None

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # JSON-LD is the most reliable
        events = self._extract_json_ld_from_soup(soup, "", self.PRIORITY)
        if events:
            e = events[0]
            e.setdefault("url", url)
            e["source"] = self.source_name
            return e

        # OG meta tags fallback
        name, date_str, time_str, venue, description = "", "", "", "", ""

        og_title = soup.find("meta", property="og:title")
        if og_title:
            name = og_title.get("content", "")

        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            description = og_desc.get("content", "")[:500]

        for attr in ["event:start_time", "og:event:start_time"]:
            el = soup.find("meta", property=attr) or soup.find("meta", {"name": attr})
            if el and el.get("content"):
                date_str, time_str = _parse_iso_datetime(el["content"])
                break

        loc_el = soup.find("meta", property="event:location")
        if loc_el:
            venue = loc_el.get("content", "")

        if not name:
            title_el = soup.find("title")
            if title_el:
                name = title_el.get_text(strip=True).replace("| Facebook", "").strip()

        if not name or len(name) < 3:
            return None

        return self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue=venue or "Tulsa, OK",
            description=description,
            url=url,
            priority=self.PRIORITY,
        )

    def scrape(self) -> List[Dict]:
        if not self._context:
            logger.warning("[facebook_events] No session -- skipping. Run tools/fb_save_session.py first.")
            return []

        monday, sunday = _get_week_range(self.week_offset)
        logger.info(f"[facebook_events] Target week: {monday.date()} to {sunday.date()}")

        seen_keys: set = set()
        all_events: List[Dict] = []

        def _add_events(cards: List[Dict], source_label: str):
            added = 0
            for event in cards:
                date_str = event.get("date", "")
                # FB events without a parsed date are recurring series stubs
                # (e.g. "Sports league") -- skip them, they're not actionable.
                if not date_str:
                    continue
                if not _is_in_week(date_str, self.week_offset):
                    continue
                dedup_key = (re.sub(r'\W+', '', event['name'].lower()), date_str)
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)
                all_events.append(event)
                added += 1
                logger.info(f"[{source_label}] + {event['name']} ({date_str or 'no date'})")
            return added

        # 1. Event searches
        for search_url, always_include in SEARCH_URLS:
            label = search_url.split("q=")[-1]
            logger.info(f"[facebook_events] search: {label}")
            cards = self._scrape_search_page(search_url, always_include)
            added = _add_events(cards, f"fb:{label}")
            logger.info(f"[facebook_events]   {len(cards)} parsed, {added} new in week")

        # 2. Venue/org page event tabs
        for page_url in PAGE_URLS:
            label = page_url.split("facebook.com/")[-1].split("/events")[0]
            logger.info(f"[facebook_events] page: {label}")
            cards = self._scrape_search_page(page_url, always_include=True)
            added = _add_events(cards, f"fb:{label}")
            logger.info(f"[facebook_events]   {len(cards)} parsed, {added} new in week")

        # 3. Group event tabs
        for group_url in GROUP_URLS:
            label = "group/" + group_url.split("/groups/")[-1].split("/events")[0]
            logger.info(f"[facebook_events] group: {label}")
            cards = self._scrape_search_page(group_url, always_include=True)
            added = _add_events(cards, f"fb:{label}")
            logger.info(f"[facebook_events]   {len(cards)} parsed, {added} new in week")

        logger.info(f"[facebook_events] Done: {len(all_events)} total events in target week")
        return all_events

    def safe_scrape(self) -> List[Dict]:
        try:
            self._start_browser()
            if not self._context:
                return []
            events = self.scrape()
            # Save refreshed cookies after a successful run so FB's 90-day
            # session expiry resets automatically each week.
            if events and self._context:
                try:
                    self._context.storage_state(path=SESSION_FILE)
                    logger.info(f"[facebook_events] Session refreshed: {SESSION_FILE}")
                except Exception as e:
                    logger.warning(f"[facebook_events] Could not refresh session: {e}")
            return events
        except Exception as e:
            logger.error(f"[facebook_events] Scraper crashed: {e}", exc_info=True)
            return []
        finally:
            self._stop_browser()


def scrape(week_offset: int = 0) -> List[Dict]:
    """Module-level entry point used by runner.py."""
    return FacebookEventsScraper(week_offset=week_offset).safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    events = scrape()
    print(f"\nFacebook Events: {len(events)} found")
    for e in events:
        print(f"  {e.get('date','?')} {e.get('time',''):10s} | {e['name'][:55]} | {e.get('venue','')[:30]}")
