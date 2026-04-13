"""Playwright-based scrapers for JavaScript-rendered event pages.

Covers sources that requests+BeautifulSoup can't read because they require
JavaScript execution:
- Freedom Oklahoma (Squarespace)
- Twisted Arts (Squarespace)
- Black Queer Tulsa (Squarespace)
- All Souls Unitarian (JS-rendered calendar at /events-calendar)
- Eventbrite (JS-rendered event cards)
- Visit Tulsa (JS-rendered calendar, LGBTQ keyword filter applied after load)
- OKEQ (JS-rendered -- public site, NOT a login wall; old requests scraper had wrong URL)
- Circle Cinema (React app, LGBTQ filter applied)
- Philbrook Museum of Art (JS-rendered, LGBTQ filter applied)

Run standalone: python scraper/playwright_scrapers.py
"""

import sys
import os
import re
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

# ── LGBTQ keyword filter ───────────────────────────────────────────────────────

LGBTQ_KEYWORDS = [
    "lgbtq", "queer", "gay", "lesbian", "bi", "trans", "drag", "pride",
    "rainbow", "dyke", "nonbinary", "non-binary", "gender", "equality",
    "affirming", "inclusive", "homo", "sapphic",
]


def _is_lgbtq_relevant(name: str, description: str = "") -> bool:
    combined = (name + " " + description).lower()
    return any(kw in combined for kw in LGBTQ_KEYWORDS)


# ── Week range helper ──────────────────────────────────────────────────────────

def _get_week_range():
    """Return (monday, sunday) datetime objects for the current week."""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return (
        monday.replace(hour=0, minute=0, second=0, microsecond=0),
        sunday.replace(hour=23, minute=59, second=59, microsecond=999999),
    )


def _is_in_current_week(date_str: str) -> bool:
    """Return True if date_str (YYYY-MM-DD) falls within the current Mon-Sun week."""
    if not date_str:
        return False
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        monday, sunday = _get_week_range()
        return monday <= dt <= sunday
    except ValueError:
        return False


# ── Date parsing helpers ───────────────────────────────────────────────────────

def _parse_iso_datetime(raw: str):
    """Parse an ISO datetime string like 2026-04-09T19:30:00.
    Returns (date_str, time_str) tuple as (YYYY-MM-DD, HH:MM AM/PM).
    """
    if not raw:
        return "", ""
    raw = raw.strip()
    try:
        if "T" in raw:
            date_part = raw[:10]
            time_part = raw[11:16]  # HH:MM
            try:
                dt = datetime.strptime(time_part, "%H:%M")
                time_str = dt.strftime("%I:%M %p").lstrip("0")
            except ValueError:
                time_str = time_part
            return date_part, time_str
        else:
            return raw[:10], ""
    except Exception:
        return "", ""


def _parse_timestamp_ms(ts) -> tuple:
    """Parse a millisecond or second Unix timestamp into (date_str, time_str)."""
    try:
        ts = int(ts)
        if ts > 1e10:
            ts = ts / 1000
        dt = datetime.utcfromtimestamp(ts)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%I:%M %p").lstrip("0")
    except Exception:
        return "", ""


# ── PlaywrightBaseScraper ──────────────────────────────────────────────────────

