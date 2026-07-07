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
from scraper.relevance import compile_lgbtq_keywords

logger = logging.getLogger(__name__)

# ── LGBTQ keyword filter ───────────────────────────────────────────────────────

LGBTQ_KEYWORDS = [
    # Explicit identity
    "lgbtq", "queer", "gay", "lesbian", "bi", "trans", "drag", "pride",
    "rainbow", "dyke", "nonbinary", "non-binary", "gender", "equality",
    "affirming", "inclusive", "homo", "sapphic", "two-spirit", "twospirit",
    # Queer-adjacent / community-coded
    "oddities", "curiosities",
    "burlesque", "cabaret",
    "feminist", "radical",
    "night market", "art market", "bazaar", "market",
    "wiz",
    "greenwood", "black wall street",
    "boots riley",
    # Cultural event types
    "screening", "film festival", "documentary",
    "exhibition", "opening reception", "art opening",
    "workshop", "panel discussion", "panel", "lecture",
    "fundraiser", "benefit show", "benefit concert",
    "cultural festival", "heritage",
    "open mic", "poetry",
]


_LGBTQ_RX = compile_lgbtq_keywords(LGBTQ_KEYWORDS)


def _is_lgbtq_relevant(name: str, description: str = "") -> bool:
    combined = (name + " " + description).lower()
    return bool(_LGBTQ_RX.search(combined))


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


