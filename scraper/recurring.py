"""Hardcoded recurring LGBTQ+ events for Tulsa.

Calculates which events fall in the current week (Monday-Sunday) and returns
them with proper YYYY-MM-DD dates. No scraping needed -- these are known,
stable recurring events.
"""

import sys
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

# freq options: "weekly", "1st", "2nd", "3rd"
# day: full weekday name matching Python's strftime %A
RECURRING = [
    # Weekly
    {
        "name": "Lambda Bowling League",
        "day": "Monday",
        "freq": "weekly",
        "time": "7:00 PM",
        "venue": "AMF Sheridan Lanes, 3121 S Sheridan Rd",
        "url": "https://www.facebook.com/groups/4177858394",
        "priority": 1,
    },
    {
        "name": "OSU Tulsa Queer Support Group",
        "day": "Tuesday",
        "freq": "weekly",
        "time": "6:00 PM",
        "venue": "OSU Tulsa Campus, 700 N Greenwood Ave",
        "url": "https://events.tulsa.okstate.edu",
        "priority": 1,
    },
    {
        "name": "Gender Outreach Support Group",
        "day": "Wednesday",
        "freq": "weekly",
        "time": "7:00 PM - 9:00 PM",
        "venue": "Dennis R. Neill Equality Center, 621 E 4th St",
        "url": "https://okeq.org",
        "priority": 1,
    },
    {
        "name": "Lambda Unity Group (LGBTQ+ AA Meeting)",
        "day": "Wednesday",
        "freq": "weekly",
        "time": "Check listing for time",
        "venue": "Fellowship Congregational Church, Tulsa",
        "url": "https://aaoklahoma.org/meetings/lambda-unity/",
        "priority": 3,
    },
    {
        "name": "DRAGNIFICENT! Drag Show",
        "day": "Thursday",
        "freq": "weekly",
        "time": "Doors 9 PM, Show 10 PM",
        "venue": "Club Majestic, 124 N Boston Ave",
        "url": "https://downtowntulsa.com/do/dragnificent-at-club-majestic-1",
        "priority": 1,
    },
    {
        "name": "Sunday Showdown Open Talent Night",
        "day": "Sunday",
        "freq": "weekly",
        "time": "Doors 9 PM, Show 11 PM",
        "venue": "Club Majestic, 124 N Boston Ave",
        "url": "https://qlist.app/events/Tulsa/The-Sunday-Showdown-Open-Talent-Night-at-Club-Majestic/16808",
        "priority": 1,
    },
    {
        "name": "All Souls Unitarian Sunday Services",
        "day": "Sunday",
        "freq": "weekly",
        "time": "10:00 AM and 11:15 AM",
        "venue": "All Souls Unitarian Church, 2952 S Peoria Ave",
        "url": "https://allsoulschurch.org",
        "priority": 2,
    },
    # 1st occurrence of the month
    {
        "name": "Homo Hotel Happy Hour (HHHH)",
        "day": "Friday",
        "freq": "1st",
        "time": "6:00 PM - 8:00 PM",
        "venue": "DoubleTree by Hilton Tulsa Downtown, 616 W 7th St",
        "url": "https://www.meetup.com/homo-hotel-happy-hour/",
        "priority": 1,
    },
    {
        "name": "PFLAG Tulsa Monthly Meeting",
        "day": "Saturday",
        "freq": "1st",
        "time": "7:00 PM",
        "venue": "110 S Hartford Ave, Tulsa",
        "url": "https://pflag.org/chapter/pflag-tulsa",
        "priority": 1,
    },
    {
        "name": "Queer Women's Collective",
        "day": "Wednesday",
        "freq": "1st",
        "time": "Evening",
        "venue": "Dennis R. Neill Equality Center, 621 E 4th St",
        "url": "https://www.facebook.com/queerwomenscollectivetulsa",
        "priority": 1,
    },
    {
        "name": "Relationships Outside the Box",
        "day": "Thursday",
        "freq": "1st",
        "time": "7:00 PM - 8:00 PM",
        "venue": "Dennis R. Neill Equality Center, 621 E 4th St",
        "url": "https://okeq.org/okeq-events/relationships-outside-the-box",
        "priority": 1,
    },
    # 2nd occurrence of the month
    {
        "name": "Tulsa Area Prime Timers",
        "day": "Tuesday",
        "freq": "2nd",
        "time": "7:00 PM",
        "venue": "Dennis R. Neill Equality Center, 621 E 4th St",
        "url": "https://okeq.org",
        "priority": 2,
    },
    {
        "name": "Elote Drag Brunch",
        "day": "Saturday",
        "freq": "2nd",
        "time": "11:00 AM and 1:30 PM (two seatings)",
        "venue": "Elote Cafe & Catering, 514 S Boston Ave",
        "url": "https://www.eventbrite.com/o/elote-cafe-catering-17620608823",
        "priority": 1,
    },
    {
        "name": "Green Country Bears Monthly Meetup",
        "day": "Thursday",
        "freq": "2nd",
        "time": "7:00 PM",
        "venue": "Restaurant varies -- check greencountrybears.com",
        "url": "https://greencountrybears.com",
        "priority": 2,
    },
    # 3rd occurrence of the month
    {
        "name": "Black Queer Tulsa Monthly Brunch",
        "day": "Sunday",
        "freq": "3rd",
        "time": "Check website for time",
        "venue": "Various locations, Tulsa",
        "url": "https://www.blackqueertulsa.org/events",
        "priority": 1,
    },
]

# Day name -> weekday number (Monday=0)
DAY_MAP = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}

# Occurrence -> day-of-month range
OCCURRENCE_RANGES = {
    "1st": (1, 7),
    "2nd": (8, 14),
    "3rd": (15, 21),
    "4th": (22, 28),
}


def _get_week_dates(reference: datetime = None) -> List[datetime]:
    """Return a list of 7 datetime objects for Mon-Sun of the current week."""
    if reference is None:
        reference = datetime.now()
    monday = reference - timedelta(days=reference.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def _matches_occurrence(date: datetime, freq: str) -> bool:
    """Return True if `date` matches the occurrence rule."""
    if freq == "weekly":
        return True
    if freq in OCCURRENCE_RANGES:
        lo, hi = OCCURRENCE_RANGES[freq]
        return lo <= date.day <= hi
    return False


class RecurringScraper(BaseScraper):
    """Generate hardcoded recurring LGBTQ+ events for the current week."""

    source_name = "recurring"

    def scrape(self) -> List[Dict]:
        events = []
        week_dates = _get_week_dates()

        for entry in RECURRING:
            target_weekday = DAY_MAP.get(entry["day"])
            if target_weekday is None:
                logger.warning(f"[recurring] Unknown day '{entry['day']}' for '{entry['name']}'")
                continue

            for date in week_dates:
                if date.weekday() != target_weekday:
                    continue
                if not _matches_occurrence(date, entry["freq"]):
                    continue

                date_str = date.strftime("%Y-%m-%d")
                events.append(self.make_event(
                    name=entry["name"],
                    date=date_str,
                    time=entry.get("time", ""),
                    venue=entry.get("venue", ""),
                    description="",
                    url=entry.get("url", ""),
                    priority=entry.get("priority", 2),
                ))
                # Each entry should only match once per week
                break

        logger.info(f"[recurring] Generated {len(events)} recurring events for this week")
        return events


def scrape() -> List[Dict]:
    """Module-level entry point."""
    return RecurringScraper().safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  {e['date']} {e['name']} | {e['time']} | {e['venue']}")
    print(f"\nTotal: {len(results)} events")
