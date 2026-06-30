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
    # REMOVED 2026-06-23 (William): the "Drag Bingo Bongo at Saturn Room" rule
    # FABRICATED a drag event. saturnroom.com only says generic "bingo every
    # Thursday night at 6:30" — there is no verified "drag" bingo, no "Bingo
    # Bongo" name, and no Karma Eclectic host on the source. The rule date-stamped
    # it onto every Thursday with no live check, and it headlined the W26 post as
    # Event of the Week for a night it wasn't happening. Do NOT re-add a recurring
    # Saturn Room event unless it is verified on the source each time it posts
    # (William: "verify that it's happening before you post it"). Recurring auto-
    # events are now also barred from EOTW in eotw_selector.select_eotw.

    # ── Yellow Brick Road (YBR) — Tulsa's only lesbian bar, INCLUSIVE ──────────
    # Added 2026-06-24 per William: YBR's events weren't surfacing because the
    # IG-only scraper (ybr_ig) depends on an Instagram session that keeps dying.
    # These are YBR's OWN published recurring schedule, read live + verified from
    # @tulsaybr's "Monthly Events" + "June 2026" flyers (2026-06-24), so YBR shows
    # EVERY week without depending on the IG session. The ybr_ig scraper still
    # catches one-off specials on top of these. Priority 1 = featured (William
    # 2026-06-20); content/generator adds the "everyone welcome" inclusive note.
    # NOTE: "RuPaul watch party every Friday WHEN IN SEASON" is intentionally NOT
    # added — the in-season condition can't be auto-verified (no fabrication).
    {"name": "Trivia Night at YBR", "day": "Tuesday", "freq": "weekly",
     "time": "7:00 PM", "venue": "Yellow Brick Road, 2630 E 15th St",
     "url": "https://www.instagram.com/tulsaybr/", "priority": 1},
    {"name": "Free Pool & Darts at YBR", "day": "Wednesday", "freq": "weekly",
     "time": "", "venue": "Yellow Brick Road, 2630 E 15th St",
     "url": "https://www.instagram.com/tulsaybr/", "priority": 1},
    {"name": "Babes & Bi-cons Dance Party at YBR", "day": "Saturday", "freq": "1st",
     "time": "9:30 PM", "venue": "Yellow Brick Road, 2630 E 15th St",
     "url": "https://www.instagram.com/tulsaybr/", "priority": 1},
    {"name": "DJ Kylie Dance Party at YBR", "day": "Friday", "freq": "2nd",
     "time": "9:30 PM", "venue": "Yellow Brick Road, 2630 E 15th St",
     "url": "https://www.instagram.com/tulsaybr/", "priority": 1},
    {"name": "Open Stage at YBR", "day": "Thursday", "freq": "3rd",
     "time": "9:00 PM", "venue": "Yellow Brick Road, 2630 E 15th St",
     "url": "https://www.instagram.com/tulsaybr/", "priority": 1},
    {"name": "KATNIP at YBR", "day": "Friday", "freq": "3rd",
     "time": "9:00 PM", "venue": "Yellow Brick Road, 2630 E 15th St",
     "url": "https://www.instagram.com/tulsaybr/", "priority": 1},
    {"name": "Gaymer Night at YBR", "day": "Monday", "freq": "last",
     "time": "7:00 PM", "venue": "Yellow Brick Road, 2630 E 15th St",
     "url": "https://www.instagram.com/tulsaybr/", "priority": 1},
    {"name": "Karaoke at YBR (with Party Possum)", "day": "Thursday", "freq": "last",
     "time": "", "venue": "Yellow Brick Road, 2630 E 15th St",
     "url": "https://www.instagram.com/tulsaybr/", "priority": 1},

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
        # Venue ROTATES month to month -- never hardcode it (a stale Equality
        # Center venue once shipped on a slide). Left blank on purpose; the real
        # monthly venue comes from data/venue_overrides.json, and preflight_post
        # hard-blocks featuring this without a confirmed venue for the month.
        "name": "Queer Women's Collective",
        "day": "Wednesday",
        "freq": "1st",
        "time": "Evening",
        "venue": "",
        "venue_varies": True,
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
        # ARTSOK free outdoor concert series — every Tuesday in June, a fun
        # all-ages summer-night staple that queer Tulsans turn out for. Real,
        # verified (artsok.org / TulsaKids). Fills Tuesdays, which are otherwise
        # bare. Lineup rotates; description stays evergreen.
        "name": "Tuesdays in the Park Concert Series",
        "day": "Tuesday",
        "freq": "weekly",
        "time": "7:00 PM - 9:00 PM",
        "venue": "Central Park, 1500 S Main St, Broken Arrow",
        "url": "https://www.artsok.org/",
        "priority": 2,
        "description": ("Free outdoor live music every Tuesday night this summer, with food trucks, "
                        "raffles, and a easy come-as-you-are crowd. Pack a blanket, grab a taco from a "
                        "truck, and post up near the stage before the band kicks off at 7."),
        "website_description": ("Tuesdays in the Park is the free, all-ages summer concert series at Central "
                        "Park in Broken Arrow, and it is one of those low-key gems that makes a weeknight "
                        "feel like a tiny festival. Live music runs 7 to 9, with food trucks, raffle prizes, "
                        "and a relaxed, friendly crowd spread out on the grass. No ticket, no dress code, just "
                        "a good excuse to be outside with people. Best-time tip: bring a blanket or a low chair, "
                        "show up around 6:45 to grab a spot and hit the food trucks before the line builds, and "
                        "stay loose, this is a chatting-with-strangers kind of night."),
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
    # "last" = the final occurrence of this weekday in the month (next same
    # weekday is in the following month). Needed for YBR's Last-Thursday Karaoke
    # and Last-Monday Gaymer Night (added 2026-06-24).
    if freq == "last":
        return (date + timedelta(days=7)).month != date.month
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
                ev = self.make_event(
                    name=entry["name"],
                    date=date_str,
                    time=entry.get("time", ""),
                    venue=entry.get("venue", ""),
                    description="",
                    url=entry.get("url", ""),
                    priority=entry.get("priority", 2),
                )
                # Flag rotating-venue events so the override/preflight layer knows
                # not to trust a blank/stale venue (e.g. Queer Women's Collective).
                if entry.get("venue_varies"):
                    ev["venue_varies"] = True
                events.append(ev)
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
