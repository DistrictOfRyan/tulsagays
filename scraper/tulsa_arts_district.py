"""Scraper for Tulsa Arts District events."""

import sys
import os
import re
import logging
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class TulsaArtsDistrictScraper(BaseScraper):
    """Scrape events from thetulsaartsdistrict.org/events/list/."""

    source_name = "tulsa_arts_district"

    BASE_URL = "https://thetulsaartsdistrict.org"
    EVENTS_URL = "https://thetulsaartsdistrict.org/events/list/"

    def scrape(self) -> List[Dict]:
        events = []

        soup = self.fetch_page(self.EVENTS_URL)
        if soup:
            events = self._extract_events(soup)

        # Try base events page if list view didn't work
        if not events:
            self._random_delay()
            soup = self.fetch_page(self.BASE_URL + "/events/")
            if soup:
                events = self._extract_events(soup)

        return events

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
