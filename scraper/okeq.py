"""Scraper for Oklahomans for Equality (OKEQ) events."""

import sys
import os
import re
import logging
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class OKEQScraper(BaseScraper):
    """Scrape events from okeq.org (Dennis R. Neill Equality Center)."""

    source_name = "okeq"

    EVENTS_URL = "https://www.okeq.org/events"
    CALENDAR_URL = "https://www.okeq.org/calendar"
    BASE_URL = "https://www.okeq.org"

    def scrape(self) -> List[Dict]:
        events = []

        # Try the main events page first
        events.extend(self._scrape_events_page())

        if not events:
            # Fallback: try the calendar page
            events.extend(self._scrape_calendar_page())

        return events

    def _scrape_events_page(self) -> List[Dict]:
        """Scrape the /events listing page."""
        soup = self.fetch_page(self.EVENTS_URL)
        if not soup:
            return []

        events = []

        # OKEQ uses various CMS patterns; try common event container selectors
        event_containers = (
            soup.select(".eventlist-event")
            or soup.select(".sqs-block-content .event")
            or soup.select("[data-type='event']")
            or soup.select(".summary-item")
            or soup.select("article.eventlist-event--upcoming")
        )

        for container in event_containers:
            try:
                event = self._parse_event_container(container)
                if event:
                    events.append(event)
            except Exception as e:
                logger.debug(f"[okeq] Failed to parse event container: {e}")
                continue

        # If no structured containers found, try a broader approach
        if not events:
            events = self._parse_unstructured(soup)

        self._random_delay()
        return events

    def _parse_event_container(self, container) -> Dict | None:
        """Parse a single event container element."""
        # Event name
        name_el = (
            container.select_one(".eventlist-title")
            or container.select_one("h1, h2, h3")
            or container.select_one(".summary-title")
        )
        if not name_el:
            return None
        name = name_el.get_text(strip=True)
        if not name:
            return None

        # Event URL
        link_el = name_el.find("a") or container.find("a")
        url = ""
        if link_el and link_el.get("href"):
            href = link_el["href"]
            url = href if href.startswith("http") else self.BASE_URL + href

        # Date
        date_el = (
            container.select_one(".eventlist-datetag")
            or container.select_one("time")
            or container.select_one(".event-date")
            or container.select_one(".summary-metadata-item--date")
        )
        date_str = ""
        if date_el:
            # Prefer datetime attribute
            date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)
        date_str = self.parse_date_flexible(date_str)

        # Time
        time_el = (
            container.select_one(".eventlist-meta-time")
            or container.select_one(".event-time-12hr")
        )
        time_str = time_el.get_text(strip=True) if time_el else ""

        # Description
        desc_el = (
            container.select_one(".eventlist-description")
            or container.select_one(".summary-excerpt")
            or container.select_one("p")
        )
        description = ""
        if desc_el:
            description = desc_el.get_text(strip=True)[:500]

        # Venue / location
        venue_el = (
            container.select_one(".eventlist-meta-address")
            or container.select_one(".event-location")
        )
        venue = venue_el.get_text(strip=True) if venue_el else "Dennis R. Neill Equality Center"

        return self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue=venue,
            description=description,
            url=url,
            priority=1,
        )

    def _scrape_calendar_page(self) -> List[Dict]:
        """Fallback: scrape the /calendar page."""
        soup = self.fetch_page(self.CALENDAR_URL)
        if not soup:
            return []

        events = []
        # Calendar pages often have event items in list or grid format
        items = soup.select(".eventlist-event") or soup.select(".sqs-block-calendar")
        for item in items:
            event = self._parse_event_container(item)
            if event:
                events.append(event)

        self._random_delay()
        return events

    def _parse_unstructured(self, soup) -> List[Dict]:
        """Last resort: look for any event-like content on the page."""
        events = []
        # Look for links that might be event pages
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)
            if "/event" in href.lower() and text and len(text) > 5:
                full_url = href if href.startswith("http") else self.BASE_URL + href
                events.append(self.make_event(
                    name=text,
                    date="",
                    url=full_url,
                    venue="Dennis R. Neill Equality Center",
                    priority=1,
                ))
        return events


def scrape() -> List[Dict]:
    """Module-level entry point."""
    return OKEQScraper().safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  {e['name']} | {e['date']} | {e['venue']}")
    print(f"\nTotal: {len(results)} events")
