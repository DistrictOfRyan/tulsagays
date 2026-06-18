"""Scraper for Tulsa Arts District events."""

import sys
import os
import re
import html
import logging
from datetime import datetime, timedelta
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class TulsaArtsDistrictScraper(BaseScraper):
    """Scrape events from thetulsaartsdistrict.org.

    The site runs The Events Calendar (WordPress). The /events/list/ page now
    renders event cards client-side via AJAX, so the static HTML carries empty
    tribe-events templates (parsing it yields 0). The plugin's REST API
    (/wp-json/tribe/events/v1/events) returns the real data, so that is the
    primary path; the HTML selectors remain as a fallback.
    """

    source_name = "tulsa_arts_district"

    BASE_URL = "https://thetulsaartsdistrict.org"
    EVENTS_URL = "https://thetulsaartsdistrict.org/events/list/"
    API_URL = "https://thetulsaartsdistrict.org/wp-json/tribe/events/v1/events"

    def scrape(self) -> List[Dict]:
        # Primary: The Events Calendar REST API.
        events = self._scrape_api()
        if events:
            return events

        # Fallback: HTML parsing (kept in case the API is ever disabled).
        soup = self.fetch_page(self.EVENTS_URL)
        if soup:
            events = self._extract_events(soup)

        if not events:
            self._random_delay()
            soup = self.fetch_page(self.BASE_URL + "/events/")
            if soup:
                events = self._extract_events(soup)

        return events

    def _scrape_api(self) -> List[Dict]:
        """Pull this-week events from the tribe/events/v1 REST API.

        The endpoint's `start_date`/`end_date` query params trip the site's
        WAF (403), so we request upcoming events undated (the API returns them
        ascending from today) and filter to the current Mon-Sun week here.
        """
        today = datetime.now()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        mon_s, sun_s = monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")

        data = self.fetch_json(self.API_URL, params={"per_page": 50, "page": 1})
        if not data or not isinstance(data, dict):
            return []

        events = []
        for item in data.get("events", []):
            start = (item.get("start_date", "") or "")[:10]
            if not (mon_s <= start <= sun_s):
                continue
            try:
                ev = self._parse_api_event(item)
                if ev:
                    events.append(ev)
            except Exception as e:  # pragma: no cover - defensive
                logger.debug(f"[{self.source_name}] API event skipped: {e}")

        logger.info(f"[{self.source_name}] API: {len(events)} this-week events "
                    f"(scanned {len(data.get('events', []))} upcoming)")
        return events

    @staticmethod
    def _clean(text: str) -> str:
        """Unescape HTML entities and strip tags from an API string field."""
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", " ", text)
        return html.unescape(text).strip()

    def _parse_api_event(self, item: Dict) -> Dict | None:
        name = self._clean(item.get("title", ""))
        if not name or len(name) < 3:
            return None

        raw_start = item.get("start_date", "") or ""  # "YYYY-MM-DD HH:MM:SS"
        date_str = raw_start[:10]
        time_str = ""
        if not item.get("all_day") and len(raw_start) >= 16:
            try:
                dt = datetime.strptime(raw_start[:19], "%Y-%m-%d %H:%M:%S")
                time_str = dt.strftime("%I:%M %p").lstrip("0")
            except ValueError:
                time_str = ""

        venue = ""
        v = item.get("venue")
        if isinstance(v, dict):
            venue = self._clean(v.get("venue", ""))
        venue = venue or "Tulsa Arts District"

        desc = self._clean(item.get("excerpt") or item.get("description") or "")[:500]
        url = item.get("url", "") or self.EVENTS_URL

        return self.make_event(
            name=name, date=date_str, time=time_str,
            venue=venue, description=desc, url=url, priority=2,
        )

    def _extract_events(self, soup) -> List[Dict]:
        """Extract events from the Tulsa Arts District events page.

        The site likely uses The Events Calendar (WordPress plugin) which
        generates tribe-events classes.
        """
        events = []

        # Strategy 1: The Events Calendar plugin (common WordPress pattern)
        containers = (
            soup.select(".tribe-events-calendar-list__event")
            or soup.select(".type-tribe_events")
            or soup.select(".tribe-events-list-event")
            or soup.select(".tribe-common-g-row")
        )

        for container in containers:
            event = self._parse_tribe_event(container)
            if event:
                events.append(event)

        # Strategy 2: Generic event containers
        if not events:
            containers = (
                soup.select(".event-item")
                or soup.select(".eventlist-event")
                or soup.select("[class*='event']")
            )

            for container in containers:
                event = self._parse_generic_container(container)
                if event:
                    events.append(event)

        # Strategy 3: Headings approach
        if not events:
            events = self._parse_headings(soup)

        return events

    def _parse_tribe_event(self, container) -> Dict | None:
        """Parse a The Events Calendar (tribe) event container."""
        name_el = container.select_one(
            ".tribe-events-calendar-list__event-title, "
            ".tribe-events-list-event-title, "
            "h2, h3"
        )
        if not name_el:
            return None

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            return None

        # URL
        link = name_el.find("a", href=True) or container.find("a", href=True)
        url = ""
        if link:
            href = link["href"]
            url = href if href.startswith("http") else self.BASE_URL + href

        # Date
        date_el = (
            container.select_one("time")
            or container.select_one(".tribe-event-schedule-details")
            or container.select_one("[class*='date']")
        )
        date_str = ""
        if date_el:
            date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)
            # Tribe events often use ISO format in datetime attr
            if date_str and "T" in date_str:
                date_str = date_str[:10]
        date_str = self.parse_date_flexible(date_str)

        # Time
        time_el = container.select_one(
            ".tribe-event-schedule-details__datetime, [class*='time']"
        )
        time_str = ""
        if time_el:
            time_text = time_el.get_text(strip=True)
            time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))', time_text)
            if time_match:
                time_str = time_match.group(1)

        # Description
        desc_el = container.select_one(
            ".tribe-events-calendar-list__event-description, "
            "p, [class*='description'], [class*='excerpt']"
        )
        description = desc_el.get_text(strip=True)[:500] if desc_el else ""

        # Venue
        venue_el = container.select_one(
            ".tribe-events-calendar-list__event-venue, "
            "[class*='venue']"
        )
        venue = venue_el.get_text(strip=True) if venue_el else "Tulsa Arts District"

        return self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue=venue,
            description=description,
            url=url,
            priority=2,
        )

    def _parse_generic_container(self, container) -> Dict | None:
        """Parse a generic event container."""
        name_el = container.select_one("h1, h2, h3, h4, .event-title")
        if not name_el:
            return None

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            return None

        link = container.find("a", href=True)
        url = ""
        if link:
            href = link["href"]
            url = href if href.startswith("http") else self.BASE_URL + href

        date_el = container.select_one("time, [class*='date']")
        date_str = ""
        if date_el:
            date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)
        date_str = self.parse_date_flexible(date_str)

        time_el = container.select_one("[class*='time']")
        time_str = time_el.get_text(strip=True) if time_el else ""

        desc_el = container.select_one("p, [class*='description']")
        description = desc_el.get_text(strip=True)[:500] if desc_el else ""

        return self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue="Tulsa Arts District",
            description=description,
            url=url,
            priority=2,
        )

    def _parse_headings(self, soup) -> List[Dict]:
        """Fallback: parse headings for event-like content."""
        events = []

        for heading in soup.find_all(["h2", "h3", "h4"]):
            text = heading.get_text(strip=True)
            if not text or len(text) < 5:
                continue

            skip_words = ["menu", "contact", "about", "home", "gallery", "shop", "sponsor"]
            if any(w in text.lower() for w in skip_words):
                continue

            parent = heading.parent
            date_str = ""
            time_str = ""
            if parent:
                sibling_text = parent.get_text(" ", strip=True)
                date_match = re.search(
                    r'(\w+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4})',
                    sibling_text
                )
                if date_match:
                    date_str = self.parse_date_flexible(date_match.group(1))

                time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))', sibling_text)
                if time_match:
                    time_str = time_match.group(1)

            link = heading.find("a", href=True)
            url = ""
            if link:
                href = link["href"]
                url = href if href.startswith("http") else self.BASE_URL + href

            events.append(self.make_event(
                name=text,
                date=date_str,
                time=time_str,
                venue="Tulsa Arts District",
                url=url,
                priority=2,
            ))

        return events


def scrape() -> List[Dict]:
    """Module-level entry point."""
    return TulsaArtsDistrictScraper().safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  {e['name']} | {e['date']} | {e['venue']}")
    print(f"\nTotal: {len(results)} events")
