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
EVENT_TIME = "6:00 PM - 8:00 PM"
EVENT_VENUE = "Downtown Tulsa (First Friday)"
EVENT_URL = "https://linktr.ee/homohotelhappyhour"
EVENT_DESCRIPTION = (
    "The queerest happy hour in T-Town is back. First Friday tradition. "
    "Drink specials, good vibes, and the community you've been looking for. "
    "All are welcome. Bring a friend, make a friend, be yourself."
)
WEEKS_AHEAD = 6  # Generate events for the next N weeks


class HomoHotelScraper(BaseScraper):
    """Generate Homo Hotel Happy Hour recurring events.

    This is not a traditional scraper - it generates known recurring events.
    Always priority 1. Always included. Always at the top.
    """

    source_name = "homo_hotel"

    def scrape(self) -> List[Dict]:
        """Generate upcoming Homo Hotel Happy Hour events (First Friday of each month)."""
        events = []
        today = datetime.now().date()

        # Find First Fridays for the next several months
        for month_offset in range(WEEKS_AHEAD):
            year = today.year
            month = today.month + month_offset
            if month > 12:
                year += (month - 1) // 12
                month = ((month - 1) % 12) + 1

            # Find the first Friday of this month
            first_day = datetime(year, month, 1).date()
            days_to_friday = (4 - first_day.weekday()) % 7  # 4 = Friday
            first_friday = first_day + timedelta(days=days_to_friday)

            # Skip dates in the past
            if first_friday < today:
                continue

            date_str = first_friday.strftime("%Y-%m-%d")
            friendly_date = first_friday.strftime("%A, %B %d")

            events.append(self.make_event(
                name="Homo Hotel Happy Hour",
                date=date_str,
                time=EVENT_TIME,
                venue=EVENT_VENUE,
                description=f"{EVENT_DESCRIPTION}\n\nThis {friendly_date}, don't miss it!",
                url=EVENT_URL,
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
