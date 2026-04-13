"""Dedicated scrapers for specific Tulsa LGBTQ organizations.

Covers: PFLAG Tulsa, Black Queer Tulsa, Freedom Oklahoma, Council Oak Men's Chorale,
HotMess Sports, Circle Cinema (filtered), Magic City Books (filtered),
All Souls Unitarian (special events), UTulsa Pride Club, OSU Tulsa events,
Twisted Arts (date-fixed).

Each org: tries JSON-LD first, then HTML parsing, then returns empty with a log message.
"""

import sys
import os
import json
import re
import logging
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

LGBTQ_KEYWORDS = [
    "lgbtq", "queer", "gay", "lesbian", "bi", "trans", "drag", "pride",
    "rainbow", "dyke", "nonbinary", "non-binary", "gender", "equality",
    "affirming", "inclusive", "homo", "sapphic",
]


def _is_lgbtq_relevant(name: str, description: str = "") -> bool:
    combined = (name + " " + description).lower()
    return any(kw in combined for kw in LGBTQ_KEYWORDS)


class BaseOrgScraper(BaseScraper):
    """Shared base for all org scrapers."""

    source_name = "specific_orgs"
    BASE_URL = ""
    EVENTS_URL = ""
    DEFAULT_VENUE = ""
    PRIORITY = 1
    FILTER_LGBTQ = False  # Set True for venues that host mixed events

    def scrape(self) -> List[Dict]:
        events = []

        # Try JSON-LD
        soup = self.fetch_page(self.EVENTS_URL)
        if soup:
            events = self._extract_json_ld(soup)
            if not events:
                events = self._extract_html(soup)
        else:
            logger.warning(f"[{self.source_name}] Could not fetch {self.EVENTS_URL}")

        if self.FILTER_LGBTQ:
            before = len(events)
            events = [e for e in events if _is_lgbtq_relevant(e.get("name", ""), e.get("description", ""))]
            logger.info(f"[{self.source_name}] Filtered {before} -> {len(events)} LGBTQ events")

        self._random_delay()
        return events

    def _extract_json_ld(self, soup) -> List[Dict]:
        events = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw = script.string
                if not raw:
                    continue
                data = json.loads(raw)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") not in ("Event", "SocialEvent", "MusicEvent"):
                        continue
                    name = item.get("name", "")
                    if not name:
                        continue
                    start = item.get("startDate", "")
                    date_str = start[:10] if start else ""
                    time_str = ""
                    if "T" in start:
                        time_str = start.split("T")[1][:5]
                    location = item.get("location", {})
                    venue = self.DEFAULT_VENUE
                    if isinstance(location, dict):
                        venue = location.get("name", self.DEFAULT_VENUE) or self.DEFAULT_VENUE
                    description = item.get("description", "")[:500]
                    url = item.get("url", "")
                    events.append(self.make_event(
                        name=name,
                        date=date_str,
                        time=time_str,
                        venue=venue,
                        description=description,
                        url=url,
                        priority=self.PRIORITY,
                    ))
            except Exception:
                continue
        return events

    def _extract_html(self, soup) -> List[Dict]:
        """Generic HTML extraction fallback."""
        events = []
        containers = (
            soup.select(".eventlist-event")
            or soup.select(".tribe-events-calendar-list__event")
            or soup.select(".type-tribe_events")
            or soup.select(".event-item")
            or soup.select("[class*='event-card']")
            or soup.select("article")
        )

        for container in containers[:20]:
            event = self._parse_container(container)
            if event:
                events.append(event)

        if not events:
            logger.info(f"[{self.source_name}] HTML parsing found no structured events at {self.EVENTS_URL}")

        return events

    def _parse_container(self, container) -> Optional[Dict]:
        name_el = container.select_one(
            "h1, h2, h3, h4, .event-title, .eventlist-title, "
            ".tribe-events-calendar-list__event-title, .summary-title"
        )
        if not name_el:
            return None
        name = name_el.get_text(strip=True)
        if not name or len(name) < 5:
            return None

        link = name_el.find("a", href=True) or container.find("a", href=True)
        url = ""
        if link:
            href = link["href"]
            url = href if href.startswith("http") else self.BASE_URL.rstrip("/") + "/" + href.lstrip("/")

        date_el = (
            container.select_one("time[datetime]")
            or container.select_one("[class*='date']")
            or container.select_one("time")
        )
        date_str = ""
        if date_el:
            raw = date_el.get("datetime", "") or date_el.get_text(strip=True)
            date_str = self.parse_date_flexible(raw[:10] if len(raw) > 10 else raw)

        time_el = container.select_one("[class*='time']")
        time_str = time_el.get_text(strip=True) if time_el else ""

        desc_el = container.select_one("p, [class*='description'], [class*='excerpt']")
        description = desc_el.get_text(strip=True)[:500] if desc_el else ""

        return self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue=self.DEFAULT_VENUE,
            description=description,
            url=url,
            priority=self.PRIORITY,
        )


