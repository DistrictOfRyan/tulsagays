"""Scraper for Twisted Arts / Twisted Fest events (twistedfest.org).

The site is WordPress + Divi. Events are rendered as headings with
plain-text context in the format:
  "[Name] Location: [Venue][Weekday], [Month] [Date] from [Time]–[Time]"

Uses BeautifulSoup + regex on the static HTML (no JS needed for content).
"""

import sys
import os
import re
import logging
from datetime import datetime
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

CURRENT_YEAR = datetime.now().year
DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _parse_date_time(context: str):
    """
    Parse date and time from context text like:
      'Saturday, May 2 from 7–9 PM'
      'Friday, March 27 from 7pm - 10pm'
      'Tuesday: March 31 from 7:00 – 9:00 PM'
      'Friday, April 17 & Saturday, April 18, 2026'
    Returns (date_str, time_str) as ('YYYY-MM-DD', 'H:MM AM/PM') or ('', '').
    """
    ctx = context.lower().replace('–', '-').replace('—', '-').replace('â', '-')

    # Find day-of-week as anchor
    day_pat = r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)[:\s,]+'
    day_m = re.search(day_pat, ctx)
    if not day_m:
        return '', ''

    rest = ctx[day_m.end():]

    # Extract month + day (+ optional year)
    month_day = re.search(
        r'(' + '|'.join(MONTHS.keys()) + r')\s+(\d{1,2})(?:,?\s*(\d{4}))?',
        rest
    )
    if not month_day:
        return '', ''

    month_name, day_num, year = month_day.group(1), int(month_day.group(2)), month_day.group(3)
    year = int(year) if year else CURRENT_YEAR
    month_num = MONTHS[month_name]

    # If the inferred date looks like it passed, bump year
    try:
        dt = datetime(year, month_num, int(day_num))
        today = datetime.now()
        if dt < today and year == CURRENT_YEAR:
            dt = datetime(year + 1, month_num, int(day_num))
        date_str = dt.strftime('%Y-%m-%d')
    except ValueError:
        return '', ''

    # Extract time after "from"
    time_str = ''
    time_m = re.search(r'from\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)', rest)
    if time_m:
        raw_time = time_m.group(1).strip()
        # Figure out AM/PM from later context
        period_m = re.search(r'from\s+\d[^a-z]*(am|pm)', rest)
        period = period_m.group(1).upper() if period_m else 'PM'
        # Normalise to "H:MM AM/PM"
        raw_time = re.sub(r'(am|pm)$', '', raw_time).strip()
        if ':' not in raw_time:
            raw_time += ':00'
        time_str = f'{raw_time} {period}'

    return date_str, time_str


class TwistedArtsScraper(BaseScraper):
    """Scrape events from twistedfest.org."""

    source_name = "twisted_arts"
    BASE_URL = "https://twistedfest.org"
    EVENTS_URL = "https://twistedfest.org/events/"

    def scrape(self) -> List[Dict]:
        soup = self.fetch_page(self.EVENTS_URL)
        if not soup:
            logger.warning("[twisted_arts] Could not fetch events page")
            return []

        events = []
        seen = set()

        headings = soup.find_all(['h2', 'h3', 'h4'])
        for h in headings:
            name = h.get_text(strip=True)
            if not name or len(name) < 4:
                continue
            if name in seen:
                continue

            # Skip navigation / section titles
            skip = {'events', 'upcoming', 'past events', 'menu', 'about', 'home', 'contact'}
            if name.lower() in skip:
                continue

            # Get surrounding context (parent div text)
            parent = h.find_parent(['div', 'section', 'article'])
            context = parent.get_text(' ', strip=True) if parent else ''

            # Extract venue (between "Location:" and first weekday)
            venue = ''
            loc_m = re.search(
                r'[Ll]ocation:\s*(.*?)(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)',
                context, re.IGNORECASE
            )
            if loc_m:
                venue = loc_m.group(1).strip().rstrip(',').strip()

            # Extract date + time
            date_str, time_str = _parse_date_time(context)

            if not date_str:
                logger.debug(f"[twisted_arts] No date found for: {name}")
                continue

            # Extract URL from heading link or nearby link
            link = h.find('a', href=True) or (parent and parent.find('a', href=True))
            url = ''
            if link:
                href = link['href']
                url = href if href.startswith('http') else self.BASE_URL + href

            # Short description (first sentence after "from [time]")
            desc = ''
            desc_m = re.search(r'(?:Join Twisted|Join us|Twisted Arts presents)(.*?)(?:read more|$)', context, re.IGNORECASE | re.DOTALL)
            if desc_m:
                desc = desc_m.group(0).replace('read more', '').strip()[:400]

            seen.add(name)
            events.append(self.make_event(
                name=name,
                date=date_str,
                time=time_str,
                venue=venue or 'Twisted Arts Tulsa',
                description=desc,
                url=url,
                priority=1,
            ))

        logger.info(f"[twisted_arts] Found {len(events)} events with dates")
        return events


def scrape() -> List[Dict]:
    return TwistedArtsScraper().safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scrape()
    for e in results:
        print(f"  {e['name']} | {e['date']} | {e.get('time','')} | {e['venue']}")
    print(f"\nTotal: {len(results)} events")