class TulsaArtistFellowshipScraper(PlaywrightBaseScraper):
    """Tulsa Artist Fellowship -- Flagship space + main calendar (Squarespace, JS-rendered).

    Flagship (112 N Boston Ave) hosts screenings, panels, lectures, artist talks,
    workshops, performances, and radical cultural programming. No LGBTQ filter —
    TAF is a trusted arts community venue; all events are relevant.
    """

    source_name = "tulsa_artist_fellowship"
    BASE_URL = "https://www.tulsaartistfellowship.org"
    EVENTS_URL = "https://www.tulsaartistfellowship.org/calendar"
    DEFAULT_VENUE = "Flagship / Tulsa Artist Fellowship, 112 N Boston Ave"
    PRIORITY = 2

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
        # No LGBTQ filter — Flagship programs screenings, lectures, radical cultural events;
        # queer Tulsans are in that audience.
        logger.info(f"[{self.source_name}] Found {len(events)} events (all kept, no filter)")
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

    circlecinema.org itself is a Wix React shell with NO scrapable schedule:
    /movies, /events and /schedule all render the Wix 404 page, JSON-LD is only
    WebSite/LocalBusiness, and the wix-warmup-data blob resolves titles to image
    filenames. The real film schedule lives on the Easy-Ware ticketing portal
    (circlecinema.easy-ware-ticketing.com), which is a Blazor Server app: data
    arrives over a SignalR WebSocket, so there is no JSON XHR to consume -- the
    rendered DOM is the API. (Diagnosed 2026-07-06.)

    Strategy: load the /events grid (#eventGrid .prodCard) and read each film's
    visible showtimes straight off the card (.prodPerfItem). The grid truncates
    to 5 showtimes behind a "More..." button, which is a Blazor client-side
    route to /eventsByMovie/<id> carrying the synopsis (.movieSynopsis) and the
    FULL showtime list (.perfCard -> .dayTitle "Monday July 6" + .timeTitle
    "3:20 PM") -- films with "More..." get that visit. For the rest, the
    "More Info" button opens a Blazored.Modal dialog (.bm-container) whose
    .synopsis div supplies the description; it only closes via its
    button.bm-close (Escape does nothing). Emits one event per film per date
    with that day's remaining showtimes in the description. LGBTQ filter
    applied on name + synopsis: only queer-relevant films kept.

    NOTE: Blazor re-renders the DOM on every interaction, so element handles go
    stale after any click -- always re-query via locators, never cache handles.
    """

    source_name = "circle_cinema"
    BASE_URL = "https://www.circlecinema.org"
    TICKETING_URL = "https://circlecinema.easy-ware-ticketing.com/events"
    DEFAULT_VENUE = "Circle Cinema, 10 S Lewis Ave, Tulsa"
    PRIORITY = 2
    MAX_FILMS = 60  # safety cap on detail-page visits

    # Film synopses (Fandango copy) often describe queer romance without any
    # identity keyword -- "Sonya, unfamiliar with dating girls..." carries zero
    # LGBTQ_KEYWORDS hits. These phrases supplement the shared list for
    # synopsis text specifically.
    SYNOPSIS_LGBTQ_PHRASES = [
        "coming out", "same-sex", "same sex", "dating girls", "dating boys",
        "her girlfriend", "his boyfriend", "gender identity",
    ]
    _FILM_RX = compile_lgbtq_keywords(LGBTQ_KEYWORDS + SYNOPSIS_LGBTQ_PHRASES)

    def _film_is_lgbtq(self, title: str, synopsis: str) -> bool:
        """_is_lgbtq_relevant plus the synopsis-phrase supplements, checked
        against the FULL synopsis rather than the truncated event description."""
        combined = f"{title} {synopsis}".lower()
        return bool(self._FILM_RX.search(combined))

    _MONTH_NUM = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    def _parse_month_day(self, text: str) -> str:
        """Parse 'Jul 6' / 'Monday July 6' -> YYYY-MM-DD (year inferred).

        The ticketing site never shows a year. Showtimes are always current or
        upcoming, so a parsed date landing >60 days in the past means the
        listing has wrapped into the next calendar year (Dec -> Jan)."""
        import re as _re
        m = _re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*$", (text or "").strip())
        if not m:
            return ""
        month = self._MONTH_NUM.get(m.group(1)[:3].lower())
        day = int(m.group(2))
        if not month:
            return ""
        today = datetime.now()
        try:
            dt = datetime(today.year, month, day)
        except ValueError:
            return ""
        if (dt - today).days < -60:
            dt = datetime(today.year + 1, month, day)
        return dt.strftime("%Y-%m-%d")

    @staticmethod
    def _time_sort_key(t: str):
        try:
            return datetime.strptime(t.strip(), "%I:%M %p")
        except ValueError:
            return datetime.max

    def _wait_for_grid(self, page):
        page.wait_for_selector("#eventGrid .prodCard .prodTitle", timeout=30000)
        page.wait_for_timeout(1200)  # let the Blazor circuit finish streaming

    def _reset_to_grid(self, page):
        page.goto(self.TICKETING_URL, wait_until="domcontentloaded", timeout=45000)
        self._wait_for_grid(page)

    def _parse_card_showtimes(self, card) -> List:
        """Parse a grid card's visible .prodPerfItem rows into (date, time) pairs."""
        import re as _re
        showtimes = []
        for item in card.locator(".prodPerfItem").all():
            text = item.inner_text().replace("\xa0", " ")
            m = _re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*-\s*(\d{1,2}:\d{2}\s*[AP]M)", text)
            if not m:
                continue
            date_str = self._parse_month_day(f"{m.group(1)} {m.group(2)}")
            if date_str:
                showtimes.append((date_str, m.group(3).strip()))
        return showtimes

    def _full_showtimes_via_detail(self, page, index: int) -> Optional[Dict]:
        """Click film #index's 'More...' -> /eventsByMovie/<id>; return synopsis, url, full showtimes."""
        import re as _re
        card = page.locator("#eventGrid .prodCard").nth(index)
        card.locator("button", has_text=_re.compile(r"^\s*More\.\.\.\s*$")).first.click(timeout=8000)
        page.wait_for_url("**/eventsByMovie/**", timeout=15000)
        page.wait_for_selector(".perfCard", timeout=15000)
        page.wait_for_timeout(600)
        detail_url = page.url

        synopsis = ""
        syn_loc = page.locator(".movieSynopsis")
        if syn_loc.count():
            synopsis = _re.sub(r"^\s*Synopsis\s*", "", syn_loc.first.inner_text(), flags=_re.I)
            synopsis = " ".join(synopsis.split())

        showtimes = []  # list of (YYYY-MM-DD, "3:20 PM")
        for pc in page.locator(".perfCard").all():
            day_loc = pc.locator(".dayTitle")
            time_loc = pc.locator(".timeTitle")
            if not day_loc.count() or not time_loc.count():
                continue
            date_str = self._parse_month_day(day_loc.first.inner_text())
            time_str = time_loc.first.inner_text().strip()
            if date_str and time_str:
                showtimes.append((date_str, time_str))

        self._reset_to_grid(page)
        return {"synopsis": synopsis, "url": detail_url, "showtimes": showtimes}

    def _synopsis_via_modal(self, page, index: int) -> str:
        """Click film #index's 'More Info' -> Blazored.Modal; read .synopsis and close it."""
        card = page.locator("#eventGrid .prodCard").nth(index)
        card.locator("button.btnDetails").first.click(timeout=8000)
        page.wait_for_selector(".bm-container .synopsis", timeout=10000)
        synopsis = " ".join(page.locator(".bm-container .synopsis").first.inner_text().split())
        try:
            page.locator(".bm-container button.bm-close").first.click(timeout=4000)
            page.wait_for_selector(".bm-container", state="detached", timeout=5000)
        except Exception:
            self._reset_to_grid(page)  # stuck modal blocks every later click
        return synopsis

    def scrape(self) -> List[Dict]:
        if not self._browser:
            logger.error(f"[{self.source_name}] Browser not started")
            return []

        _, sunday = _get_week_range()
        week_end = sunday.strftime("%Y-%m-%d")

        context = self._browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
            locale="en-US",
        )
        films = []
        try:
            import re as _re
            page = context.new_page()
            self._reset_to_grid(page)

            # Pre-scan the grid: title + visible showtimes + truncation flag per
            # card. Grid showtimes are chronological, so if a film's FIRST
            # visible showtime is already past this week's Sunday, every
            # showtime is -- skip it entirely.
            cards = page.locator("#eventGrid .prodCard")
            plan = []
            for i in range(min(cards.count(), self.MAX_FILMS)):
                card = cards.nth(i)
                title_loc = card.locator(".prodTitle")
                if not title_loc.count():
                    continue
                title = title_loc.first.inner_text().strip()
                if not title:
                    continue
                showtimes = self._parse_card_showtimes(card)
                if not showtimes or showtimes[0][0] > week_end:
                    continue
                has_more = card.locator(
                    "button", has_text=_re.compile(r"^\s*More\.\.\.\s*$")).count() > 0
                plan.append({"index": i, "title": title,
                             "showtimes": showtimes, "has_more": has_more})
            logger.info(f"[{self.source_name}] {cards.count()} films on grid, "
                        f"{len(plan)} start within current week")

            for film in plan:
                synopsis, url = "", self.TICKETING_URL
                try:
                    if film["has_more"]:
                        detail = self._full_showtimes_via_detail(page, film["index"])
                        synopsis = detail["synopsis"]
                        url = detail["url"]
                        if detail["showtimes"]:
                            film["showtimes"] = detail["showtimes"]
                    else:
                        synopsis = self._synopsis_via_modal(page, film["index"])
                except Exception as e:
                    logger.warning(f"[{self.source_name}] detail/modal failed for "
                                   f"'{film['title']}': {e}")
                    try:
                        self._reset_to_grid(page)  # never leave a modal/detail page open
                    except Exception:
                        pass
                films.append({"title": film["title"], "synopsis": synopsis,
                              "url": url, "showtimes": film["showtimes"]})
        finally:
            try:
                context.close()
            except Exception:
                pass

        # Filter to LGBTQ/community-relevant films on the FULL synopsis, then
        # emit one event per film per date with that day's showtimes listed.
        kept = [f for f in films if self._film_is_lgbtq(f["title"], f["synopsis"])]
        logger.info(f"[{self.source_name}] {len(films)} films scraped, "
                    f"{len(kept)} LGBTQ/community-relevant")
        all_events = []
        for film in kept:
            by_date = {}
            for date_str, time_str in film["showtimes"]:
                by_date.setdefault(date_str, []).append(time_str)
            for date_str, times in sorted(by_date.items()):
                times = sorted(set(times), key=self._time_sort_key)
                description = film["synopsis"][:400]
                if len(times) > 1:
                    description = (description + " Showtimes: " + ", ".join(times)).strip()
                all_events.append(self.make_event(
                    name=film["title"], date=date_str, time=times[0],
                    venue=self.DEFAULT_VENUE, description=description,
                    url=film["url"], priority=self.PRIORITY,
                ))

        logger.info(f"[{self.source_name}] {len(all_events)} events emitted")
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
            # 2026-07-06: Philbrook's Webflow calendar has NO time[datetime] —
            # dates are plain text ("Jul 8, 2026" in .event-date, "9:30 am" in
            # .event-time). The old ISO-only parse produced 18 undated events
            # every run, all silently dropped by the week filter. Nested
            # [class*='event'] matches also duplicated every card, so dedupe
            # by (name, date).
            containers = (
                soup.select("[class*='events-item']")
                or soup.select("[class*='event-card']")
                or soup.select("[class*='eventCard']")
                or soup.select("[class*='event']")
                or soup.select("article")
            )
            seen = set()
            for container in containers[:60]:
                name_el = container.select_one(
                    "[class*='event-card-title'], h1, h2, h3, h4, [class*='title']")
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
                date_str, time_str = "", ""
                time_el = container.select_one("time[datetime]")
                if time_el:
                    date_str, time_str = _parse_iso_datetime(time_el.get("datetime", ""))
                if not date_str:
                    date_el = container.select_one("[class*='event-date']")
                    if date_el:
                        parsed = self.parse_date_flexible(date_el.get_text(strip=True))
                        if parsed and re.match(r"\d{4}-\d{2}-\d{2}", parsed):
                            date_str = parsed[:10]
                if not time_str:
                    t_el = container.select_one("[class*='event-time']")
                    if t_el:
                        time_str = t_el.get_text(strip=True)[:20]
                key = (name.lower(), date_str)
                if key in seen:
                    continue
                seen.add(key)
                desc_el = container.select_one("p, [class*='description']")
                description = desc_el.get_text(strip=True)[:500] if desc_el else ""
                events.append(self.make_event(
                    name=name, date=date_str, time=time_str,
                    venue=self.DEFAULT_VENUE, description=description,
                    url=url, priority=self.PRIORITY,
                ))

        # No strict LGBTQ filter — Philbrook is a known queer-welcoming institution
        # (hosts Pride nights, queer artist exhibitions, inclusive programming).
        # Major art openings and community events are relevant to our audience.
        logger.info(f"[{self.source_name}] {len(events)} events (all kept, no filter)")
        return events


