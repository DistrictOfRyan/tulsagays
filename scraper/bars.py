"""Scraper for Tulsa LGBTQ+ bars: Tulsa Eagle, YBR, Majestic.

Primary method: Facebook page scraping (all three bars use Facebook as main platform).
Fallback: Website scraping if Facebook fails.
"""

import sys
import os
import re
import logging
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper.base import BaseScraper
from scraper.facebook_scraper import FacebookPageScraper, scrape_facebook_page

logger = logging.getLogger(__name__)

# Keywords that indicate a special event worth featuring
SPECIAL_KEYWORDS = [
    "special", "drag", "show", "benefit", "fundraiser", "pride",
    "contest", "pageant", "karaoke", "bingo", "brunch", "live",
    "performance", "charity", "anniversary", "holiday", "theme",
    "costume", "guest", "feature", "headline", "celebration",
]

# Bar Facebook pages and config
BAR_FACEBOOK_PAGES = [
    (config.SOURCES["tulsa_eagle"]["url"], "tulsa_eagle", config.SOURCES["tulsa_eagle"]["priority"]),
    (config.SOURCES["ybr"]["url"], "ybr", config.SOURCES["ybr"]["priority"]),
    (config.SOURCES["majestic"]["url"], "majestic", config.SOURCES["majestic"]["priority"]),
]

# Venue name mapping
VENUE_NAMES = {
    "tulsa_eagle": "Tulsa Eagle",
    "ybr": "Yellow Brick Road (YBR)",
    "majestic": "Majestic Night Club",
}


def _classify_event(name: str) -> tuple:
    """Return (priority, type) based on event name.

    Default: priority=3, type='bar_regular'
    If name contains special keywords: priority=2, type='bar_special'
    """
    name_lower = name.lower()
    for keyword in SPECIAL_KEYWORDS:
        if keyword in name_lower:
            return 2, "bar_special"
    return 3, "bar_regular"


def _apply_bar_classification(events: List[Dict]) -> List[Dict]:
    """Apply bar-specific event classification to events from Facebook scraping."""
    for event in events:
        priority, event_type = _classify_event(event.get("name", ""))
        event["event_type"] = event_type
        # Upgrade priority if it's a special event (but don't downgrade)
        if priority < event.get("priority", 99):
            event["priority"] = priority
        # Set venue name if not already set
        source = event.get("source", "")
        if source in VENUE_NAMES and not event.get("venue"):
            event["venue"] = VENUE_NAMES[source]
    return events


class TulsaEagleScraper(BaseScraper):
    """Scrape events from Tulsa Eagle (website fallback)."""

    source_name = "tulsa_eagle"

    # Fallback website URLs in case Facebook scraping fails
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

        return events

    def _extract_events(self, soup, base_url: str) -> List[Dict]:
        """Extract events from the page."""
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
            events = self._parse_generic(soup, base_url)

        return events

    def _parse_container(self, container, base_url: str) -> Dict | None:
        """Parse a structured event container."""
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

        desc_el = container.select_one("p, [class*='desc'], [class*='excerpt']")
        description = desc_el.get_text(strip=True)[:500] if desc_el else ""

        event = self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue="Tulsa Eagle",
            description=description,
            url=url,
            priority=priority,
        )
        event["event_type"] = event_type
        return event

    def _parse_generic(self, soup, base_url: str) -> List[Dict]:
        """Fallback generic parser for bar events."""
        events = []
        seen = set()

        for el in soup.find_all(["h2", "h3", "h4", "li"]):
            text = el.get_text(strip=True)
            if not text or len(text) < 5 or text in seen:
                continue

            skip = ["menu", "contact", "about", "home", "hours", "location", "address"]
            if any(s in text.lower() for s in skip):
                continue

            seen.add(text)
            priority, event_type = _classify_event(text)

            parent_text = el.parent.get_text(" ", strip=True) if el.parent else ""
            date_match = re.search(
                r'(\w+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}(?:/\d{2,4})?)',
                parent_text
            )
            date_str = self.parse_date_flexible(date_match.group(1)) if date_match else ""

            time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))', parent_text)
            time_str = time_match.group(1) if time_match else ""

            link = el.find("a", href=True)
            url = ""
            if link:
                href = link["href"]
                url = href if href.startswith("http") else base_url + href

            event = self.make_event(
                name=text,
                date=date_str,
                time=time_str,
                venue="Tulsa Eagle",
                url=url,
                priority=priority,
            )
            event["event_type"] = event_type
            events.append(event)

        return events