class PlaywrightBaseScraper(BaseScraper):
    """Base class for Playwright-powered scrapers.

    Launches Chromium in headless mode via playwright.sync_api.
    Each scraper instance manages its own browser lifecycle.
    """

    source_name = "playwright_base"

    def __init__(self):
        super().__init__()
        self._playwright = None
        self._browser = None

    def _start_browser(self):
        """Launch Playwright Chromium browser."""
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        logger.debug(f"[{self.source_name}] Browser started")

    def _stop_browser(self):
        """Close browser and Playwright instance cleanly."""
        try:
            if self._browser:
                self._browser.close()
                self._browser = None
        except Exception as e:
            logger.debug(f"[{self.source_name}] Browser close error: {e}")
        try:
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
        except Exception as e:
            logger.debug(f"[{self.source_name}] Playwright stop error: {e}")

    def fetch_page_js(
        self,
        url: str,
        wait_for_selector: Optional[str] = None,
        timeout: int = 15000,
    ) -> Optional[str]:
        """Fetch a URL using Playwright and return the rendered HTML.

        Args:
            url: Target URL to load.
            wait_for_selector: CSS selector to wait for before returning HTML.
                               If None, just waits for network idle.
            timeout: Max time in milliseconds to wait.

        Returns:
            HTML string after JS execution, or None on failure.
        """
        if not self._browser:
            logger.error(f"[{self.source_name}] Browser not started -- call _start_browser() first")
            return None
        try:
            context = self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/134.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            logger.info(f"[{self.source_name}] Playwright fetching {url}")
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")

            if wait_for_selector:
                try:
                    page.wait_for_selector(wait_for_selector, timeout=timeout)
                    logger.debug(f"[{self.source_name}] Selector '{wait_for_selector}' found")
                except Exception:
                    logger.debug(
                        f"[{self.source_name}] Selector '{wait_for_selector}' not found, "
                        "using page as-is"
                    )
            else:
                try:
                    page.wait_for_load_state("networkidle", timeout=min(timeout, 10000))
                except Exception:
                    pass  # networkidle timeout is not fatal

            html = page.content()
            page.close()
            context.close()
            return html
        except Exception as e:
            logger.error(f"[{self.source_name}] fetch_page_js failed for {url}: {e}")
            return None

    def safe_scrape(self) -> List[Dict]:
        """Run scrape() with browser lifecycle management and full error handling."""
        try:
            self._start_browser()
            events = self.scrape()
            logger.info(f"[{self.source_name}] Scraped {len(events)} events")
            return events
        except Exception as e:
            logger.error(f"[{self.source_name}] Scraper crashed: {e}", exc_info=True)
            return []
        finally:
            self._stop_browser()

    def scrape(self) -> List[Dict]:
        raise NotImplementedError("Subclasses must implement scrape()")

    # ── Shared Squarespace extraction ─────────────────────────────────────────

    def _extract_squarespace_html(self, html: str, base_url: str, venue: str, priority: int) -> List[Dict]:
        """Parse Squarespace event list HTML after JS rendering.

        Squarespace event pages use .eventlist-event containers.
        Dates live in time[datetime] attributes (ISO format).
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        events = []

        # Try JSON-LD first -- most reliable when present
        events = self._extract_json_ld_from_soup(soup, venue, priority)
        if events:
            logger.info(f"[{self.source_name}] JSON-LD extracted {len(events)} events")
            return events

        # Squarespace rendered selectors (order matters: most specific first)
        containers = (
            soup.select("article.eventlist-event--upcoming")
            or soup.select("article.eventlist-event")
            or soup.select(".eventlist-event")
            or soup.select(".summary-item[data-type='event']")
            or soup.select(".summary-item")
            or soup.select("[class*='eventlist']")
        )

        logger.debug(f"[{self.source_name}] Found {len(containers)} Squarespace containers")

        for container in containers[:30]:
            event = self._parse_squarespace_container(container, base_url, venue, priority)
            if event:
                events.append(event)

        return events

    def _parse_squarespace_container(self, container, base_url: str, venue: str, priority: int) -> Optional[Dict]:
        """Parse one Squarespace event container element."""
        # Name
        name_el = (
            container.select_one(".eventlist-title a")
            or container.select_one(".eventlist-title")
            or container.select_one(".summary-title a")
            or container.select_one(".summary-title")
            or container.select_one("h1, h2, h3")
        )
        if not name_el:
            return None
        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            return None

        # URL
        link_el = name_el if name_el.name == "a" else (name_el.find("a") or container.find("a", href=True))
        url = ""
        if link_el and link_el.get("href"):
            href = link_el["href"]
            url = href if href.startswith("http") else base_url.rstrip("/") + "/" + href.lstrip("/")

        # Date: look for time[datetime] first (ISO format), then text
        date_str, time_str = "", ""
        time_el = (
            container.select_one("time[datetime]")
            or container.select_one(".eventlist-datetag-startdate[datetime]")
        )
        if time_el:
            raw = time_el.get("datetime", "")
            if raw:
                date_str, time_str = _parse_iso_datetime(raw)

        if not date_str:
            # Try text-based date fallback
            date_tag = (
                container.select_one(".eventlist-datetag")
                or container.select_one(".eventlist-datetag-inner")
                or container.select_one(".event-date")
            )
            if date_tag:
                raw_text = date_tag.get_text(strip=True)
                date_str = BaseScraper.parse_date_flexible(raw_text)

        # Time fallback from text
        if not time_str:
            time_tag = (
                container.select_one(".eventlist-meta-time")
                or container.select_one(".event-time-12hr")
                or container.select_one("[class*='time']")
            )
            if time_tag:
                time_str = time_tag.get_text(strip=True)

        # Description
        desc_el = (
            container.select_one(".eventlist-description")
            or container.select_one(".summary-excerpt")
            or container.select_one("p")
        )
        description = desc_el.get_text(strip=True)[:500] if desc_el else ""

        return self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue=venue,
            description=description,
            url=url,
            priority=priority,
        )

    def _extract_json_ld_from_soup(self, soup, venue: str, priority: int) -> List[Dict]:
        """Extract Event items from JSON-LD script blocks in a BeautifulSoup object.

        Handles multiple JSON-LD formats:
        - Top-level @type: Event (standard)
        - Top-level list of events
        - itemListElement: [{item: {Event}}] (Eventbrite format)
        - @graph: [{Event}] (some CMS formats)
        """
        events = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw = script.string
                if not raw:
                    continue
                data = json.loads(raw)

                # Collect all candidate event objects from various nesting formats
                candidates = []

                if isinstance(data, list):
                    candidates.extend(data)
                elif isinstance(data, dict):
                    # Standard: top-level is one event
                    candidates.append(data)
                    # itemListElement: [{position, @type:ListItem, item:{Event}}]
                    for list_item in data.get("itemListElement", []):
                        if isinstance(list_item, dict):
                            inner = list_item.get("item", {})
                            if isinstance(inner, dict):
                                candidates.append(inner)
                    # @graph array
                    for graph_item in data.get("@graph", []):
                        if isinstance(graph_item, dict):
                            candidates.append(graph_item)

                for item in candidates:
                    if not isinstance(item, dict):
                        continue
                    if item.get("@type") not in ("Event", "SocialEvent", "MusicEvent"):
                        continue
                    name = item.get("name", "")
                    if not name or len(name) < 3:
                        continue
                    start = item.get("startDate", "")
                    date_str, time_str = _parse_iso_datetime(start)
                    location = item.get("location", {})
                    loc_name = venue
                    if isinstance(location, dict):
                        loc_name = location.get("name", venue) or venue
                    description = item.get("description", "")[:500]
                    url = item.get("url", "")
                    events.append(self.make_event(
                        name=name,
                        date=date_str,
                        time=time_str,
                        venue=loc_name,
                        description=description,
                        url=url,
                        priority=priority,
                    ))
            except Exception:
                continue
        return events


# ── Individual scrapers ────────────────────────────────────────────────────────

class FreedomOklahomaScraper(PlaywrightBaseScraper):
    """Freedom Oklahoma -- Squarespace events page (JS-rendered)."""

    source_name = "freedom_oklahoma"
    BASE_URL = "https://www.freedomoklahoma.org"
    EVENTS_URL = "https://www.freedomoklahoma.org/events"
    DEFAULT_VENUE = "Oklahoma City / Tulsa area"
    PRIORITY = 1

    def scrape(self) -> List[Dict]:
        html = self.fetch_page_js(
            self.EVENTS_URL,
            wait_for_selector=".eventlist-event, .summary-item, [class*='eventlist']",
            timeout=20000,
        )
        if not html:
            logger.warning(f"[{self.source_name}] No HTML returned from Playwright")
            return []

        events = self._extract_squarespace_html(html, self.BASE_URL, self.DEFAULT_VENUE, self.PRIORITY)
        logger.info(f"[{self.source_name}] Found {len(events)} raw events")
        return events


class TwistedArtsScraper(PlaywrightBaseScraper):
    """Twisted Arts / Twisted Fest -- Squarespace events page (JS-rendered)."""

    source_name = "twisted_arts"
    BASE_URL = "https://twistedfest.org"
    EVENTS_URL = "https://twistedfest.org/events"
    DEFAULT_VENUE = "Circle Cinema / Twisted Arts Tulsa"
    PRIORITY = 1

    def scrape(self) -> List[Dict]:
        html = self.fetch_page_js(
            self.EVENTS_URL,
            wait_for_selector=".eventlist-event, .summary-item, [class*='eventlist']",
            timeout=20000,
        )
        if not html:
            logger.warning(f"[{self.source_name}] No HTML returned from Playwright")
            return []

        events = self._extract_squarespace_html(html, self.BASE_URL, self.DEFAULT_VENUE, self.PRIORITY)
        logger.info(f"[{self.source_name}] Found {len(events)} raw events")
        return events


class BlackQueerTulsaScraper(PlaywrightBaseScraper):
    """Black Queer Tulsa -- Squarespace events page (JS-rendered)."""

    source_name = "black_queer_tulsa"
    BASE_URL = "https://www.blackqueertulsa.org"
    EVENTS_URL = "https://www.blackqueertulsa.org/events"
    DEFAULT_VENUE = "Various locations, Tulsa"
    PRIORITY = 1

    def scrape(self) -> List[Dict]:
        html = self.fetch_page_js(
            self.EVENTS_URL,
            wait_for_selector=".eventlist-event, .summary-item, [class*='eventlist']",
            timeout=20000,
        )
        if not html:
            logger.warning(f"[{self.source_name}] No HTML returned from Playwright")
            return []

        events = self._extract_squarespace_html(html, self.BASE_URL, self.DEFAULT_VENUE, self.PRIORITY)
        logger.info(f"[{self.source_name}] Found {len(events)} raw events")
        return events


class AllSoulsScraper(PlaywrightBaseScraper):
    """All Souls Unitarian Church -- special events only (not regular Sunday services).

    NOTE: allsoulschurch.org is a PUBLIC website. Primary URL is /events-calendar,
    fallback is /calendar. The old requests-based scraper failed due to JS rendering.
    Playwright waits for the calendar to fully load before extracting.
    """

    source_name = "all_souls_special"
    BASE_URL = "https://allsoulschurch.org"
    DEFAULT_VENUE = "All Souls Unitarian Church, 2952 S Peoria Ave"
    PRIORITY = 2

    # These patterns in the event name indicate a plain weekly service we skip
    SKIP_PATTERNS = [
        "sunday service",
        "sunday morning service",
        "sunday worship",
        "worship service",
        "regular service",
        "weekly service",
    ]

    def scrape(self) -> List[Dict]:
        urls_to_try = [
            "/events-calendar",
            "/calendar",
            "/events",
            "/upcoming-events",
        ]

        for path in urls_to_try:
            url = self.BASE_URL + path
            html = self.fetch_page_js(
                url,
                wait_for_selector=(
                    ".tribe-events-calendar-list__event, "
                    ".tribe-event, "
                    ".eventlist-event, "
                    "[class*='tribe-events'], "
                    "[class*='event'], .calendar-event"
                ),
                timeout=25000,
            )
            if not html:
                logger.debug(f"[{self.source_name}] No response from {url}")
                continue

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # Check for 404 / error page
            title_el = soup.find("title")
            page_title = title_el.get_text(strip=True).lower() if title_el else ""
            if "404" in page_title or "not found" in page_title:
                logger.debug(f"[{self.source_name}] 404 at {url}, trying next path")
                continue

            events = self._extract_json_ld_from_soup(soup, self.DEFAULT_VENUE, self.PRIORITY)
            if not events:
                events = self._extract_squarespace_html(html, self.BASE_URL, self.DEFAULT_VENUE, self.PRIORITY)
            if not events:
                events = self._extract_tribe_events(soup)

            if events:
                logger.info(f"[{self.source_name}] Found {len(events)} events at {url}")
                break

        # Filter out plain weekly Sunday services (already in recurring.py)
        before = len(events) if 'events' in dir() else 0
        events = [
            e for e in (events if 'events' in dir() else [])
            if not any(pat in e.get("name", "").lower() for pat in self.SKIP_PATTERNS)
        ]
        logger.info(f"[{self.source_name}] After filtering weekly services: {len(events)} events (was {before})")
        return events

    def _extract_tribe_events(self, soup) -> List[Dict]:
        """Try The Events Calendar (tribe) plugin patterns as fallback."""
        containers = (
            soup.select(".tribe-events-calendar-list__event")
            or soup.select(".tribe-events-list-event")
            or soup.select(".type-tribe_events")
        )
        events = []
        for container in containers[:20]:
            name_el = (
                container.select_one(".tribe-events-calendar-list__event-title a")
                or container.select_one(".tribe-events-calendar-list__event-title")
                or container.select_one("h2, h3")
            )
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 3:
                continue

            link_el = name_el if name_el.name == "a" else name_el.find("a")
            url = ""
            if link_el and link_el.get("href"):
                href = link_el["href"]
                url = href if href.startswith("http") else self.BASE_URL + href

            time_el = container.select_one("time[datetime]")
            date_str, time_str = "", ""
            if time_el:
                raw = time_el.get("datetime", "")
                date_str, time_str = _parse_iso_datetime(raw)

            events.append(self.make_event(
                name=name,
                date=date_str,
                time=time_str,
                venue=self.DEFAULT_VENUE,
                url=url,
                priority=self.PRIORITY,
            ))
        return events


class EventbriteJSScraper(PlaywrightBaseScraper):
    """Eventbrite LGBTQ Tulsa search -- JS-rendered event cards."""

    source_name = "eventbrite"
    PRIORITY = 2

    SEARCH_PATHS = [
        "https://www.eventbrite.com/d/ok--tulsa/lgbtq/",
        "https://www.eventbrite.com/d/ok--tulsa/pride/",
        "https://www.eventbrite.com/d/ok--tulsa/queer/",
        "https://www.eventbrite.com/d/ok--tulsa/drag/",
    ]

    def scrape(self) -> List[Dict]:
        """Two-phase scrape:
        Phase 1 — collect event URLs from search pages (no reliable dates on search results).
        Phase 2 — visit each individual event page for JSON-LD with actual startDate.
        Only events with dates in the current week are returned.
        """
        from bs4 import BeautifulSoup

        # Phase 1: collect up to 20 unique Eventbrite event URLs
        seen_names: set = set()
        event_stubs: List[Dict] = []  # {name, url}

        for search_url in self.SEARCH_PATHS:
            html = self.fetch_page_js(
                search_url,
                wait_for_selector=(
                    "[data-testid='event-card'], "
                    ".SearchResultPanelContent, "
                    ".event-card, "
                    "[class*='eventCard']"
                ),
                timeout=20000,
            )
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            links_found = 0
            for link in soup.find_all("a", href=True):
                href = link["href"]
                text = link.get_text(strip=True)
                if (
                    "eventbrite.com/e/" in href
                    and text
                    and len(text) > 8
                    and text.lower() not in seen_names
                ):
                    seen_names.add(text.lower())
                    event_stubs.append({
                        "name": text,
                        "url": href.split("?")[0],
                    })
                    links_found += 1
            logger.info(f"[{self.source_name}] {search_url}: {links_found} event links found")
            if len(event_stubs) >= 20:
                break

        logger.info(f"[{self.source_name}] Phase 1: {len(event_stubs)} unique event links")

        # Phase 2: visit each event page for JSON-LD (contains startDate)
        all_events = []
        monday, sunday = _get_week_range()

        for stub in event_stubs[:20]:
            ev_html = self.fetch_page_js(stub["url"], timeout=15000)
            if not ev_html:
                continue
            soup = BeautifulSoup(ev_html, "html.parser")
            found = self._extract_json_ld_from_soup(soup, "Tulsa, OK", self.PRIORITY)
            if found:
                for e in found:
                    if _is_in_current_week(e.get("date", "")):
                        all_events.append(e)
            else:
                # JSON-LD missing — parse meta tags for date
                date_str, time_str = "", ""
                meta_dt = soup.find("meta", {"property": "event:start_time"}) or soup.find("meta", {"name": "event:start_time"})
                if meta_dt and meta_dt.get("content"):
                    date_str, time_str = _parse_iso_datetime(meta_dt["content"])
                if date_str and _is_in_current_week(date_str):
                    all_events.append(self.make_event(
                        name=stub["name"],
                        date=date_str,
                        time=time_str,
                        url=stub["url"],
                        priority=self.PRIORITY,
                    ))

        logger.info(f"[{self.source_name}] Phase 2: {len(all_events)} events in current week with dates")
        return all_events

    def _extract_eventbrite_cards(self, soup) -> List[Dict]:
        """Extract event data from Eventbrite's rendered JS event cards."""
        events = []

        # Try multiple card selectors Eventbrite has used over time
        cards = (
            soup.select("[data-testid='event-card']")
            or soup.select("[data-testid*='event']")
            or soup.select(".event-card")
            or soup.select("[class*='eventCard']")
            or soup.select("[class*='SearchResultEvent']")
            or soup.select("article")
        )

        logger.debug(f"[{self.source_name}] Found {len(cards)} potential event cards")

        for card in cards[:40]:
            event = self._parse_eventbrite_card(card)
            if event:
                events.append(event)

        # Last resort: pull event links from page
        if not events:
            events = self._extract_event_links(soup)

        return events

    def _parse_eventbrite_card(self, card) -> Optional[Dict]:
        """Parse a single Eventbrite event card."""
        # Name
        name_el = (
            card.select_one("[data-testid='event-title']")
            or card.select_one("h2, h3")
            or card.select_one("[class*='title']")
            or card.select_one("[class*='name']")
        )
        if not name_el:
            return None
        name = name_el.get_text(strip=True)
        if not name or len(name) < 5:
            return None

        # URL
        link_el = card.find("a", href=True)
        url = ""
        if link_el:
            href = link_el["href"]
            url = href if href.startswith("http") else "https://www.eventbrite.com" + href

        # Date: look for time[datetime] or aria-label with date
        date_str, time_str = "", ""
        time_el = card.select_one("time[datetime]")
        if time_el:
            raw = time_el.get("datetime", "")
            date_str, time_str = _parse_iso_datetime(raw)

        if not date_str:
            # Try any element whose class contains 'date'
            date_el = card.select_one("[class*='date'], [class*='Date']")
            if date_el:
                raw_text = date_el.get_text(strip=True)
                date_str = BaseScraper.parse_date_flexible(raw_text)

        # Venue
        venue_el = (
            card.select_one("[data-testid='venue-name']")
            or card.select_one("[class*='venue']")
            or card.select_one("[class*='location']")
        )
        venue = venue_el.get_text(strip=True) if venue_el else "Tulsa, OK"

        # Description / summary
        desc_el = card.select_one("p, [class*='description'], [class*='summary']")
        description = desc_el.get_text(strip=True)[:500] if desc_el else ""

        return self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue=venue,
            description=description,
            url=url,
            priority=self.PRIORITY,
        )

    def _extract_event_links(self, soup) -> List[Dict]:
        """Last resort: grab event URLs directly from the page."""
        events = []
        seen = set()
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)
            if (
                "eventbrite.com/e/" in href
                and text
                and len(text) > 10
                and text not in seen
            ):
                seen.add(text)
                events.append(self.make_event(
                    name=text,
                    date="",
                    url=href.split("?")[0],
                    priority=self.PRIORITY,
                ))
        return events