class WOMPAScraper(PlaywrightBaseScraper):
    """WOMPA - Event Venue & Creative Community, Tulsa.

    URL is a Wix-hosted JS app (app.wompatulsa.com) — requires Playwright.
    WOMPA is a trusted community venue; ALL events are returned (no LGBTQ filter).
    """

    source_name = "wompa_tulsa"
    BASE_URL = "https://wompatulsa.com"
    EVENTS_URL = "https://app.wompatulsa.com/events-1/c/0"
    DEFAULT_VENUE = "WOMPA, 108 N Boston Ave, Tulsa"
    PRIORITY = 1

    # WOMPA's site (app.wompatulsa.com) is a GoodBarber app, NOT Wix. Events are
    # served as JSON from the GoodBarber content API — far more reliable than
    # scraping the JS-rendered DOM (the old Wix selectors never matched and the
    # scraper silently returned 0 even when events existed). App id + events
    # section id were extracted from the page's gb-app-state blob.
    GOODBARBER_APP_ID = "3682793"
    GOODBARBER_EVENTS_SECTION = "60857482"
    GOODBARBER_API = (
        "https://api.goodbarber.net/front/get_items/"
        "{app}/{section}/?category_index=0"
    )

    def scrape(self) -> List[Dict]:
        """Fetch WOMPA events from the GoodBarber JSON API (with DOM fallback)."""
        import requests as _requests
        import html as _html
        import re as _re
        from datetime import datetime, timezone

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/134.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }
        url = self.GOODBARBER_API.format(
            app=self.GOODBARBER_APP_ID, section=self.GOODBARBER_EVENTS_SECTION
        )
        raw_items: List[Dict] = []
        pages = 0
        try:
            while url and pages < 5:
                resp = _requests.get(url, headers=headers, timeout=20)
                if resp.status_code != 200:
                    logger.warning(
                        f"[{self.source_name}] GoodBarber API status "
                        f"{resp.status_code} for {url}"
                    )
                    break
                data = resp.json()
                items = data.get("items") or []
                raw_items.extend(items)
                pages += 1
                url = data.get("next_page") if items else None
        except Exception as e:
            logger.error(
                f"[{self.source_name}] GoodBarber API failed ({e}); "
                "falling back to DOM scrape"
            )
            return self._scrape_dom_fallback()

        if not raw_items:
            logger.info(
                f"[{self.source_name}] GoodBarber events section empty "
                "(0 items); WOMPA has no events posted right now"
            )
            return []

        logger.debug(
            f"[{self.source_name}] GoodBarber first-item keys: "
            f"{list(raw_items[0].keys())}"
        )

        def _strip(s) -> str:
            return _html.unescape(_re.sub(r"<[^>]+>", " ", str(s or ""))).strip()

        def _gb_date(val):
            """GoodBarber dates: unix ts (s or ms) or ISO string -> (date, time)."""
            if val in (None, "", 0, "0"):
                return "", ""
            try:
                iv = int(float(val))
                if iv > 10_000_000_000:  # milliseconds -> seconds
                    iv //= 1000
                dt = datetime.fromtimestamp(iv, tz=timezone.utc)
                return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
            except (ValueError, TypeError):
                s = str(val)
                if "T" in s:
                    return _parse_iso_datetime(s)
                return BaseScraper.parse_date_flexible(s), ""

        events: List[Dict] = []
        for it in raw_items:
            name = _strip(it.get("title") or it.get("name"))
            if not name or len(name) < 3:
                continue

            date_str, time_str = "", ""
            for dk in ("startDate", "start_date", "date", "start",
                       "beginDate", "timestamp", "when"):
                if it.get(dk):
                    date_str, time_str = _gb_date(it.get(dk))
                    if date_str:
                        break

            venue = (it.get("placeName") or it.get("place_name")
                     or it.get("address") or it.get("location"))
            if isinstance(venue, dict):
                venue = venue.get("address") or venue.get("name")
            venue = _strip(venue) or self.DEFAULT_VENUE

            description = _strip(
                it.get("text") or it.get("content")
                or it.get("subtitle") or it.get("description")
            )[:500]

            url_ = it.get("url") or it.get("link") or ""
            if url_ and not str(url_).startswith("http"):
                url_ = self.BASE_URL + str(url_)

            events.append(self.make_event(
                name=name,
                date=date_str,
                time=time_str,
                venue=venue,
                description=description,
                url=url_,
                priority=self.PRIORITY,
            ))

        # No LGBTQ filter — WOMPA is a trusted community venue, all events relevant
        logger.info(
            f"[{self.source_name}] Found {len(events)} events via "
            "GoodBarber API (no filter applied)"
        )
        return events

    def _scrape_dom_fallback(self) -> List[Dict]:
        """Legacy DOM scrape (kept as a fallback if the API path fails)."""
        from bs4 import BeautifulSoup

        html = self.fetch_page_js(
            self.EVENTS_URL,
            wait_for_selector=(
                "[data-hook='events-widget-event-card'], "
                "[data-hook='list-item'], "
                "[class*='eventsGallery'], "
                "[class*='event-list'], "
                "article, [class*='event']"
            ),
            timeout=25000,
        )
        if not html:
            logger.warning(f"[{self.source_name}] No HTML returned from Playwright")
            return []

        soup = BeautifulSoup(html, "html.parser")

        # Try JSON-LD first
        events = self._extract_json_ld_from_soup(soup, self.DEFAULT_VENUE, self.PRIORITY)
        if events:
            logger.info(f"[{self.source_name}] JSON-LD: {len(events)} events")
            return events

        # Wix Events widget selectors (Wix has changed these over time — try all)
        containers = (
            soup.select("[data-hook='events-widget-event-card']")
            or soup.select("[data-hook='list-item']")
            or soup.select("[class*='evGallery-item']")
            or soup.select("[class*='evWidget-item']")
            or soup.select("[class*='event-list-item']")
            or soup.select("[class*='eventCard']")
            or soup.select("article[class*='event']")
            or soup.select("li[class*='event']")
        )

        logger.debug(f"[{self.source_name}] Found {len(containers)} candidate containers")

        for container in containers[:30]:
            name_el = container.select_one(
                "h1, h2, h3, h4, "
                "[data-hook='event-title'], "
                "[class*='title'], "
                "[class*='name']"
            )
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 4:
                continue

            link_el = container.find("a", href=True)
            url = ""
            if link_el:
                href = link_el["href"]
                url = href if href.startswith("http") else self.BASE_URL + href

            date_str, time_str = "", ""
            time_el = container.select_one(
                "time[datetime], "
                "[data-hook='event-scheduled-date'], "
                "[class*='date'], "
                "[class*='Date']"
            )
            if time_el:
                raw = time_el.get("datetime", "") or time_el.get_text(strip=True)
                if raw and "T" in raw:
                    date_str, time_str = _parse_iso_datetime(raw)
                else:
                    date_str = BaseScraper.parse_date_flexible(raw)

            desc_el = container.select_one(
                "p, [data-hook='event-description'], [class*='description'], [class*='excerpt']"
            )
            description = desc_el.get_text(strip=True)[:500] if desc_el else ""

            events.append(self.make_event(
                name=name,
                date=date_str,
                time=time_str,
                venue=self.DEFAULT_VENUE,
                description=description,
                url=url,
                priority=self.PRIORITY,
            ))

        # No LGBTQ filter — WOMPA is a trusted community venue, all events relevant
        logger.info(f"[{self.source_name}] Found {len(events)} events (no filter applied)")
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


