"""Scraper for Eventbrite and Meetup LGBTQ events in Tulsa via public search pages."""

import sys
import os
import re
import logging
import urllib.parse
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_TERMS = [
    "lgbtq",
    "pride",
    "queer",
    "gay",
    "drag",
    "trans",
    "rainbow",
]


class EventbriteScraper(BaseScraper):
    """Search Eventbrite's public pages for Tulsa LGBTQ events."""

    source_name = "eventbrite"

    SEARCH_URL = "https://www.eventbrite.com/d/ok--tulsa/{query}/"

    def scrape(self) -> List[Dict]:
        events = []
        seen_names = set()

        for term in SEARCH_TERMS:
            url = self.SEARCH_URL.format(query=urllib.parse.quote(term))
            soup = self.fetch_page(url)
            if not soup:
                self._random_delay()
                continue

            found = self._extract_events(soup)
            for event in found:
                # Deduplicate within this scraper
                key = event["name"].lower().strip()
                if key not in seen_names:
                    seen_names.add(key)
                    events.append(event)

            self._random_delay()

            # Stop early if we have plenty of events
            if len(events) >= 30:
                break

        return events

    def _extract_events(self, soup) -> List[Dict]:
        """Extract events from Eventbrite search results."""
        events = []

        # Eventbrite search result cards
        cards = (
            soup.select("[data-testid='search-event-card']")
            or soup.select(".search-event-card-wrapper")
            or soup.select(".eds-event-card-content__content")
            or soup.select(".discover-search-desktop-card")
            or soup.select("article[class*='event']")
            or soup.select("[class*='SearchResultCard']")
        )

        for card in cards:
            event = self._parse_card(card)
            if event:
                events.append(event)

        # Fallback: look for any event-like structured data
        if not events:
            events = self._parse_json_ld(soup)

        # Fallback: generic link scraping
        if not events:
            events = self._parse_links(soup)

        return events

    def _parse_card(self, card) -> Dict | None:
        """Parse an Eventbrite event card."""
        # Title
        title_el = (
            card.select_one("[data-testid='event-card-title']")
            or card.select_one("h2, h3")
            or card.select_one(".eds-event-card-content__title")
            or card.select_one("[class*='title']")
        )
        if not title_el:
            return None

        name = title_el.get_text(strip=True)
        if not name or len(name) < 5:
            return None

        # URL
        link = card.find("a", href=True)
        url = ""
        if link:
            href = link["href"]
            # Clean tracking params
            url = href.split("?")[0] if "eventbrite.com" in href else href

        # Date
        date_el = (
            card.select_one("[data-testid='event-card-date']")
            or card.select_one("p[class*='date']")
            or card.select_one("[class*='date']")
        )
        date_str = ""
        time_str = ""
        if date_el:
            raw = date_el.get_text(strip=True)
            date_str = self.parse_date_flexible(raw)
            # Try to extract time
            time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))', raw)
            if time_match:
                time_str = time_match.group(1)

        # Location / venue
        venue_el = (
            card.select_one("[data-testid='event-card-venue']")
            or card.select_one("[class*='location']")
            or card.select_one("[class*='venue']")
        )
        venue = venue_el.get_text(strip=True) if venue_el else ""

        # Description (usually minimal in cards)
        desc_el = card.select_one("p:not([class*='date']):not([class*='venue'])")
        description = desc_el.get_text(strip=True)[:300] if desc_el else ""

        return self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue=venue,
            description=description,
            url=url,
            priority=2,
        )

    def _parse_json_ld(self, soup) -> List[Dict]:
        """Try to extract events from JSON-LD structured data."""
        import json
        events = []

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") == "Event":
                        name = item.get("name", "")
                        if not name:
                            continue

                        start = item.get("startDate", "")
                        date_str = start[:10] if start else ""
                        time_str = ""
                        if "T" in start:
                            time_str = start.split("T")[1][:5]

                        location = item.get("location", {})
                        venue = ""
                        if isinstance(location, dict):
                            venue = location.get("name", "")

                        events.append(self.make_event(
                            name=name,
                            date=date_str,
                            time=time_str,
                            venue=venue,
                            description=item.get("description", "")[:300],
                            url=item.get("url", ""),
                            priority=2,
                        ))
            except (json.JSONDecodeError, TypeError):
                continue

        return events

    def _parse_links(self, soup) -> List[Dict]:
        """Fallback: look for event links."""
        events = []
        seen = set()

        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)

            if (
                "eventbrite.com/e/" in href
                and text
                and len(text) > 10
                and text not in seen
            ):
                seen.add(text)
                events.append(self.make_event(
                    name=text,
                    date="",
                    url=href.split("?")[0],
                    priority=2,
                ))

        return events