class VisitTulsaScraper(PlaywrightBaseScraper):
    """Visit Tulsa events calendar -- filter for LGBTQ-relevant events."""

    source_name = "visit_tulsa"
    BASE_URL = "https://www.visittulsa.com"
    EVENTS_URL = "https://www.visittulsa.com/events/"
    PRIORITY = 3

    def scrape(self) -> List[Dict]:
        html = self.fetch_page_js(
            self.EVENTS_URL,
            wait_for_selector=(
                ".event-card, .tribe-events-calendar-list__event, "
                "[class*='event'], article"
            ),
            timeout=20000,
        )
        if not html:
            logger.warning(f"[{self.source_name}] No HTML returned from Playwright")
            return []

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        events = self._extract_json_ld_from_soup(soup, "Visit Tulsa", self.PRIORITY)
        if not events:
            events = self._extract_generic_events(soup)

        # Filter: only keep LGBTQ-relevant events
        before = len(events)
        events = [e for e in events if _is_lgbtq_relevant(e.get("name", ""), e.get("description", ""))]
        logger.info(f"[{self.source_name}] {before} total, {len(events)} LGBTQ-relevant kept")
        return events

    def _extract_generic_events(self, soup) -> List[Dict]:
        """Generic event card parser for Visit Tulsa's JS-rendered layout."""
        containers = (
            soup.select(".event-card")
            or soup.select(".tribe-events-calendar-list__event")
            or soup.select(".type-tribe_events")
            or soup.select("[class*='event-card']")
            or soup.select("article")
        )

        events = []
        for container in containers[:40]:
            name_el = container.select_one("h1, h2, h3, h4, [class*='title']")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 5:
                continue

            link_el = container.find("a", href=True)
            url = ""
            if link_el:
                href = link_el["href"]
                url = href if href.startswith("http") else self.BASE_URL + href

            time_el = container.select_one("time[datetime]")
            date_str, time_str = "", ""
            if time_el:
                raw = time_el.get("datetime", "")
                date_str, time_str = _parse_iso_datetime(raw)

            if not date_str:
                date_el = container.select_one("[class*='date']")
                if date_el:
                    date_str = BaseScraper.parse_date_flexible(date_el.get_text(strip=True))

            desc_el = container.select_one("p, [class*='description'], [class*='excerpt']")
            description = desc_el.get_text(strip=True)[:500] if desc_el else ""

            events.append(self.make_event(
                name=name,
                date=date_str,
                time=time_str,
                venue="Tulsa, OK",
                description=description,
                url=url,
                priority=self.PRIORITY,
            ))

        return events