# ── Flexible venue scraper (Tribe / Squarespace / JSON-LD / Wix) ───────────────

class _FlexibleVenueScraper(PlaywrightBaseScraper):
    """Base class for venues whose CMS we don't know upfront.

    Tries JSON-LD → The Events Calendar (Tribe) → Squarespace → Wix selectors
    against one or more candidate URLs. Subclasses set source_name, BASE_URL,
    URLS_TO_TRY, DEFAULT_VENUE, PRIORITY. No LGBTQ keyword filter — these
    venues are added to LGBTQ_SOURCES so the runner trusts their curation.
    """

    URLS_TO_TRY: List[str] = []
    WAIT_SELECTOR = (
        ".tribe-events-calendar, .tribe-event, "
        ".tribe-events-calendar-list__event, "
        ".eventlist-event, .summary-item, "
        "[data-hook='events-widget-event-card'], "
        "[class*='tribe-event'], [class*='eventlist'], "
        "article, main"
    )

    def scrape(self) -> List[Dict]:
        from bs4 import BeautifulSoup

        for url in self.URLS_TO_TRY:
            html = self.fetch_page_js(url, wait_for_selector=self.WAIT_SELECTOR, timeout=25000)
            if not html:
                logger.debug(f"[{self.source_name}] No HTML from {url}, trying next")
                continue

            soup = BeautifulSoup(html, "html.parser")

            title_el = soup.find("title")
            page_title = title_el.get_text(strip=True).lower() if title_el else ""
            if "404" in page_title or "not found" in page_title:
                logger.debug(f"[{self.source_name}] 404 at {url}, trying next")
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
        """Reuse OKEQPlaywrightScraper's Tribe parser if available; otherwise no-op."""
        try:
            return OKEQPlaywrightScraper._extract_tribe_events(self, soup)
        except Exception:
            return []


