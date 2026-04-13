"""Scraper for LGBTQ+ AA meetings in Tulsa via aaoklahoma.org.

Tries multiple approaches:
1. WordPress REST API: /wp-json/wp/v2/posts?per_page=50
2. Page HTML looking for tsml (12-step meeting list) JSON data in script tags
3. Direct page HTML parsing for meeting info
"""

import sys
import os
import json
import re
import logging
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://aaoklahoma.org"
MEETINGS_URL = "https://aaoklahoma.org/meetings/?tsml-day=any&tsml-region=tulsa&tsml-type=LGBTQ"
WP_API_URL = "https://aaoklahoma.org/wp-json/wp/v2/posts?per_page=50"
TSML_JSON_URL = "https://aaoklahoma.org/wp-json/tsml/v1/meetings?day=any&region=tulsa&type=LGBTQ"

TULSA_LGBTQ_MEETINGS = [
    {
        "name": "Lambda Unity Group (LGBTQ+ AA Meeting)",
        "day": "Wednesday",
        "time": "7:30 PM",
        "venue": "Fellowship Congregational Church, 2900 S Harvard Ave, Tulsa",
        "url": "https://aaoklahoma.org/meetings/lambda-unity/",
    },
]

DAY_MAP = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
    "Friday": 4, "Saturday": 5, "Sunday": 6,
}


class AAMeetingsScraper(BaseScraper):
    """Scrape LGBTQ AA meetings from aaoklahoma.org."""

    source_name = "aa_meetings"

    def scrape(self) -> List[Dict]:
        events = []

        # Strategy 1: TSML WordPress REST API (plugin-specific endpoint)
        events = self._try_tsml_api()
        if events:
            logger.info(f"[aa_meetings] TSML API found {len(events)} meetings")
            return events

        # Strategy 2: Page HTML for tsml JS data blocks
        events = self._try_page_json()
        if events:
            logger.info(f"[aa_meetings] Page JSON found {len(events)} meetings")
            return events

        # Strategy 3: Generic page HTML parsing
        events = self._try_html_parsing()
        if events:
            logger.info(f"[aa_meetings] HTML parsing found {len(events)} meetings")
            return events

        # Fallback: hardcoded known meetings for this week
        logger.info("[aa_meetings] Live scraping failed -- using hardcoded known meetings")
        events = self._hardcoded_meetings()
        return events

    def _try_tsml_api(self) -> List[Dict]:
        """Try the 12-step meeting list plugin REST endpoint."""
        data = self.fetch_json(TSML_JSON_URL)
        if not data:
            return []

        meetings = data if isinstance(data, list) else data.get("meetings", [])
        if not meetings:
            return []

        events = []
        for m in meetings:
            event = self._parse_tsml_meeting(m)
            if event:
                events.append(event)
        return events

    def _parse_tsml_meeting(self, m: dict) -> Optional[Dict]:
        name = m.get("name", "")
        if not name:
            return None

        day_name = m.get("day", "")
        time_str = m.get("time", "")
        location = m.get("location", "") or m.get("address", "")
        city = m.get("city", "")
        url = m.get("url", "") or BASE_URL

        # Only include Tulsa meetings
        if city and "tulsa" not in city.lower():
            return None

        venue = location
        if city and city not in venue:
            venue = f"{venue}, {city}" if venue else city

        # We store as recurring (no fixed date); priority=3
        date_str = self._day_to_date_this_week(day_name)

        return self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue=venue or "Tulsa, OK",
            url=url,
            priority=3,
        )

    def _try_page_json(self) -> List[Dict]:
        """Look for tsml meeting data in inline script tags on the page."""
        soup = self.fetch_page(MEETINGS_URL)
        if not soup:
            return []

        events = []
        for script in soup.find_all("script"):
            content = script.string or ""
            if "tsml" not in content.lower():
                continue

            # TSML inlines meeting data as a JSON object assigned to a JS var
            # e.g. var tsml = {"meetings": [...]}
            match = re.search(r'var\s+\w*tsml\w*\s*=\s*(\{.*?\});', content, re.DOTALL)
            if not match:
                # Try alternate pattern
                match = re.search(r'"meetings"\s*:\s*(\[.*?\])', content, re.DOTALL)

            if match:
                try:
                    raw = match.group(1)
                    data = json.loads(raw)
                    meetings = data if isinstance(data, list) else data.get("meetings", [])
                    for m in meetings:
                        event = self._parse_tsml_meeting(m)
                        if event:
                            events.append(event)
                    if events:
                        break
                except json.JSONDecodeError:
                    continue

        self._random_delay()
        return events

    def _try_html_parsing(self) -> List[Dict]:
        """Parse the meetings page HTML for table or list rows."""
        soup = self.fetch_page(MEETINGS_URL)
        if not soup:
            return []

        events = []

        # TSML often renders a table
        rows = soup.select("table tr") or soup.select(".tsml-meeting") or soup.select("[class*='meeting']")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                # Try as a div-based row
                name_el = row.select_one(".name, h2, h3, strong, a")
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                if not name or len(name) < 5:
                    continue
                text = row.get_text(" ", strip=True)
                day_match = re.search(r'\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b', text)
                day_name = day_match.group(1) if day_match else ""
                time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM))', text, re.IGNORECASE)
                time_str = time_match.group(1) if time_match else ""
                events.append(self.make_event(
                    name=name,
                    date=self._day_to_date_this_week(day_name),
                    time=time_str,
                    venue="Tulsa, OK",
                    url=MEETINGS_URL,
                    priority=3,
                ))
                continue

            # Table row: columns typically: Day | Time | Name | Location
            text_cells = [c.get_text(strip=True) for c in cells]
            if len(text_cells) >= 3:
                name = text_cells[2] if len(text_cells) > 2 else text_cells[0]
                day_name = text_cells[0] if text_cells else ""
                time_str = text_cells[1] if len(text_cells) > 1 else ""
                events.append(self.make_event(
                    name=name,
                    date=self._day_to_date_this_week(day_name),
                    time=time_str,
                    venue="Tulsa, OK",
                    url=MEETINGS_URL,
                    priority=3,
                ))

        self._random_delay()
        return events

    def _hardcoded_meetings(self) -> List[Dict]:
        """Return known LGBTQ AA meetings with dates for the current week."""
        from datetime import datetime, timedelta
        today = datetime.now()
        monday = today - timedelta(days=today.weekday())
        week_dates = {(monday + timedelta(days=i)).strftime("%A"): (monday + timedelta(days=i)) for i in range(7)}

        events = []
        for m in TULSA_LGBTQ_MEETINGS:
            day_name = m["day"]
            date_obj = week_dates.get(day_name)
            if date_obj:
                events.append(self.make_event(
                    name=m["name"],
                    date=date_obj.strftime("%Y-%m-%d"),
                    time=m["time"],
                    venue=m["venue"],
                    url=m["url"],
                    priority=3,
                ))
        return events

    def _day_to_date_this_week(self, day_name: str) -> str:
        """Convert a weekday name to the date of that day in the current week."""
        if not day_name:
            return ""
        from datetime import datetime, timedelta
        target_wd = DAY_MAP.get(day_name.strip().capitalize())
        if target_wd is None:
            return ""
        today = datetime.now()
        monday = today - timedelta(days=today.weekday())
        target_date = monday + timedelta(days=target_wd)
        return target_date.strftime("%Y-%m-%d")


def scrape() -> List[Dict]:
    """Module-level entry point."""
    return AAMeetingsScraper().safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  {e['date']} | {e['name']} | {e['time']} | {e['venue']}")
    print(f"\nTotal: {len(results)} events")