class CircleCinemaScraper(PlaywrightBaseScraper):
    """Circle Cinema -- independent art-house cinema in Tulsa.

    JS-rendered React app. Tries JSON-LD first, then generic event containers.
    LGBTQ filter applied: only keeps queer-relevant films and events.
    """

    source_name = "circle_cinema"
    BASE_URL = "https://www.circlecinema.org"
    DEFAULT_VENUE = "Circle Cinema, 10 S Lewis Ave, Tulsa"
    PRIORITY = 2

    URLS_TO_TRY = [
        "https://www.circlecinema.org/",
        "https://www.circlecinema.org/movies",
        "https://www.circlecinema.org/events",
        "https://www.circlecinema.org/schedule",
    ]

    def scrape(self) -> List[Dict]:
        from bs4 import BeautifulSoup
        all_events = []

        for url in self.URLS_TO_TRY:
            html = self.fetch_page_js(
                url,
                wait_for_selector="[class*='movie'], [class*='event'], [class*='film'], article, h2",
                timeout=20000,
            )
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")

            # Try JSON-LD
            events = self._extract_json_ld_from_soup(soup, self.DEFAULT_VENUE, self.PRIORITY)

            # Generic fallback
            if not events:
                containers = (
                    soup.select("[class*='event']")
                    or soup.select("[class*='movie']")
                    or soup.select("[class*='film']")
                    or soup.select("article")
                )
                for container in containers[:30]:
                    name_el = container.select_one("h1, h2, h3, h4, [class*='title']")
                    if not name_el:
                        continue
                    name = name_el.get_text(strip=True)
                    if not name or len(name) < 5:
                        continue
                    link_el = container.find("a", href=True)
                    url_ev = ""
                    if link_el:
                        href = link_el["href"]
                        url_ev = href if href.startswith("http") else self.BASE_URL + href
                    time_el = container.select_one("time[datetime]")
                    date_str, time_str = "", ""
                    if time_el:
                        date_str, time_str = _parse_iso_datetime(time_el.get("datetime", ""))
                    desc_el = container.select_one("p, [class*='description']")
                    description = desc_el.get_text(strip=True)[:500] if desc_el else ""
                    events.append(self.make_event(
                        name=name, date=date_str, time=time_str,
                        venue=self.DEFAULT_VENUE, description=description,
                        url=url_ev, priority=self.PRIORITY,
                    ))

            if events:
                all_events.extend(events)
                break  # Don't hit more URLs if we found something

        # Filter to LGBTQ-relevant only
        before = len(all_events)
        all_events = [e for e in all_events if _is_lgbtq_relevant(e.get("name", ""), e.get("description", ""))]
        logger.info(f"[{self.source_name}] {before} total, {len(all_events)} LGBTQ-relevant")
        return all_events