class ShambhalaTulsaScraper(_FlexibleVenueScraper):
    """Shambhala Meditation Center of Tulsa — meditation programs, sound baths,
    workshops, retreats. Curated wellness calendar, queer-welcoming community space.
    """
    source_name = "shambhala_tulsa"
    BASE_URL = "https://tulsa.shambhala.org"
    URLS_TO_TRY = [
        "https://tulsa.shambhala.org/events/",
        "https://tulsa.shambhala.org/calendar/",
        "https://tulsa.shambhala.org/programs/",
    ]
    DEFAULT_VENUE = "Shambhala Meditation Center of Tulsa"
    PRIORITY = 2


class BeLoveYogaScraper(_FlexibleVenueScraper):
    """Be Love Yoga Studio (Pearl District / Jenks) — workshops, sound baths,
    kirtan, donation classes, the Big Om Yoga Retreat. Queer-welcoming.
    """
    source_name = "be_love_yoga"
    BASE_URL = "https://beloveyogastudio.com"
    URLS_TO_TRY = [
        "https://beloveyogastudio.com/events/",
        "https://beloveyogastudio.com/workshops/",
        "https://beloveyogastudio.com/calendar/",
    ]
    DEFAULT_VENUE = "Be Love Yoga Studio, Tulsa"
    PRIORITY = 2


