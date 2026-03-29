"""Scraper for public Facebook pages' events tabs.

Facebook pages often have an /events tab that lists upcoming events.
This scraper attempts to parse those pages for event information.
"""

import sys
import os
import re
import logging
from typing import List, Dict, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)


def scrape_facebook_page(page_url: str, source_name: str) -> List[Dict]:
    """Scrape a Facebook page's events tab for upcoming events.

    Args:
        page_url: The Facebook page URL (e.g. https://www.facebook.com/TheTulsaEagle/)
        source_name: Name to use as the source identifier

    Returns:
        List of event dicts with name, date, time, location, url, etc.
    """
    scraper = _SinglePageScraper(page_url, source_name)
    return scraper.safe_scrape()


class _SinglePageScraper(BaseScraper):
    """Internal scraper for a single Facebook page."""

    def __init__(self, page_url: str, source_name: str):
        super().__init__()
        self.page_url = page_url.rstrip("/")
        self.source_name = source_name
        # Facebook needs a more convincing browser signature
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/134.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        })

    def scrape(self) -> List[Dict]:
        events = []

        # Try the events tab first
        events_url = self.page_url + "/events/"
        soup = self.fetch_page(events_url)
        if soup:
            found = self._extract_events(soup)
            events.extend(found)

        # If no events from the events tab, try the main page
        if not events:
            self._random_delay()
            soup = self.fetch_page(self.page_url)
            if soup:
                found = self._extract_events(soup)
                events.extend(found)

        return events

    def _extract_events(self, soup) -> List[Dict]:
        """Extract events from a Facebook page.

        Facebook's HTML is heavily obfuscated and rendered client-side,
        so we try multiple approaches to find event information.
        """
        events = []

        # Strategy 1: Look for structured event data in meta tags / JSON-LD
        events.extend(self._parse_json_ld(soup))
        if events:
            return events

        # Strategy 2: Look for event cards with typical Facebook event patterns
        events.extend(self._parse_event_cards(soup))
        if events:
            return events

        # Strategy 3: Look for links to /events/ detail pages
        events.extend(self._parse_event_links(soup))
        if events:
            return events

        # Strategy 4: Look for any text content that resembles event listings
        events.extend(self._parse_text_content(soup))

        return events

    def _parse_json_ld(self, soup) -> List[Dict]:
        """Look for JSON-LD structured data about events."""
        import json
        events = []

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") in ("Event", "SocialEvent", "MusicEvent"):
                        name = item.get("name", "")
                        date_str = item.get("startDate", "")
                        location = item.get("location", {})
                        venue = ""
                        if isinstance(location, dict):
                            venue = location.get("name", "")
                        elif isinstance(location, str):
                            venue = location
                        url = item.get("url", "")
                        description = item.get("description", "")[:500] if item.get("description") else ""

                        # Parse date
                        parsed_date = ""
                        if date_str:
                            parsed_date = self.parse_date_flexible(date_str[:10])

                        events.append(self.make_event(
                            name=name,
                            date=parsed_date,
                            venue=venue,
                            description=description,
                            url=url,
                            priority=3,
                        ))
            except (json.JSONDecodeError, TypeError, AttributeError):
                continue

        return events

    def _parse_event_cards(self, soup) -> List[Dict]:
        """Look for event card patterns in the page."""
        events = []

        # Facebook event cards often have these patterns
        selectors = [
            "[data-testid*='event']",
            "[role='article']",
            "div[class*='event']",
            "div[class*='Event']",
        ]

        for selector in selectors:
            cards = soup.select(selector)
            for card in cards:
                name_el = card.select_one("span, h2, h3, a")
                if not name_el:
                    continue

                name = name_el.get_text(strip=True)
                if not name or len(name) < 5:
                    continue

                # Try to find date text
                date_str = ""
                time_str = ""
                text_content = card.get_text(" ", strip=True)

                date_match = re.search(
                    r'(\w+day,?\s+\w+ \d{1,2},?\s*\d{4}|\w+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4})',
                    text_content
                )
                if date_match:
                    date_str = self.parse_date_flexible(date_match.group(1))

                time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))', text_content)
                if time_match:
                    time_str = time_match.group(1)

                # Try to find a link
                link = card.find("a", href=True)
                url = ""
                if link:
                    href = link["href"]
                    if href.startswith("http"):
                        url = href
                    elif href.startswith("/"):
                        url = "https://www.facebook.com" + href

                events.append(self.make_event(
                    name=name,
                    date=date_str,
                    time=time_str,
                    url=url,
                    priority=3,
                ))

            if events:
                break

        return events

    def _parse_event_links(self, soup) -> List[Dict]:
        """Look for links to Facebook event pages."""
        events = []
        seen = set()

        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)

            # Look for links to /events/ detail pages
            if "/events/" in href and text and len(text) >= 5 and text not in seen:
                seen.add(text)
                full_url = href if href.startswith("http") else "https://www.facebook.com" + href
                events.append(self.make_event(
                    name=text,
                    date="",
                    url=full_url,
                    priority=3,
                ))

        return events

    def _parse_text_content(self, soup) -> List[Dict]:
        """Last resort: scan page text for event-like content."""
        events = []

        # Look for text blocks that mention events with dates
        for el in soup.find_all(["div", "span", "p"]):
            text = el.get_text(strip=True)
            if not text or len(text) < 10 or len(text) > 500:
                continue

            # Look for event-like patterns (date + event keywords)
            event_keywords = ["show", "drag", "karaoke", "bingo", "night", "party",
                              "performance", "live", "special", "pride", "benefit"]

            has_keyword = any(kw in text.lower() for kw in event_keywords)
            has_date = bool(re.search(
                r'(\w+day|\d{1,2}/\d{1,2}|\w+ \d{1,2})',
                text
            ))

            if has_keyword and has_date:
                # Try to extract the event name (first sentence or line)
                name = text.split(".")[0].split("\n")[0][:200]
                date_match = re.search(
                    r'(\w+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{4})',
                    text
                )
                date_str = self.parse_date_flexible(date_match.group(1)) if date_match else ""

                time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))', text)
                time_str = time_match.group(1) if time_match else ""

                events.append(self.make_event(
                    name=name,
                    date=date_str,
                    time=time_str,
                    priority=3,
                ))

        return events


