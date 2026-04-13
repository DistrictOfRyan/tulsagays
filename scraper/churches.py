"""Scraper for affirming church events: All Souls Unitarian Church.

NOTE: Church of the Restoration (churchoftherestoration.org) is DNS-dead as of 2026
and has been removed from this scraper.

All Souls Unitarian regular Sunday services are handled in recurring.py.
This scraper looks for special events beyond weekly services.
"""

import sys
import os
import re
import json
import logging
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class AllSoulsScraper(BaseScraper):
    """Scrape special events from All Souls Unitarian Church (allsoulschurch.org)."""

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

            found = self._extract_json_ld(soup)
            if not found:
                found = self._extract_events(soup)
            events.extend(found)
            self._random_delay()

            if events:
                break

        # Filter out plain "Sunday Service" entries (covered in recurring.py)
        events = [e for e in events if "sunday service" not in e.get("name", "").lower()]
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
                    if item.get("@type") != "Event":
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
                    venue = "All Souls Unitarian Church, 2952 S Peoria Ave"
                    if isinstance(location, dict):
                        venue = location.get("name", venue) or venue
                    description = item.get("description", "")[:500]
                    url = item.get("url", "")
                    events.append(self.make_event(
                        name=name,
                        date=date_str,
                        time=time_str,
                        venue=venue,
                        description=description,
                        url=url,
                        priority=2,
                    ))
            except Exception:
                continue
        return events

    def _extract_events(self, soup) -> List[Dict]:
        events = []

        containers = (
            soup.select(".eventlist-event")
            or soup.select(".tribe-events-list .tribe-events-calendar-list__event")
            or soup.select(".type-tribe_events")
            or soup.select(".event-item")
            or soup.select(".views-row")
            or soup.select("[class*='event']")
        )

        for container in containers:
            event = self._parse_event(container)
            if event:
                events.append(event)

        return events

    def _parse_event(self, container) -> Optional[Dict]:
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

        link = name_el.find("a", href=True) or container.find("a", href=True)
        url = ""
        if link:
            href = link["href"]
            url = href if href.startswith("http") else self.BASE_URL + href

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

        time_el = container.select_one("[class*='time']")
        time_str = time_el.get_text(strip=True) if time_el else ""

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


def scrape() -> List[Dict]:
    """Module-level entry point."""
    return AllSoulsScraper().safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  [{e['source']}] {e['name']} | {e['date']} | {e['venue']}")
    print(f"\nTotal: {len(results)} events")