class OpenEyeYogaScraper(_FlexibleVenueScraper):
    """Open Eye Yoga (Brookside) — power/restorative/yin/kundalini, Sana sound baths,
    workshops. Queer-welcoming community wellness venue.
    """
    source_name = "open_eye_yoga"
    BASE_URL = "https://www.openeyeyoga.com"
    URLS_TO_TRY = [
        "https://www.openeyeyoga.com/events",
        "https://www.openeyeyoga.com/workshops",
        "https://www.openeyeyoga.com/calendar",
    ]
    DEFAULT_VENUE = "Open Eye Yoga, 4329 S Peoria Ave Suite 350, Tulsa"
    PRIORITY = 2


class YogaQuestScraper(_FlexibleVenueScraper):
    """yogaQuest — Tulsa wellness studio. Workshops and special events."""
    source_name = "yogaquest_tulsa"
    BASE_URL = "https://www.tulsayogaquest.com"
    URLS_TO_TRY = [
        "https://www.tulsayogaquest.com/events",
        "https://www.tulsayogaquest.com/workshops",
        "https://www.tulsayogaquest.com/calendar",
    ]
    DEFAULT_VENUE = "yogaQuest, Tulsa"
    PRIORITY = 2


class SonicRayScraper(_FlexibleVenueScraper):
    """Nicholas Ray Bradford (@thesonicray) — sound bath meditation events
    around Tulsa. Mobile artist; venue varies by event.
    """
    source_name = "the_sonic_ray"
    BASE_URL = "https://thesonicray.com"
    URLS_TO_TRY = [
        "https://thesonicray.com/events",
        "https://thesonicray.com/schedule",
        "https://thesonicray.com/calendar",
        "https://thesonicray.com/",
    ]
    DEFAULT_VENUE = "Various locations, Tulsa (The Sonic Ray)"
    PRIORITY = 2


class UpdogYogaScraper(_FlexibleVenueScraper):
    """Updog Yoga Tulsa (415 E 12th St) — indoor/outdoor yoga, infrared heat,
    hosts Sana Meditation sound baths and other special events.
    """
    source_name = "updog_yoga_tulsa"
    BASE_URL = "https://www.updogyogatulsa.com"
    URLS_TO_TRY = [
        "https://www.updogyogatulsa.com/events",
        "https://www.updogyogatulsa.com/workshops",
        "https://www.updogyogatulsa.com/calendar",
        "https://www.updogyogatulsa.com/class-schedule",
    ]
    DEFAULT_VENUE = "Updog Yoga, 415 E 12th St, Tulsa"
    PRIORITY = 2


class SanaMeditationScraper(_FlexibleVenueScraper):
    """Sana Meditation — Tulsa wellness collective (Sue Webb & Tiffany Tran)
    running immersive sound baths at Fly Loft, Tulsa Botanic Garden, Updog,
    and other community venues.
    """
    source_name = "sana_meditation"
    BASE_URL = "https://sanameditation.com"
    URLS_TO_TRY = [
        "https://sanameditation.com/events",
        "https://sanameditation.com/schedule",
        "https://sanameditation.com/calendar",
        "https://sanameditation.com/",
    ]
    DEFAULT_VENUE = "Various locations, Tulsa (Sana Meditation)"
    PRIORITY = 2


class TulsaYogaMeditationCenterScraper(_FlexibleVenueScraper):
    """Tulsa Yoga Meditation Center (5319 S Sheridan Rd) — yoga, Buddhist
    meditation, Vedic education, Ayurveda, Reiki. Hosts workshops and
    therapeutic classes.
    """
    source_name = "tulsa_yoga_meditation_center"
    BASE_URL = "https://www.tulsayogameditationcenter.com"
    URLS_TO_TRY = [
        "https://www.tulsayogameditationcenter.com/events",
        "https://www.tulsayogameditationcenter.com/workshops",
        "https://www.tulsayogameditationcenter.com/calendar",
        "https://www.tulsayogameditationcenter.com/classes",
    ]
    DEFAULT_VENUE = "Tulsa Yoga Meditation Center, 5319 S Sheridan Rd"
    PRIORITY = 2