class PhilbrookMuseumScraper(PlaywrightBaseScraper):
    """Philbrook Museum of Art -- JS-rendered events calendar.

    Philbrook regularly hosts LGBTQ events (Pride nights, queer artist exhibitions).
    Filter applied: only keeps queer-relevant events.
    """

    source_name = "philbrook_museum"
    BASE_URL = "https://www.philbrook.org"
    DEFAULT_VENUE = "Philbrook Museum of Art, 2727 S Rockford Rd, Tulsa"
    PRIORITY = 2

    def scrape(self) -> List[Dict]:
        from bs4 import BeautifulSoup
        html = self.fetch_page_js(
            "https://www.philbrook.org/calendar",
            wait_for_selector="[class*='event'], article, [class*='card']",
            timeout=20000,
        )
        if not html:
            logger.warning(f"[{self.source_name}] No HTML returned")
            return []

        soup = BeautifulSoup(html, "html.parser")

        events = self._extract_json_ld_from_soup(soup, self.DEFAULT_VENUE, self.PRIORITY)
        if not events:
            containers = (
                soup.select("[class*='event-card']")
                or soup.select("[class*='eventCard']")
                or soup.select("[class*='event']")
                or soup.select("article")
            )
            for container in containers[:30]:
                name_el = container.select_one("h1, h2, h3, h4, [class*='title']")
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                if not name or len(name) < 5:
                    continue
                link_el = container.find("a", href=True)
                url = ""
                if link_el:
                    href = link_el["href"]
                    url = href if href.startswith("http") else self.BASE_URL + href
                time_el = container.select_one("time[datetime]")
                date_str, time_str = "", ""
                if time_el:
                    date_str, time_str = _parse_iso_datetime(time_el.get("datetime", ""))
                desc_el = container.select_one("p, [class*='description']")
                description = desc_el.get_text(strip=True)[:500] if desc_el else ""
                events.append(self.make_event(
                    name=name, date=date_str, time=time_str,
                    venue=self.DEFAULT_VENUE, description=description,
                    url=url, priority=self.PRIORITY,
                ))

        # Filter to LGBTQ-relevant only
        before = len(events)
        events = [e for e in events if _is_lgbtq_relevant(e.get("name", ""), e.get("description", ""))]
        logger.info(f"[{self.source_name}] {before} total, {len(events)} LGBTQ-relevant")
        return events


