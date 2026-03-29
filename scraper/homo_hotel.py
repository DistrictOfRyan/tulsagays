"""Homo Hotel Happy Hour - always priority 1, always featured.

This is the signature recurring weekly event for Tulsa Gays.
Since it may not have a dedicated website, we generate the upcoming
occurrences as hardcoded recurring events.
"""

import sys
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

# ── Configuration for Homo Hotel Happy Hour ──────────────────────────────
# Adjust these as the event details become known/change
EVENT_DAY_OF_WEEK = 3  # Thursday (0=Mon, 3=Thu)
EVENT_TIME = "5:00 PM - 8:00 PM"
EVENT_VENUE = "Homo Hotel"
EVENT_DESCRIPTION = (
    "Tulsa's favorite weekly queer happy hour! Every Friday, the Homo Hotel "
    "opens its doors for an evening of community, conversation, and cocktails. "
    "Whether you're new to Tulsa or a longtime local, this is THE place to "
    "kick off your weekend with your LGBTQ+ family. All are welcome - bring "
    "a friend, make a friend, be yourself. No cover, just vibes."
)
WEEKS_AHEAD = 4  # Generate events for the next N weeks


class HomoHotelScraper(BaseScraper):
    """Generate Homo Hotel Happy Hour recurring events.

    This is not a traditional scraper - it generates known recurring events.
    Always priority 1. Always included. Always at the top.
    """

    source_name = "homo_hotel"

    def scrape(self) -> List[Dict]:
        """Generate upcoming Homo Hotel Happy Hour events."""
        events = []
        today = datetime.now().date()

        for week_offset in range(WEEKS_AHEAD):
            # Find the next occurrence of the event day
            target = today + timedelta(weeks=week_offset)
            # Adjust to the correct day of week
            days_ahead = EVENT_DAY_OF_WEEK - target.weekday()
            if days_ahead < 0 and week_offset == 0:
                days_ahead += 7
            elif week_offset > 0 and days_ahead < 0:
                days_ahead += 7

            event_date = target + timedelta(days=days_ahead)

            # Skip dates in the past
            if event_date < today:
                continue

            date_str = event_date.strftime("%Y-%m-%d")
            friendly_date = event_date.strftime("%A, %B %d")

            events.append(self.make_event(
                name="Homo Hotel Happy Hour",
                date=date_str,
                time=EVENT_TIME,
                venue=EVENT_VENUE,
                description=f"{EVENT_DESCRIPTION}\n\nThis {friendly_date} - don't miss it!",
                url="",  # No dedicated URL yet
                priority=1,  # ALWAYS priority 1
            ))

        logger.info(f"[homo_hotel] Generated {len(events)} upcoming Happy Hour events")
        return events


def scrape() -> List[Dict]:
    """Module-level entry point."""
    return HomoHotelScraper().safe_scrape()


def get_next_event() -> Dict | None:
    """Convenience: get just the next upcoming Homo Hotel Happy Hour."""
    events = scrape()
    return events[0] if events else None


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  {e['name']} | {e['date']} | {e['time']} | P{e['priority']}")
    print(f"\nTotal: {len(results)} upcoming events")