# ── Individual org scrapers ────────────────────────────────────────────────

class PFLAGTulsaScraper(BaseOrgScraper):
    source_name = "pflag_tulsa"
    BASE_URL = "https://pflag.org"
    EVENTS_URL = "https://pflag.org/chapter/pflag-tulsa/"
    DEFAULT_VENUE = "110 S Hartford Ave, Tulsa"
    PRIORITY = 1


class BlackQueerTulsaScraper(BaseOrgScraper):
    """Stub -- handled by playwright_scrapers.BlackQueerTulsaScraper."""
    source_name = "black_queer_tulsa"
    BASE_URL = "https://www.blackqueertulsa.org"
    EVENTS_URL = "https://www.blackqueertulsa.org/events"
    DEFAULT_VENUE = "Various locations, Tulsa"
    PRIORITY = 1

    def scrape(self) -> List[Dict]:
        logger.info("[specific_orgs] black_queer_tulsa: handled by playwright_scrapers")
        return []


class FreedomOklahomaScraper(BaseOrgScraper):
    """Stub -- handled by playwright_scrapers.FreedomOklahomaScraper."""
    source_name = "freedom_oklahoma"
    BASE_URL = "https://www.freedomoklahoma.org"
    EVENTS_URL = "https://www.freedomoklahoma.org/events"
    DEFAULT_VENUE = "Oklahoma City / Tulsa area"
    PRIORITY = 2

    def scrape(self) -> List[Dict]:
        logger.info("[specific_orgs] freedom_oklahoma: handled by playwright_scrapers")
        return []


class CouncilOakScraper(BaseOrgScraper):
    source_name = "council_oak"
    BASE_URL = "https://www.counciloak.org"
    EVENTS_URL = "https://www.counciloak.org/concerts"
    DEFAULT_VENUE = "Tulsa Performing Arts Center"
    PRIORITY = 1


class HotMessSportsScraper(BaseOrgScraper):
    source_name = "hotmess_sports"
    BASE_URL = "https://www.hotmesssports.com"
    EVENTS_URL = "https://www.hotmesssports.com/tulsa"
    DEFAULT_VENUE = "Various venues, Tulsa"
    PRIORITY = 2


class CircleCinemaScraper(BaseOrgScraper):
    source_name = "circle_cinema"
    BASE_URL = "https://www.circlecinema.org"
    EVENTS_URL = "https://www.circlecinema.org/"
    DEFAULT_VENUE = "Circle Cinema, Tulsa"
    PRIORITY = 2
    FILTER_LGBTQ = True


class MagicCityBooksScraper(BaseOrgScraper):
    source_name = "magic_city_books"
    BASE_URL = "https://magiccitybooks.com"
    EVENTS_URL = "https://magiccitybooks.com/events/"
    DEFAULT_VENUE = "Magic City Books, Tulsa"
    PRIORITY = 2
    FILTER_LGBTQ = True


class AllSoulsSpecialScraper(BaseOrgScraper):
    """Special events beyond regular Sunday services."""
    source_name = "all_souls_special"
    BASE_URL = "https://allsoulschurch.org"
    EVENTS_URL = "https://allsoulschurch.org/events/"
    DEFAULT_VENUE = "All Souls Unitarian Church, 2952 S Peoria Ave"
    PRIORITY = 2

    def scrape(self) -> List[Dict]:
        events = []
        for path in ["/events/", "/calendar/", "/upcoming-events/"]:
            url = self.BASE_URL + path
            soup = self.fetch_page(url)
            if soup:
                found = self._extract_json_ld(soup)
                if not found:
                    found = self._extract_html(soup)
                events.extend(found)
                if events:
                    break
            self._random_delay()

        # Filter out basic weekly services (already in recurring.py)
        events = [e for e in events if "sunday service" not in e.get("name", "").lower()]
        return events


class UTulsaPrideClubScraper(BaseOrgScraper):
    source_name = "utulsa_pride"
    BASE_URL = "https://calendar.utulsa.edu"
    EVENTS_URL = "https://calendar.utulsa.edu/organization/pride-club/"
    DEFAULT_VENUE = "University of Tulsa Campus"
    PRIORITY = 2