class OKEQPlaywrightScraper(PlaywrightBaseScraper):
    """OKEQ calendar -- uses Playwright to handle JS rendering.

    NOTE: okeq.org is a PUBLIC website. The old requests-based scraper failed
    because it couldn't execute JavaScript. Playwright handles it fine.
    Primary URL is /events/, fallback is /calendar/.
    """

    source_name = "okeq_calendar"
    BASE_URL = "https://okeq.org"
    DEFAULT_VENUE = "Dennis R. Neill Equality Center, 621 E 4th St"
    PRIORITY = 1

    URLS_TO_TRY = [
        "https://okeq.org/events/",
        "https://okeq.org/calendar/",
        "https://okeq.org/event-calendar/",
    ]

    def scrape(self) -> List[Dict]:
        for url in self.URLS_TO_TRY:
            html = self.fetch_page_js(
                url,
                wait_for_selector=(
                    ".tribe-events-calendar, .tribe-event, "
                    ".tribe-events-calendar-list__event, "
                    ".eventlist-event, .summary-item, "
                    "[class*='tribe-event'], [class*='eventlist']"
                ),
                timeout=25000,
            )
            if not html:
                logger.debug(f"[{self.source_name}] No HTML from {url}, trying next")
                continue

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # Skip 404 pages
            title_el = soup.find("title")
            page_title = title_el.get_text(strip=True).lower() if title_el else ""
            if "404" in page_title or "not found" in page_title:
                logger.debug(f"[{self.source_name}] 404 at {url}, trying next")
                continue

            # Check for a hard login wall (presence of login form)
            if soup.select_one("form[action*='login'], input[name='password']"):
                logger.warning(f"[{self.source_name}] Login wall detected at {url} -- trying next")
                continue

            events = self._extract_json_ld_from_soup(soup, self.DEFAULT_VENUE, self.PRIORITY)
            if not events:
                events = self._extract_tribe_events(soup)
            if not events:
                events = self._extract_squarespace_html(html, self.BASE_URL, self.DEFAULT_VENUE, self.PRIORITY)

            if events:
                logger.info(f"[{self.source_name}] Found {len(events)} events at {url}")
                return events

            logger.debug(f"[{self.source_name}] No events parsed from {url}, trying next")

        logger.warning(f"[{self.source_name}] No events found across all URLs")
        return []

    def _extract_tribe_events(self, soup) -> List[Dict]:
        """Try The Events Calendar (tribe) plugin patterns."""
        containers = (
            soup.select(".tribe-events-calendar-list__event")
            or soup.select(".tribe-event")
            or soup.select(".tribe-events-list-event")
            or soup.select(".type-tribe_events")
        )
        events = []
        for container in containers[:30]:
            name_el = (
                container.select_one(".tribe-events-calendar-list__event-title a")
                or container.select_one(".tribe-events-calendar-list__event-title")
                or container.select_one(".tribe-event-url")
                or container.select_one("h2, h3")
            )
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 3:
                continue

            link_el = name_el if name_el.name == "a" else name_el.find("a")
            url = ""
            if link_el and link_el.get("href"):
                href = link_el["href"]
                url = href if href.startswith("http") else self.BASE_URL + href

            time_el = container.select_one("time[datetime]")
            date_str, time_str = "", ""
            if time_el:
                raw = time_el.get("datetime", "")
                date_str, time_str = _parse_iso_datetime(raw)

            events.append(self.make_event(
                name=name,
                date=date_str,
                time=time_str,
                venue=self.DEFAULT_VENUE,
                url=url,
                priority=self.PRIORITY,
            ))
        return events