class FacebookPageScraper(BaseScraper):
    """Scraper that handles multiple Facebook pages for events.

    Takes a list of (page_url, source_name, priority) tuples and scrapes
    each page for events.
    """

    source_name = "facebook"

    def __init__(self, pages: List[Tuple[str, str, int]]):
        """
        Args:
            pages: List of (page_url, source_name, priority) tuples.
                   e.g. [("https://www.facebook.com/TheTulsaEagle/", "tulsa_eagle", 3)]
        """
        super().__init__()
        self.pages = pages

    def scrape(self) -> List[Dict]:
        all_events = []

        for page_url, source_name, priority in self.pages:
            logger.info(f"[facebook] Scraping {source_name}: {page_url}")
            try:
                events = scrape_facebook_page(page_url, source_name)
                # Override priority from config
                for event in events:
                    event["priority"] = priority
                    event["source"] = source_name
                all_events.extend(events)
                logger.info(f"[facebook] {source_name}: {len(events)} events found")
            except Exception as e:
                logger.error(f"[facebook] {source_name}: FAILED - {e}", exc_info=True)

            self._random_delay()

        return all_events


def scrape() -> List[Dict]:
    """Module-level entry point. Scrapes all configured Facebook bar pages."""
    bar_pages = [
        (config.SOURCES["tulsa_eagle"]["url"], "tulsa_eagle", config.SOURCES["tulsa_eagle"]["priority"]),
        (config.SOURCES["ybr"]["url"], "ybr", config.SOURCES["ybr"]["priority"]),
        (config.SOURCES["majestic"]["url"], "majestic", config.SOURCES["majestic"]["priority"]),
    ]
    scraper = FacebookPageScraper(bar_pages)
    return scraper.safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  [{e['source']}] P{e['priority']} | {e['name']} | {e['date']}")
    print(f"\nTotal: {len(results)} events")
