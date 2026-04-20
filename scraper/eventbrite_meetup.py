"""Scraper for Eventbrite and Meetup LGBTQ events in Tulsa.

Eventbrite primary path:
1. Public search API: https://www.eventbrite.com/api/v3/destination/search/
   - Returns JSON with events including start_date, start_time, venue.name
2. JSON-LD structured data from search result pages (fallback)
3. Event link extraction (last resort, no dates)

Meetup: JSON-LD from search pages + link extraction fallback.
"""

import sys
import os
import re
import json
import logging
import urllib.parse
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
    "sonic ray",  # The Sonic Ray — inclusive sound baths, community partner
]

LGBTQ_KEYWORDS = [
    "lgbtq", "lgbt", "queer", "gay", "lesbian", "bisexual", "trans",
    "transgender", "nonbinary", "non-binary", "drag", "pride", "rainbow",
    "equality", "homo", "sapphic", "two-spirit", "twospirit",
    "gender", "okeq", "sonic ray", "twisted arts", "council oak",
]

def _is_lgbtq_relevant(name: str, description: str = "", venue: str = "") -> bool:
    """Return True if any field contains an LGBTQ keyword."""
    combined = " ".join([name, description, venue]).lower()
    return any(kw in combined for kw in LGBTQ_KEYWORDS)

# Tulsa bounding box: SW lat/lon, NE lat/lon
# Format for Eventbrite API: "lat_min,lng_min,lat_max,lng_max"
TULSA_BBOX = "36.05,-96.05,36.25,-95.85"

EVENTBRITE_API = "https://www.eventbrite.com/api/v3/destination/search/"
EVENTBRITE_SEARCH_URL = "https://www.eventbrite.com/d/ok--tulsa/{query}/"


