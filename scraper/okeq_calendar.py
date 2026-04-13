"""Dedicated scraper for okeq.org/event-calendar/ (Dennis R. Neill Equality Center).

Tries multiple approaches in order:
1. Squarespace format=json API
2. JSON-LD structured data on the page
3. .eventlist-event HTML elements with datetime attributes
4. Follow individual event links and extract dates from detail pages
"""

import sys
import os
import json
import re
import logging
import time
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://okeq.org"
CALENDAR_URL = "https://okeq.org/event-calendar/"
JSON_API_URL = "https://okeq.org/event-calendar/?format=json-pretty"
ALT_JSON_API_URL = "https://okeq.org/events?format=json-pretty"


class OKEQCalendarScraper(BaseScraper):
    """Scrape okeq.org event calendar with multiple fallback strategies."""

    source_name = "okeq_calendar"

    def scrape(self) -> List[Dict]:
        events = []

        # Strategy 1: Squarespace JSON API
        events = self._try_squarespace_api(CALENDAR_URL)
        if events:
            logger.info(f"[okeq_calendar] Strategy 1 (JSON API) found {len(events)} events")
            return events

        # Strategy 2: Try alternate JSON endpoint
        events = self._try_squarespace_api(ALT_JSON_API_URL)
        if events:
            logger.info(f"[okeq_calendar] Strategy 2 (alt JSON API) found {len(events)} events")
            return events

        # Strategy 3: JSON-LD from the HTML page
        events = self._try_json_ld()
        if events:
            logger.info(f"[okeq_calendar] Strategy 3 (JSON-LD) found {len(events)} events")
            return events

        # Strategy 4: Parse HTML event list elements
        events = self._try_html_parsing()
        if events:
            logger.info(f"[okeq_calendar] Strategy 4 (HTML parsing) found {len(events)} events")
            return events

        logger.warning("[okeq_calendar] All strategies returned 0 events -- site may need manual review")
        return []

    def _try_squarespace_api(self, base_url: str) -> List[Dict]:
        """Try Squarespace's format=json-pretty API endpoint."""
        url = base_url if "format=json" in base_url else base_url + "?format=json-pretty"
        try:
            self._rotate_user_agent()
            logger.info(f"[okeq_calendar] Trying Squarespace JSON API: {url}")
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()

            # Squarespace returns JSON with an "items" array
            data = resp.json()
            items = data.get("items", [])
            if not items and isinstance(data, list):
                items = data

            events = []
            for item in items:
                event = self._parse_squarespace_item(item)
                if event:
                    events.append(event)
            return events

        except Exception as e:
            logger.debug(f"[okeq_calendar] Squarespace API failed for {url}: {e}")
            return []

    def _parse_squarespace_item(self, item: dict) -> Optional[Dict]:
        """Parse a single Squarespace event item."""
        try:
            name = item.get("title", "")
            if not name:
                return None

            # Squarespace stores timestamps in milliseconds
            start_ts = item.get("startDate") or item.get("publishOn")
            date_str = ""
            time_str = ""
            if start_ts:
                try:
                    # Millisecond timestamp
                    ts = int(start_ts)
                    if ts > 1e10:  # ms timestamp
                        ts = ts / 1000
                    from datetime import datetime
                    dt = datetime.utcfromtimestamp(ts)
                    date_str = dt.strftime("%Y-%m-%d")
                    time_str = dt.strftime("%I:%M %p")
                except (ValueError, OSError):
                    pass

            # Try ISO string format too
            if not date_str:
                start_iso = item.get("startDateIso") or item.get("startDateFormatted", "")
                if start_iso:
                    date_str = self.parse_date_flexible(start_iso[:10])

            url = item.get("fullUrl", "") or item.get("absUrl", "")
            if url and not url.startswith("http"):
                url = BASE_URL + url

            location = item.get("location", {})
            venue = ""
            if isinstance(location, dict):
                venue = location.get("addressLine1") or location.get("mapAddress", "") or "Dennis R. Neill Equality Center"
            if not venue:
                venue = "Dennis R. Neill Equality Center"

            body = item.get("body", "") or ""
            description = re.sub(r'<[^>]+>', '', body)[:500] if body else ""

            return self.make_event(
                name=name,
                date=date_str,
                time=time_str,
                venue=venue,
                description=description,
                url=url,
                priority=1,
            )
        except Exception as e:
            logger.debug(f"[okeq_calendar] Failed to parse Squarespace item: {e}")
            return None

    def _try_json_ld(self) -> List[Dict]:
        """Extract events from JSON-LD structured data on the calendar page."""
        soup = self.fetch_page(CALENDAR_URL)
        if not soup:
            return []

        events = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw = script.string
                if not raw:
                    continue
                data = json.loads(raw)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") == "Event":
                        event = self._parse_json_ld_item(item)
                        if event:
                            events.append(event)
            except (json.JSONDecodeError, TypeError):
                continue

        self._random_delay()
        return events

    def _parse_json_ld_item(self, item: dict) -> Optional[Dict]:
        """Parse a JSON-LD Event object."""
        name = item.get("name", "")
        if not name:
            return None

        start = item.get("startDate", "")
        date_str = start[:10] if start else ""
        time_str = ""
        if "T" in start:
            time_str = start.split("T")[1][:5]

        location = item.get("location", {})
        venue = ""
        if isinstance(location, dict):
            venue = location.get("name", "")

        url = item.get("url", "")
        description = item.get("description", "")[:500]

        return self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue=venue or "Dennis R. Neill Equality Center",
            description=description,
            url=url,
            priority=1,
        )

    def _try_html_parsing(self) -> List[Dict]:
        """Parse .eventlist-event elements and datetime attributes from the HTML."""
        soup = self.fetch_page(CALENDAR_URL)
        if not soup:
            return []

        events = []

        # Squarespace event list pattern
        containers = (
            soup.select(".eventlist-event")
            or soup.select("article.eventlist-event--upcoming")
            or soup.select(".summary-item[data-type='event']")
        )

        for container in containers:
            event = self._parse_html_container(container)
            if event:
                events.append(event)

        # If still nothing, try scraping individual event detail links
        if not events:
            events = self._follow_event_links(soup)

        self._random_delay()
        return events

    def _parse_html_container(self, container) -> Optional[Dict]:
        """Parse a single Squarespace event container from HTML."""
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

        link_el = name_el.find("a") or container.find("a")
        url = ""
        if link_el and link_el.get("href"):
            href = link_el["href"]
            url = href if href.startswith("http") else BASE_URL + href

        # Date -- Squarespace puts ISO dates in datetime attrs
        date_el = (
            container.select_one("time[datetime]")
            or container.select_one(".eventlist-datetag-startdate")
            or container.select_one(".event-date")
        )
        date_str = ""
        if date_el:
            raw = date_el.get("datetime", "") or date_el.get_text(strip=True)
            if raw:
                date_str = self.parse_date_flexible(raw[:10] if len(raw) > 10 else raw)

        time_el = (
            container.select_one(".eventlist-meta-time")
            or container.select_one(".event-time-12hr")
        )
        time_str = time_el.get_text(strip=True) if time_el else ""

        desc_el = (
            container.select_one(".eventlist-description")
            or container.select_one(".summary-excerpt")
        )
        description = desc_el.get_text(strip=True)[:500] if desc_el else ""

        return self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue="Dennis R. Neill Equality Center, 621 E 4th St",
            description=description,
            url=url,
            priority=1,
        )

    def _follow_event_links(self, soup) -> List[Dict]:
        """Follow event detail links from the calendar page to get dates."""
        events = []
        seen_urls = set()

        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)

            # okeq.org event URLs contain /event-calendar/ or /okeq-events/
            if not any(p in href for p in ["/event-calendar/", "/okeq-events/", "/events/"]):
                continue
            if not text or len(text) < 5:
                continue

            full_url = href if href.startswith("http") else BASE_URL + href
            if full_url in seen_urls or full_url == CALENDAR_URL:
                continue
            seen_urls.add(full_url)

            if len(events) >= 10:  # Limit detail page fetches
                break

            detail_soup = self.fetch_page(full_url)
            if not detail_soup:
                time.sleep(1)
                continue

            date_str = self._extract_date_from_detail(detail_soup)

            events.append(self.make_event(
                name=text,
                date=date_str,
                venue="Dennis R. Neill Equality Center, 621 E 4th St",
                url=full_url,
                priority=1,
            ))
            self._random_delay()

        return events

    def _extract_date_from_detail(self, soup) -> str:
        """Extract the start date from an event detail page."""
        # JSON-LD first
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") == "Event":
                        start = item.get("startDate", "")
                        if start:
                            return start[:10]
            except Exception:
                continue

        # time[datetime] attribute
        time_el = soup.select_one("time[datetime]")
        if time_el:
            raw = time_el.get("datetime", "")
            if raw:
                return self.parse_date_flexible(raw[:10])

        # .eventlist-datetag text
        datetag = soup.select_one(".eventlist-datetag")
        if datetag:
            return self.parse_date_flexible(datetag.get_text(strip=True))

        return ""


def scrape() -> List[Dict]:
    """Module-level entry point."""
    return OKEQCalendarScraper().safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  {e['date']} | {e['name']} | {e['venue']}")
    print(f"\nTotal: {len(results)} events")