class TulsaPeoplesOrchestraScraper(PlaywrightBaseScraper):
    """Tulsa People's Orchestra -- Instagram profile scraper.

    Public Instagram at @tulsapeoplesorchestra. Extracts post captions that
    look like event announcements (brunches, concerts, performances at The Vault
    and other Tulsa venues). Falls back gracefully if Instagram blocks the request.
    """

    source_name = "tulsa_peoples_orchestra"
    PROFILE_URL = "https://www.instagram.com/tulsapeoplesorchestra/"
    DEFAULT_VENUE = "The Vault, Tulsa"
    PRIORITY = 2

    EVENT_KEYWORDS = [
        "brunch", "concert", "performance", "show", "event",
        "join us", "come out", "tickets", "doors open", "live music",
        "tonight", "this week", "upcoming", "the vault",
    ]

    def scrape(self) -> List[Dict]:
        import re
        from bs4 import BeautifulSoup

        html = self.fetch_page_js(
            self.PROFILE_URL,
            wait_for_selector="article, main, [role='main']",
            timeout=20000,
        )
        if not html:
            logger.warning(f"[{self.source_name}] No HTML from Instagram -- may require login")
            return []

        soup = BeautifulSoup(html, "html.parser")

        # Try JSON-LD first
        events = self._extract_json_ld_from_soup(soup, self.DEFAULT_VENUE, self.PRIORITY)
        if events:
            logger.info(f"[{self.source_name}] JSON-LD: {len(events)} events")
            return events

        # Extract post captions from Instagram's embedded JSON in <script> tags
        captions = []
        for script in soup.find_all("script"):
            text = script.string or ""
            if not text:
                continue
            found = re.findall(r'"edge_media_to_caption":\{"edges":\[.*?"text":"([^"]{10,})"', text)
            captions.extend(found)
            found2 = re.findall(r'"caption":"([^"]{10,500})"', text)
            captions.extend(found2)

        events = []
        for caption in captions[:20]:
            caption_clean = caption.replace("\\n", "\n").replace("\\u0026", "&")
            caption_lower = caption_clean.lower()

            if not any(kw in caption_lower for kw in self.EVENT_KEYWORDS):
                continue

            date_str = BaseScraper.parse_date_flexible(caption_clean)
            time_match = re.search(r'\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b', caption_lower)
            time_str = time_match.group(1).upper() if time_match else ""

            venue = "The Vault, Tulsa" if "the vault" in caption_lower else self.DEFAULT_VENUE
            first_line = caption_clean.split("\n")[0].strip()[:80] or "Tulsa People's Orchestra Event"

            events.append(self.make_event(
                name=first_line,
                date=date_str,
                time=time_str,
                venue=venue,
                description=caption_clean[:400],
                url=self.PROFILE_URL,
                priority=self.PRIORITY,
            ))

        logger.info(f"[{self.source_name}] Found {len(events)} event posts from Instagram")
        return events


class GoogleEventsScraper(PlaywrightBaseScraper):
    """Google Events aggregator (headless, no login) — the bulk-up source.

    Google's events panel (ibp=htl;events) aggregates venue + community events
    that individual venue calendars don't expose to scrapers (BOK, Cain's, TPAC,
    Gathering Place, Guthrie Green, markets, comedy, etc.). One query per day of
    the current Mon-Sun week pulls dozens of real Tulsa events. Loosened
    relevance keeps the Tulsa-area ones; the featured selection still floats the
    fun/queer picks; the website lists them all.
    """
    source_name = "google_events"
    PRIORITY = 2
    # English + Spanish: the machine can sit in a Spanish-locale region (PV move
    # 2026-06), and Google then serves the es-MX UI. hl/gl params below force
    # English, but the Spanish terms stay as defense in depth (W28 shipped
    # "Obtener entradas" / "mié" as venues on 41 events).
    _JUNK_HEADINGS = {"all events", "events filters list", "details", "more events",
                      "saved", "feedback", "learn more", "map",
                      "todos los eventos", "detalles", "más eventos", "guardado",
                      "comentarios", "más información", "mapa"}

    def scrape(self) -> List[Dict]:
        from bs4 import BeautifulSoup
        from datetime import datetime, timedelta
        import re as _re
        today = datetime.now().date()
        monday = today - timedelta(days=today.weekday())
        week = [monday + timedelta(days=i) for i in range(7)]
        events, seen = [], set()
        time_rx = _re.compile(
            r'(\d{1,2}(?::\d{2})?\s*(?:[–\-]\s*\d{1,2}(?::\d{2})?)?\s*[AP]M)', _re.I)
        for d in week:
            q = f"events in tulsa {d.strftime('%B')} {d.day} {d.year}"
            # hl/gl pin the UI to English/US regardless of the machine's location
            # (Puerto Vallarta IPs get es-MX otherwise and the button labels
            # "Obtener entradas"/"Detalles" leak into the venue field).
            url = (f"https://www.google.com/search?q={q.replace(' ','+')}"
                   f"&ibp=htl;events&hl=en&gl=US&pws=0")
            html = self.fetch_page_js(url, wait_for_selector=None, timeout=30000)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            dstr = d.strftime("%Y-%m-%d")
            for h in soup.select("div[role='heading']"):
                nm = h.get_text(" ", strip=True)
                if not nm or len(nm) < 6 or nm.lower() in self._JUNK_HEADINGS:
                    continue
                key = (nm.lower()[:40], dstr)
                if key in seen:
                    continue
                # climb to the card container for time/venue
                card = h
                for _ in range(4):
                    if card.parent:
                        card = card.parent
                ctext = card.get_text(" \n ", strip=True)
                tm = ""
                tmatch = time_rx.search(ctext)
                if tmatch:
                    tm = tmatch.group(1).replace("–", "-").upper().replace(" ", " ")
                # Weekday off-by-one guard: Google's panel for one day can carry
                # cards from adjacent days; every heading used to get stamped with
                # the QUERY date, shifting events onto the wrong weekday. If the
                # card itself names a date and it isn't the query day, skip it -
                # the correct day's query picks it up (dedup key is name+date).
                _date_rx = _re.compile(
                    r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})\b', _re.I)
                dm = _date_rx.search(ctext)
                if dm:
                    _mon = ("jan feb mar apr may jun jul aug sep oct nov dec"
                            .split().index(dm.group(1).lower()[:3]) + 1)
                    if (_mon, int(dm.group(2))) != (d.month, d.day):
                        continue
                # venue: a line that isn't the name/date/city/time.
                # Junk lists carry English + Spanish (es-MX UI leak, W28).
                venue = ""
                _btn = ("get tickets", "details", "directions", "save event", "save",
                        "more sources", "more", "official site", "tickets", "share",
                        "see web results", "interested", "going", "from $",
                        "obtener entradas", "entradas", "detalles", "cómo llegar",
                        "como llegar", "guardar", "compartir", "sitio oficial",
                        "más opciones", "me interesa", "asistiré", "desde $")
                # Spanish weekday tokens need a boundary right after (bare 'mar'
                # would block "Marshall Brewing"); English keeps legacy prefix match.
                _wday_rx = _re.compile(
                    r'^(mon|tue|wed|thu|fri|sat|sun|tomorrow|today|\d'
                    r'|(?:lun|mar|mi[eé]|jue|vie|s[aá]b|dom|hoy|ma[ñn]ana)(?:[\s,.:]|$))', _re.I)
                for line in [x.strip() for x in ctext.split("\n") if x.strip()]:
                    low = line.lower()
                    if (line != nm and "tulsa, ok" not in low and not time_rx.fullmatch(line)
                            and not any(b == low or b in low for b in _btn)
                            and not _wday_rx.match(low)
                            and 4 < len(line) < 60 and any(c.isalpha() for c in line)):
                        venue = line
                        break
                seen.add(key)
                events.append(self.make_event(
                    name=nm, date=dstr, time=tm, venue=venue or "Tulsa, OK",
                    description="", url=url, priority=self.PRIORITY,
                ))
        logger.info(f"[{self.source_name}] {len(events)} events across the week")
        return events