class MeetupScraper(BaseScraper):
    """Search Meetup's public pages for Tulsa LGBTQ events."""

    source_name = "meetup"

    SEARCH_URL = "https://www.meetup.com/find/?keywords={query}&location=Tulsa%2C+OK"

    def scrape(self) -> List[Dict]:
        events = []
        seen_names = set()

        for term in SEARCH_TERMS[:4]:  # Meetup is stricter, fewer queries
            url = self.SEARCH_URL.format(query=urllib.parse.quote(term))
            soup = self.fetch_page(url)
            if not soup:
                self._random_delay()
                continue

            found = self._extract_events(soup)
            for event in found:
                key = event["name"].lower().strip()
                if key not in seen_names:
                    seen_names.add(key)
                    events.append(event)

            self._random_delay()

            if len(events) >= 20:
                break

        return events

    def _extract_events(self, soup) -> List[Dict]:
        """Extract events from Meetup search results."""
        events = []

        # Meetup search result cards
        cards = (
            soup.select("[class*='eventCard']")
            or soup.select("[data-testid*='event']")
            or soup.select(".searchResult")
            or soup.select("[id*='event']")
        )

        for card in cards:
            event = self._parse_card(card)
            if event:
                events.append(event)

        # Fallback: JSON-LD
        if not events:
            events = self._parse_json_ld(soup)

        # Fallback: links
        if not events:
            events = self._parse_links(soup)

        return events

    def _parse_card(self, card) -> Dict | None:
        """Parse a Meetup event card."""
        title_el = card.select_one("h2, h3, [class*='title'], [class*='name']")
        if not title_el:
            return None

        name = title_el.get_text(strip=True)
        if not name or len(name) < 5:
            return None

        link = card.find("a", href=True)
        url = ""
        if link:
            href = link["href"]
            url = href if href.startswith("http") else "https://www.meetup.com" + href

        date_el = card.select_one("time, [class*='date'], [class*='time']")
        date_str = ""
        time_str = ""
        if date_el:
            raw = date_el.get("datetime", "") or date_el.get_text(strip=True)
            if raw:
                date_str = self.parse_date_flexible(raw[:10] if len(raw) > 10 else raw)
                time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm))', raw)
                if time_match:
                    time_str = time_match.group(1)

        venue_el = card.select_one("[class*='venue'], [class*='location']")
        venue = venue_el.get_text(strip=True) if venue_el else ""

        return self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue=venue,
            url=url,
            priority=2,
        )

    def _parse_json_ld(self, soup) -> List[Dict]:
        """Try JSON-LD structured data."""
        import json
        events = []

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
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
                            venue=item.get("location", {}).get("name", "") if isinstance(item.get("location"), dict) else "",
                            description=item.get("description", "")[:300],
                            url=item.get("url", ""),
                            priority=2,
                        ))
            except (json.JSONDecodeError, TypeError):
                continue

        return events

    def _parse_links(self, soup) -> List[Dict]:
        """Fallback: event links."""
        events = []
        seen = set()

        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)
            if (
                "/events/" in href
                and text
                and len(text) > 10
                and text not in seen
            ):
                seen.add(text)
                full_url = href if href.startswith("http") else "https://www.meetup.com" + href
                events.append(self.make_event(
                    name=text,
                    date="",
                    url=full_url,
                    priority=2,
                ))

        return events


def scrape() -> List[Dict]:
    """Module-level entry point. Scrapes both Eventbrite and Meetup."""
    all_events = []

    eb = EventbriteScraper()
    all_events.extend(eb.safe_scrape())

    mu = MeetupScraper()
    all_events.extend(mu.safe_scrape())

    return all_events


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  [{e['source']}] {e['name']} | {e['date']} | {e['venue']}")
    print(f"\nTotal: {len(results)} events")
