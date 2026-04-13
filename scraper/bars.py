"""Scraper for Tulsa LGBTQ+ bars: Tulsa Eagle.

NOTE: YBR (ybrtulsa.com), Majestic (majestictulsa.com), Studio 66 (s66tulsa.com),
and Tulsa House of Drag (tulsahouseofdrag.com) are DNS-dead as of 2026 and have
been removed. Tulsa Eagle website is attempted as a fallback.

Facebook scraping is disabled (blocked). Check bar Facebook pages manually:
- Tulsa Eagle: https://www.facebook.com/TheTulsaEagle/
- YBR: https://www.facebook.com/YBRTulsa/
- Club Majestic: https://www.facebook.com/clubmajestictulsa/
"""

import sys
import os
import re
import logging
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

SPECIAL_KEYWORDS = [
    "special", "drag", "show", "benefit", "fundraiser", "pride",
    "contest", "pageant", "karaoke", "bingo", "brunch", "live",
    "performance", "charity", "anniversary", "holiday", "theme",
    "costume", "guest", "feature", "headline", "celebration",
]


def _classify_event(name: str) -> tuple:
    """Return (priority, type) based on event name."""
    name_lower = name.lower()
    for keyword in SPECIAL_KEYWORDS:
        if keyword in name_lower:
            return 2, "bar_special"
    return 3, "bar_regular"


class TulsaEagleScraper(BaseScraper):
    """Scrape events from Tulsa Eagle website."""

    source_name = "tulsa_eagle"

    FALLBACK_URLS = [
        "https://www.tulsaeagle.com/events",
        "https://www.tulsaeagle.com/calendar",
        "https://www.tulsaeagle.com",
    ]

    def scrape(self) -> List[Dict]:
        events = []

        for url in self.FALLBACK_URLS:
            soup = self.fetch_page(url)
            if not soup:
                continue

            found = self._extract_events(soup, url)
            events.extend(found)
            self._random_delay()

            if events:
                break

        if not events:
            logger.info(
                "[tulsa_eagle] No events found. "
                "Check manually: https://www.facebook.com/TheTulsaEagle/"
            )

        return events

    def _extract_events(self, soup, base_url: str) -> List[Dict]:
        events = []

        containers = (
            soup.select(".event-item")
            or soup.select(".eventlist-event")
            or soup.select("[class*='event']")
            or soup.select(".summary-item")
        )

        for container in containers:
            event = self._parse_container(container, base_url)
            if event:
                events.append(event)

        if not events:
            events = self._parse_json_ld(soup)

        return events

    def _parse_json_ld(self, soup) -> List[Dict]:
        import json
        events = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") == "Event":
                        name = item.get("name", "")
                        if not name:
                            continue
                        start = item.get("startDate", "")
                        events.append(self.make_event(
                            name=name,
                            date=start[:10] if start else "",
                            venue="Tulsa Eagle",
                            url=item.get("url", ""),
                            priority=3,
                        ))
            except Exception:
                continue
        return events

    def _parse_container(self, container, base_url: str) -> Dict | None:
        name_el = container.select_one("h1, h2, h3, h4, .event-title, .summary-title")
        if not name_el:
            return None

        name = name_el.get_text(strip=True)
        if not name or len(name) < 3:
            return None

        priority, event_type = _classify_event(name)

        link = container.find("a", href=True)
        url = ""
        if link:
            href = link["href"]
            url = href if href.startswith("http") else base_url + href

        date_el = container.select_one("time, [class*='date']")
        date_str = ""
        if date_el:
            date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)
        date_str = self.parse_date_flexible(date_str)

        time_el = container.select_one("[class*='time']")
        time_str = time_el.get_text(strip=True) if time_el else ""

        event = self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue="Tulsa Eagle",
            url=url,
            priority=priority,
        )
        event["event_type"] = event_type
        return event


def scrape() -> List[Dict]:
    """Module-level entry point."""
    logger.info("[bars] Note: YBR, Majestic, Studio 66, Tulsa House of Drag DNS-dead. Tulsa Eagle only.")
    scraper = TulsaEagleScraper()
    return scraper.safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  [{e['source']}] P{e['priority']} | {e['name']} | {e['date']}")
    print(f"\nTotal: {len(results)} events")