class VanguardScraper(PlaywrightBaseScraper):
    """The Vanguard — Tulsa live-music venue (Webflow site, .ec-col-item cards).
    A queer-friendly venue with shows most nights, so it fills weekday slates.
    """
    source_name = "the_vanguard_tulsa"
    BASE_URL = "https://www.thevanguardtulsa.com"
    EVENTS_URL = "https://www.thevanguardtulsa.com/shows"
    DEFAULT_VENUE = "The Vanguard, 222 N Main St, Tulsa, OK"

    _MONTHS = ("January|February|March|April|May|June|July|August|September|"
               "October|November|December")

    def scrape(self) -> List[Dict]:
        from bs4 import BeautifulSoup
        import re as _re
        html = self.fetch_page_js(self.EVENTS_URL, wait_for_selector=".ec-col-item", timeout=25000)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        date_rx = _re.compile(rf'({self._MONTHS})\s+(\d{{1,2}}),\s*(\d{{4}})')
        events, seen = [], set()
        for card in soup.select(".ec-col-item"):
            text = card.get_text(" ", strip=True)
            m = date_rx.search(text)
            if not m:
                continue
            name = _re.sub(r'^[^A-Za-z0-9]+', '', text[:m.start()].strip())
            if not name or len(name) < 2:
                continue
            try:
                date = datetime.strptime(
                    f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y"
                ).strftime("%Y-%m-%d")
            except ValueError:
                continue
            link = card.find("a", href=True)
            href = link["href"] if link else ""
            url = (self.BASE_URL + href) if href.startswith("/") else (href or self.EVENTS_URL)
            key = (name.lower(), date)
            if key in seen:
                continue
            seen.add(key)
            events.append(self.make_event(
                name=name, date=date, time="", venue=self.DEFAULT_VENUE,
                description="", url=url, priority=2,
            ))
        return events


# ── Module-level entry point ───────────────────────────────────────────────────

_PLAYWRIGHT_SCRAPERS = [
    GoogleEventsScraper,
    VanguardScraper,
    FreedomOklahomaScraper,
    TulsaArtistFellowshipScraper,
    TwistedArtsScraper,
    BlackQueerTulsaScraper,
    AllSoulsScraper,
    EventbriteJSScraper,
    VisitTulsaScraper,
    OKEQPlaywrightScraper,
    CircleCinemaScraper,
    PhilbrookMuseumScraper,
    WOMPAScraper,
    ShambhalaTulsaScraper,
    BeLoveYogaScraper,
    OpenEyeYogaScraper,
    YogaQuestScraper,
    SonicRayScraper,
    UpdogYogaScraper,
    SanaMeditationScraper,
    TulsaYogaMeditationCenterScraper,
    TulsaPeoplesOrchestraScraper,
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