class YBRScraper(BaseScraper):
    """Scrape events from Yellow Brick Road (YBR) - website fallback."""

    source_name = "ybr"

    FALLBACK_URLS = [
        "https://www.ybrtulsa.com/events",
        "https://ybrtulsa.com/events",
        "https://www.ybrtulsa.com",
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
                return events

        logger.info("[ybr] No events found from fallback website.")
        return events

    def _extract_events(self, soup, base_url: str) -> List[Dict]:
        """Extract events from YBR page."""
        events = []

        containers = (
            soup.select(".event-item")
            or soup.select("[class*='event']")
            or soup.select(".summary-item")
        )

        for container in containers:
            name_el = container.select_one("h1, h2, h3, h4")
            if not name_el:
                continue

            name = name_el.get_text(strip=True)
            if not name:
                continue

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

            event = self.make_event(
                name=name,
                date=date_str,
                venue="Yellow Brick Road (YBR)",
                url=url,
                priority=priority,
            )
            event["event_type"] = event_type
            events.append(event)

        return events


class MajesticScraper(BaseScraper):
    """Scrape events from Majestic Night Club - website fallback."""

    source_name = "majestic"

    FALLBACK_URLS = [
        "https://www.majestictulsa.com/events",
        "https://majestictulsa.com/events",
        "https://www.majestictulsa.com",
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
                return events

        logger.info("[majestic] No events found from fallback website.")
        return events

    def _extract_events(self, soup, base_url: str) -> List[Dict]:
        """Extract events from Majestic page."""
        events = []

        containers = (
            soup.select(".event-item")
            or soup.select("[class*='event']")
            or soup.select(".summary-item")
        )

        for container in containers:
            name_el = container.select_one("h1, h2, h3, h4")
            if not name_el:
                continue

            name = name_el.get_text(strip=True)
            if not name:
                continue

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

            event = self.make_event(
                name=name,
                date=date_str,
                venue="Majestic Night Club",
                url=url,
                priority=priority,
            )
            event["event_type"] = event_type
            events.append(event)

        return events


def scrape() -> List[Dict]:
    """Module-level entry point. Scrapes all three bars.

    Primary: Facebook page scraping.
    Fallback: Individual website scrapers.
    """
    all_events = []

    # Primary method: Facebook scraping for all three bars
    logger.info("[bars] Trying Facebook scraping as primary method...")
    fb_scraper = FacebookPageScraper(BAR_FACEBOOK_PAGES)
    fb_events = fb_scraper.safe_scrape()
    fb_events = _apply_bar_classification(fb_events)

    # Track which bars got results from Facebook
    fb_sources = set(e.get("source") for e in fb_events)
    all_events.extend(fb_events)

    if fb_events:
        logger.info(f"[bars] Facebook scraping found {len(fb_events)} events from: {fb_sources}")

    # Fallback: website scraping for any bars that didn't return Facebook results
    fallback_scrapers = {
        "tulsa_eagle": TulsaEagleScraper,
        "ybr": YBRScraper,
        "majestic": MajesticScraper,
    }

    for source_name, scraper_cls in fallback_scrapers.items():
        if source_name not in fb_sources:
            logger.info(f"[bars] No Facebook results for {source_name}, trying website fallback...")
            scraper = scraper_cls()
            fallback_events = scraper.safe_scrape()
            all_events.extend(fallback_events)

    return all_events


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  [{e['source']}] P{e['priority']} {e.get('event_type', '')} | {e['name']} | {e['date']}")
    print(f"\nTotal: {len(results)} events")