class OSUTulsaScraper(BaseOrgScraper):
    source_name = "osu_tulsa"
    BASE_URL = "https://events.tulsa.okstate.edu"
    EVENTS_URL = "https://events.tulsa.okstate.edu"
    DEFAULT_VENUE = "OSU Tulsa Campus, 700 N Greenwood Ave"
    PRIORITY = 2
    FILTER_LGBTQ = True


class TwistedArtsScraper(BaseOrgScraper):
    """Stub -- handled by playwright_scrapers.TwistedArtsScraper."""

    source_name = "twisted_arts"
    BASE_URL = "https://twistedfest.org"
    EVENTS_URL = "https://twistedfest.org/events"
    DEFAULT_VENUE = "Circle Cinema / Twisted Arts Tulsa"
    PRIORITY = 1

    def scrape(self) -> List[Dict]:
        logger.info("[specific_orgs] twisted_arts: handled by playwright_scrapers")
        return []

    def _scrape_original(self) -> List[Dict]:
        """Original implementation kept here for reference."""
        events = []

        # Try Squarespace JSON API first
        for path in ["/events?format=json-pretty", "/upcoming-events?format=json-pretty"]:
            try:
                url = self.BASE_URL + path
                self._rotate_user_agent()
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                items = data.get("items", [])
                for item in items:
                    event = self._parse_squarespace_item(item)
                    if event:
                        events.append(event)
                if events:
                    logger.info(f"[twisted_arts] Squarespace API found {len(events)} events")
                    return events
            except Exception as e:
                logger.debug(f"[twisted_arts] Squarespace API path {path} failed: {e}")

        # Try JSON-LD on each path
        for path in ["/events", ""]:
            url = self.BASE_URL + path
            soup = self.fetch_page(url)
            if soup:
                found = self._extract_json_ld(soup)
                if found:
                    logger.info(f"[twisted_arts] JSON-LD found {len(found)} events at {url}")
                    return found
                found = self._extract_html(soup)
                if found:
                    return found
            self._random_delay()

        logger.warning("[twisted_arts] No events found -- site may be JS-rendered")
        return []

    def _parse_squarespace_item(self, item: dict) -> Optional[Dict]:
        name = item.get("title", "")
        if not name:
            return None

        start_ts = item.get("startDate")
        date_str = ""
        time_str = ""
        if start_ts:
            try:
                ts = int(start_ts)
                if ts > 1e10:
                    ts = ts / 1000
                from datetime import datetime as _dt
                dt = _dt.utcfromtimestamp(ts)
                date_str = dt.strftime("%Y-%m-%d")
                time_str = dt.strftime("%I:%M %p")
            except Exception:
                pass

        if not date_str:
            for key in ["startDateIso", "startDateFormatted"]:
                val = item.get(key, "")
                if val:
                    date_str = self.parse_date_flexible(val[:10])
                    break

        url = item.get("fullUrl", "") or item.get("absUrl", "")
        if url and not url.startswith("http"):
            url = self.BASE_URL + url

        body = item.get("body", "") or ""
        description = re.sub(r'<[^>]+>', '', body)[:500]

        return self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue=self.DEFAULT_VENUE,
            description=description,
            url=url,
            priority=self.PRIORITY,
        )


# ── Module-level scrape function ───────────────────────────────────────────

_SCRAPERS = [
    PFLAGTulsaScraper,
    BlackQueerTulsaScraper,
    FreedomOklahomaScraper,
    CouncilOakScraper,
    HotMessSportsScraper,
    CircleCinemaScraper,
    MagicCityBooksScraper,
    AllSoulsSpecialScraper,
    UTulsaPrideClubScraper,
    OSUTulsaScraper,
    TwistedArtsScraper,
]


def scrape() -> List[Dict]:
    """Module-level entry point -- runs all org scrapers."""
    all_events = []
    for scraper_cls in _SCRAPERS:
        scraper = scraper_cls()
        try:
            events = scraper.safe_scrape()
            logger.info(f"[specific_orgs] {scraper.source_name}: {len(events)} events")
            all_events.extend(events)
        except Exception as e:
            logger.error(f"[specific_orgs] {scraper.source_name} crashed: {e}")
    return all_events


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  [{e['source']}] {e['date']} | {e['name']} | {e['venue']}")
    print(f"\nTotal: {len(results)} events")
