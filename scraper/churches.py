"""Scraper for affirming church events: All Souls Unitarian and Church of the Restoration."""

import sys
import os
import re
import logging
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class AllSoulsScraper(BaseScraper):
    """Scrape events from All Souls Unitarian Church (allsoulschurch.org)."""

    source_name = "all_souls"

    BASE_URL = "https://www.allsoulschurch.org"
    EVENTS_PATHS = ["/events", "/calendar", "/upcoming-events", "/whats-happening"]

    def scrape(self) -> List[Dict]:
        events = []

        for path in self.EVENTS_PATHS:
            url = self.BASE_URL + path
            soup = self.fetch_page(url)
            if not soup:
                continue

            found = self._extract_events(soup)
            events.extend(found)
            self._random_delay()

            if events:
                break

        return events

    def _extract_events(self, soup) -> List[Dict]:
        """Extract events from the page."""
        events = []

        # Try common CMS event selectors
        containers = (
            soup.select(".eventlist-event")
            or soup.select(".tribe-events-list .tribe-events-calendar-list__event")
            or soup.select(".type-tribe_events")
            or soup.select(".event-item")
            or soup.select(".views-row")  # Drupal
            or soup.select("[class*='event']")
        )

        for container in containers:
            event = self._parse_event(container)
            if event:
                events.append(event)

        # Fallback: look for a calendar or event listing
        if not events:
            events = self._parse_generic(soup)

        return events

    def _parse_event(self, container) -> Dict | None:
        """Parse a single event container."""
        name_el = container.select_one(
            "h1, h2, h3, h4, "
            ".tribe-events-list-event-title, "
            ".eventlist-title, "
            ".event-title"
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
            or container.select_one("abbr")
        )
        date_str = ""
        if date_el:
            date_str = date_el.get("datetime", "") or date_el.get("title", "") or date_el.get_text(strip=True)
        date_str = self.parse_date_flexible(date_str)

        # Time
        time_str = ""
        time_el = container.select_one("[class*='time']")
        if time_el:
            time_str = time_el.get_text(strip=True)

        # Description
        desc_el = container.select_one(
            "p, .tribe-events-list-event-description, [class*='desc'], [class*='excerpt']"
        )
        description = desc_el.get_text(strip=True)[:500] if desc_el else ""

        return self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue="All Souls Unitarian Church",
            description=description,
            url=url,
            priority=2,
        )

    def _parse_generic(self, soup) -> List[Dict]:
        """Generic fallback parser."""
        events = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)
            if text and len(text) > 5 and ("event" in href.lower() or "calendar" in href.lower()):
                full_url = href if href.startswith("http") else self.BASE_URL + href
                events.append(self.make_event(
                    name=text,
                    date="",
                    venue="All Souls Unitarian Church",
                    url=full_url,
                    priority=2,
                ))
        return events


class ChurchRestorationScraper(BaseScraper):
    """Scrape events from Church of the Restoration UU."""

    source_name = "church_restoration"

    BASE_URL = "https://www.churchoftherestoration.org"
    EVENTS_PATHS = ["/events", "/calendar", "/upcoming", ""]

    def scrape(self) -> List[Dict]:
        events = []

        for path in self.EVENTS_PATHS:
            url = self.BASE_URL + path
            soup = self.fetch_page(url)
            if not soup:
                continue

            found = self._extract_events(soup)
            events.extend(found)
            self._random_delay()

            if events:
                break

        return events

    def _extract_events(self, soup) -> List[Dict]:
        """Extract events from the page."""
        events = []

        containers = (
            soup.select(".eventlist-event")
            or soup.select(".event-item")
            or soup.select("[class*='event']")
            or soup.select(".summary-item")
        )

        for container in containers:
            name_el = container.select_one("h1, h2, h3, h4, .event-title, .summary-title")
            if not name_el:
                continue

            name = name_el.get_text(strip=True)
            if not name or len(name) < 3:
                continue

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

            desc_el = container.select_one("p, [class*='desc'], [class*='excerpt']")
            description = desc_el.get_text(strip=True)[:500] if desc_el else ""

            events.append(self.make_event(
                name=name,
                date=date_str,
                time=time_str,
                venue="Church of the Restoration",
                description=description,
                url=url,
                priority=2,
            ))

        return events


def scrape() -> List[Dict]:
    """Module-level entry point. Scrapes both churches."""
    all_events = []

    all_souls = AllSoulsScraper()
    all_events.extend(all_souls.safe_scrape())

    restoration = ChurchRestorationScraper()
    all_events.extend(restoration.safe_scrape())

    return all_events


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  [{e['source']}] {e['name']} | {e['date']} | {e['venue']}")
    print(f"\nTotal: {len(results)} events")
