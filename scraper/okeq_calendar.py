"""Scraper for okeq.org/event-calendar/ (Oklahomans for Equality).

okeq.org is WordPress + Simple Calendar (google-calendar-events plugin v3.x).
Events are pre-rendered in the initial HTML as li.simcal-event elements and
fetched for additional months via AJAX.

AJAX endpoint: POST /wp-admin/admin-ajax.php
  action=simcal_default_calendar_draw_grid
  month=<1-12>
  year=<YYYY>
  id=<calendar_post_id>   (discovered from data-calendar-id attribute)
"""

import sys
import os
import re
import json
import logging
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

CALENDAR_URL = "https://okeq.org/event-calendar/"
AJAX_URL = "https://okeq.org/wp-admin/admin-ajax.php"

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}

# Garbage names that OKEQ renders as nav links / page artifacts
_GARBAGE = {
    "event calendar", "bruce goff event center", "event application",
    "our partners", "stay connected", "stay connected!",
}


class OKEQCalendarScraper(BaseScraper):
    """Scrape okeq.org event calendar via Simple Calendar HTML + AJAX."""

    source_name = "okeq"

    def scrape(self) -> List[Dict]:
        soup = self.fetch_page(CALENDAR_URL)
        if not soup:
            logger.warning("[okeq] Could not fetch calendar page")
            return []

        # Discover calendar post ID from the widget's data attribute
        cal_div = soup.find("div", attrs={"data-calendar-id": True})
        cal_id = cal_div["data-calendar-id"] if cal_div else "5945"
        logger.info(f"[okeq] Calendar post ID: {cal_id}")

        # Parse events already in the initial HTML (current month)
        events_by_key: dict = {}
        self._parse_events_from_soup(soup, events_by_key)
        logger.info(f"[okeq] Initial page: {len(events_by_key)} events")

        # Always fetch the next month too (weekly scrapes span month boundaries)
        today = date.today()
        months_to_fetch = self._months_to_fetch(today)
        for month, year in months_to_fetch:
            extra = self._fetch_month_ajax(cal_id, month, year)
            before = len(events_by_key)
            self._parse_events_from_soup(extra, events_by_key)
            logger.info(f"[okeq] Month {year}-{month:02d}: +{len(events_by_key)-before} new events")
            self._random_delay()

        result = list(events_by_key.values())
        logger.info(f"[okeq] Total events scraped: {len(result)}")
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _months_to_fetch(self, today: date) -> List[Tuple[int, int]]:
        """Return (month, year) pairs to fetch via AJAX beyond the current page."""
        months = []
        # Always get next month (current week may extend into it)
        if today.month == 12:
            months.append((1, today.year + 1))
        else:
            months.append((today.month + 1, today.year))
        return months

    def _fetch_month_ajax(self, cal_id: str, month: int, year: int):
        """Fetch a calendar month via the Simple Calendar AJAX endpoint."""
        try:
            resp = self.session.post(AJAX_URL, data={
                "action": "simcal_default_calendar_draw_grid",
                "month": str(month),
                "year": str(year),
                "id": cal_id,
            }, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                logger.warning(f"[okeq] AJAX {year}-{month:02d} not successful: {data.get('data','')[:100]}")
                return None
            from bs4 import BeautifulSoup
            return BeautifulSoup(data["data"], "html.parser")
        except Exception as e:
            logger.warning(f"[okeq] AJAX failed for {year}-{month:02d}: {e}")
            return None

    def _parse_events_from_soup(self, soup, events_by_key: dict) -> None:
        """Extract events from a BeautifulSoup object and add to events_by_key."""
        if not soup:
            return
        for li in soup.find_all("li", class_="simcal-event"):
            event = self._parse_event_li(li)
            if not event:
                continue
            key = f"{event['date']}|{event['name'].lower()}"
            if key not in events_by_key:
                events_by_key[key] = event

    def _parse_event_li(self, li) -> Optional[Dict]:
        title_el = li.find("span", class_="simcal-event-title")
        if not title_el:
            return None
        name = title_el.get_text(strip=True)
        if not name or len(name) < 4:
            return None
        if name.lower() in _GARBAGE:
            return None

        details_el = li.find("div", class_="simcal-event-details")
        details_text = details_el.get_text(" ", strip=True) if details_el else ""

        # Date: "May 1, 2026 | 9:00 am - 4:00 pm"
        date_m = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)"
            r"\s+(\d{1,2}),?\s+(\d{4})",
            details_text,
        )
        if not date_m:
            return None
        month_name = date_m.group(1).lower()
        day = int(date_m.group(2))
        year = int(date_m.group(3))
        date_str = f"{year}-{MONTHS[month_name]:02d}-{day:02d}"

        # Time: first "H:MM am/pm" token
        time_m = re.search(r"(\d{1,2}:\d{2}\s*(?:am|pm))", details_text, re.IGNORECASE)
        time_str = time_m.group(1).upper() if time_m else ""

        # URL
        link = li.find("a", href=True)
        url = link["href"] if link else ""
        if url and not url.startswith("http"):
            url = "https://okeq.org" + url

        # Description: full details text minus the title
        desc = details_text.replace(name, "").strip()[:400]

        return self.make_event(
            name=name,
            date=date_str,
            time=time_str,
            venue="Dennis R. Neill Equality Center, 621 E 4th St",
            description=desc,
            url=url,
            priority=1,
        )


def scrape() -> List[Dict]:
    return OKEQCalendarScraper().safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scrape()
    results.sort(key=lambda e: e["date"])
    for e in results:
        print(f"  {e['date']} | {e['name'][:55]:55} | {e.get('time', '')}")
    print(f"\nTotal: {len(results)} events")