# ── Module-level entry point ───────────────────────────────────────────────────

_PLAYWRIGHT_SCRAPERS = [
    FreedomOklahomaScraper,
    TwistedArtsScraper,
    BlackQueerTulsaScraper,
    AllSoulsScraper,
    EventbriteJSScraper,
    VisitTulsaScraper,
    OKEQPlaywrightScraper,
    CircleCinemaScraper,
    PhilbrookMuseumScraper,
]


def scrape_all() -> List[Dict]:
    """Run all Playwright scrapers and return the combined event list.

    Each scraper is run independently so a single failure doesn't abort the rest.
    Only events within the current Mon-Sun week are returned.
    """
    all_events = []

    for scraper_cls in _PLAYWRIGHT_SCRAPERS:
        scraper = scraper_cls()
        try:
            events = scraper.safe_scrape()
            # Only pass events that have dates AND are in the current week.
            # Undated events are excluded here — they offer no scheduling value.
            week_events = [e for e in events if e.get("date") and _is_in_current_week(e.get("date", ""))]
            logger.info(
                f"[playwright_scrapers] {scraper.source_name}: "
                f"{len(events)} total, {len(week_events)} in current week (with dates)"
            )
            all_events.extend(week_events)
        except Exception as e:
            logger.error(f"[playwright_scrapers] {scraper_cls.__name__} crashed: {e}", exc_info=True)

    return all_events


# ── Standalone test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    monday, sunday = _get_week_range()
    print(f"\nPlaywright Scrapers -- Current week: {monday.date()} to {sunday.date()}")
    print("=" * 70)

    results = scrape_all()

    print(f"\n{'='*70}")
    print(f"TOTAL EVENTS IN CURRENT WEEK: {len(results)}")
    print(f"{'='*70}")

    by_source = {}
    for e in results:
        src = e.get("source", "unknown")
        by_source.setdefault(src, []).append(e)

    for src, evts in sorted(by_source.items()):
        print(f"\n[{src.upper()}] -- {len(evts)} events")
        for e in evts:
            date_str = e.get("date", "NO DATE")
            time_str = e.get("time", "")
            name = e.get("name", "?")
            venue = e.get("venue", "")
            when = f"{date_str} {time_str}".strip()
            print(f"  {when:25s} | {name[:50]:50s} | {venue[:30]}")

    if not results:
        print("\nNo events found this week. This may mean:")
        print("  - No events are scheduled Apr 6-12, 2026")
        print("  - Sites have changed their HTML structure")
        print("  - Network timeouts hit (check logs above)")
