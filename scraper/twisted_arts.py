"""Scraper for Twisted Arts / Twisted Fest events and shows."""

import sys
import os
import re
import logging
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class TwistedArtsScraper(BaseScraper):
    """Scrape events from twistedfest.org (formerly twistedartstulsa.com)."""

    source_name = "twisted_arts"

    BASE_URL = "https://twistedfest.org"
    EVENTS_PATHS = ["/events", "/upcoming-events", "/home-front-page", ""]

    def scrape(self) -> List[Dict]:
        events = []

        for path in self.EVENTS_PATHS:
            url = self.BASE_URL + path
            soup = self.fetch_page(url)
            if not soup:
                continue

            found = self._extract_events(soup, url)
            events.extend(found)
            self._random_delay()

            if events:
                break  # Got events, no need to try more paths

        return events

    def _extract_events(self, soup, page_url: str) -> List[Dict]:
        """Extract events from a page using multiple strategies."""
        events = []

        # Strategy 1: Structured event containers (Squarespace, Wix, WordPress patterns)
        containers = (
            soup.select(".eventlist-event")
            or soup.select(".event-item")
            or soup.select(".shows-item")
            or soup.select(".summary-item")
            or soup.select(".tribe-events-calendar-list__event")
            or soup.select(".type-tribe_events")
            or soup.select("[class*='event']")
        )

        for container in containers:
            event = self._parse_container(container)
            if event:
                events.append(event)

        # Strategy 2: Look for event-like headings with dates nearby
        if not events:
            events = self._parse_headings_approach(soup)

        # Strategy 3: Look for links to event detail pages
        if not events:
            events = self._parse_links_approach(soup, page_url)

        return events

    def _parse_container(self, container) -> Dict | None:
        """Parse a structured event container."""
        name_el = container.select_one(
            "h1, h2, h3, h4, .event-title, .summary-title, "
            ".tribe-events-calendar-list__event-title"
        )
        if not name_el:
            return None

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            return None

        # URL
        link_el = container.find("a", href=True)
        url = ""
        if link_el:
            href = link_el["href"]
            url = href if href.startswith("http") else self.BASE_URL + href

        # Date
        date_el = (
            container.select_one("time")
            or container.select_one("[class*='date']")
            or container.select_one(".eventlist-datetag")
            or container.select_one(".tribe-event-schedule-details")
        )
        date_str = ""
        if date_el:
            date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)
        date_str = self.parse_date_flexible(date_str)

        # Time
        time_el = container.select_one("[class*='time']")
        time_str = time_el.get_text(strip=True) if time_el else ""

        # Description
        desc_el = container.select_one("p, [class*='description'], [class*='excerpt']")
        description = desc_el.get_text(strip=True)[:500] if desc_el else ""

        return self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue="Twisted Arts Tulsa",
            description=description,
            url=url,
            priority=1,
        )

    def _parse_headings_approach(self, soup) -> List[Dict]:
        """Look for event names in headings."""
        events = []
        headings = soup.find_all(["h2", "h3", "h4"])

        for heading in headings:
            text = heading.get_text(strip=True)
            if not text or len(text) < 5:
                continue

            # Skip navigation-type headings
            skip_words = ["menu", "contact", "about", "home", "gallery", "shop", "cart"]
            if any(w in text.lower() for w in skip_words):
                continue

            # Check for date info nearby
            parent = heading.parent
            date_str = ""
            time_str = ""
            if parent:
                sibling_text = parent.get_text(" ", strip=True)
                date_match = re.search(
                    r'(\w+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4}|\w+day,?\s+\w+ \d{1,2})',
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
                venue="Twisted Arts Tulsa",
                url=url,
                priority=1,
            ))

        return events

    def _parse_links_approach(self, soup, page_url: str) -> List[Dict]:
        """Look for links that might be event detail pages."""
        events = []
        seen = set()

        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)

            if not text or len(text) < 5 or text in seen:
                continue

            # Look for event-like link patterns
            event_patterns = ["event", "show", "performance", "drag", "night", "fest", "festival"]
            if any(p in href.lower() for p in event_patterns) or any(p in text.lower() for p in event_patterns):
                seen.add(text)
                full_url = href if href.startswith("http") else self.BASE_URL + href
                events.append(self.make_event(
                    name=text,
                    date="",
                    venue="Twisted Arts Tulsa",
                    url=full_url,
                    priority=1,
                ))

        return events


def scrape() -> List[Dict]:
    """Module-level entry point."""
    return TwistedArtsScraper().safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  {e['name']} | {e['date']} | {e['venue']}")
    print(f"\nTotal: {len(results)} events")