class EventbriteScraper(BaseScraper):
    """Search Eventbrite for Tulsa LGBTQ events.

    Primary: public search API (returns proper JSON with dates).
    Fallback 1: JSON-LD on search result pages.
    Fallback 2: Event link extraction (no dates, last resort).
    """

    source_name = "eventbrite"

    def scrape(self) -> List[Dict]:
        events = []
        seen_names = set()

        # Primary: API endpoint
        api_events = self._try_api()
        for event in api_events:
            key = event["name"].lower().strip()
            if key not in seen_names:
                seen_names.add(key)
                events.append(event)

        if events:
            logger.info(f"[eventbrite] API path: {len(events)} events with dates")
            return events

        # Fallback: scrape search pages for JSON-LD
        for term in SEARCH_TERMS:
            url = EVENTBRITE_SEARCH_URL.format(query=urllib.parse.quote(term))
            soup = self.fetch_page(url)
            if not soup:
                self._random_delay()
                continue

            found = self._extract_json_ld(soup)
            if not found:
                found = self._parse_links(soup)

            for event in found:
                key = event["name"].lower().strip()
                if key not in seen_names:
                    seen_names.add(key)
                    events.append(event)

            self._random_delay()

            if len(events) >= 30:
                break

        return events

    def _try_api(self) -> List[Dict]:
        """Try the Eventbrite public search API for each search term."""
        all_events = []
        seen = set()

        for term in SEARCH_TERMS:
            try:
                self._rotate_user_agent()
                resp = self.session.get(
                    EVENTBRITE_API,
                    params={
                        "page_size": 50,
                        "q": term,
                        "bbox": TULSA_BBOX,
                    },
                    timeout=15,
                )
                if resp.status_code != 200:
                    logger.debug(f"[eventbrite] API returned {resp.status_code} for '{term}'")
                    continue

                data = resp.json()
                # The API wraps results in various keys depending on version
                events_data = (
                    data.get("events", {}).get("results", [])
                    or data.get("results", [])
                    or data.get("events", [])
                )
                if isinstance(events_data, dict):
                    events_data = events_data.get("results", [])

                for item in events_data:
                    event = self._parse_api_event(item)
                    if not event:
                        continue
                    if not _is_lgbtq_relevant(event["name"], event.get("description", ""), event.get("venue", "")):
                        continue
                    key = event["name"].lower().strip()
                    if key not in seen:
                        seen.add(key)
                        all_events.append(event)

                self._random_delay()

                if len(all_events) >= 30:
                    break

            except Exception as e:
                logger.debug(f"[eventbrite] API request failed for '{term}': {e}")

        return all_events

    def _parse_api_event(self, item: dict) -> Optional[Dict]:
        """Parse one event from the Eventbrite API response."""
        # Item structure varies; try common keys
        name = item.get("name") or item.get("title", "")
        if isinstance(name, dict):
            name = name.get("text", "")
        if not name or len(name) < 5:
            return None

        # Dates
        start = item.get("start_date") or item.get("start", {})
        if isinstance(start, dict):
            date_str = start.get("local", "")[:10] if start.get("local") else ""
            time_str = start.get("local", "")[11:16] if start.get("local") and "T" in start.get("local", "") else ""
        elif isinstance(start, str):
            date_str = start[:10]
            time_str = ""
        else:
            date_str = ""
            time_str = ""

        # start_time separate field
        if not time_str:
            time_str = item.get("start_time", "")

        # Venue
        venue_data = item.get("venue") or item.get("primary_venue", {})
        venue = ""
        if isinstance(venue_data, dict):
            venue = venue_data.get("name", "") or venue_data.get("address", {}).get("localized_address_display", "")

        url = item.get("url") or item.get("eventbrite_url", "")
        if not url:
            event_id = item.get("id") or item.get("eid", "")
            if event_id:
                url = f"https://www.eventbrite.com/e/{event_id}"

        description = ""
        desc = item.get("description") or item.get("summary", "")
        if isinstance(desc, dict):
            description = desc.get("text", "")[:500]
        elif isinstance(desc, str):
            description = desc[:500]

        return self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue=venue,
            description=description,
            url=url,
            priority=2,
        )

    def _extract_json_ld(self, soup) -> List[Dict]:
        """Extract events from JSON-LD structured data on Eventbrite search pages."""
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
                    venue = ""
                    if isinstance(location, dict):
                        venue = location.get("name", "")
                    desc = item.get("description", "")[:300]
                    if not _is_lgbtq_relevant(name, desc, venue):
                        continue
                    events.append(self.make_event(
                        name=name,
                        date=date_str,
                        time=time_str,
                        venue=venue,
                        description=desc,
                        url=item.get("url", ""),
                        priority=2,
                    ))
            except (json.JSONDecodeError, TypeError):
                continue
        return events

    def _parse_links(self, soup) -> List[Dict]:
        """Fallback: look for event links on the page (no date, last resort)."""
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

        for term in SEARCH_TERMS[:4]:
            url = self.SEARCH_URL.format(query=urllib.parse.quote(term))
            soup = self.fetch_page(url, timeout=8)
            if not soup:
                self._random_delay()
                continue

            found = self._extract_json_ld(soup)
            if not found:
                found = self._parse_cards(soup)
            if not found:
                found = self._parse_links(soup)

            for event in found:
                key = event["name"].lower().strip()
                if key not in seen_names:
                    seen_names.add(key)
                    events.append(event)

            self._random_delay()

            if len(events) >= 20:
                break

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
                    location = item.get("location", {})
                    venue = ""
                    if isinstance(location, dict):
                        venue = location.get("name", "")
                    events.append(self.make_event(
                        name=name,
                        date=start[:10] if start else "",
                        venue=venue,
                        description=item.get("description", "")[:300],
                        url=item.get("url", ""),
                        priority=2,
                    ))
            except (json.JSONDecodeError, TypeError):
                continue
        return events

    def _parse_cards(self, soup) -> List[Dict]:
        events = []
        cards = (
            soup.select("[class*='eventCard']")
            or soup.select("[data-testid*='event']")
            or soup.select(".searchResult")
        )

        for card in cards:
            title_el = card.select_one("h2, h3, [class*='title'], [class*='name']")
            if not title_el:
                continue
            name = title_el.get_text(strip=True)
            if not name or len(name) < 5:
                continue

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

            events.append(self.make_event(
                name=name,
                date=date_str,
                time=time_str,
                venue=venue,
                url=url,
                priority=2,
            ))

        return events

    def _parse_links(self, soup) -> List[Dict]:
        events = []
        seen = set()
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)
            if "/events/" in href and text and len(text) > 10 and text not in seen:
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
    all_events.extend(EventbriteScraper().safe_scrape())
    all_events.extend(MeetupScraper().safe_scrape())
    return all_events


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  [{e['source']}] {e['name']} | {e['date']} | {e['venue']}")
    print(f"\nTotal: {len(results)} events")
