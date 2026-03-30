"""Scraper for LGBTQ+ community groups, sports leagues, and recurring events in Tulsa.

Covers: Black Queer Tulsa, Studio 66, Lambda Bowling, HotMess Sports,
Queer Women's Collective, PFLAG Tulsa, Green Country Bears, Prime Timers,
Elote Drag Brunch, Council Oak Men's Chorus.
"""

import sys
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class CommunityGroupsScraper(BaseScraper):
    """Scrape events from community groups and generate recurring event entries."""

    source_name = "community_groups"

    # ── Websites to scrape ─────────────────────────────────────────────
    SOURCES = {
        "black_queer_tulsa": "https://www.blackqueertulsa.org/",
        "studio_66": "https://www.s66tulsa.com/",
        "elote_events": "https://www.elotetulsa.com/events",
        "green_country_bears": "https://greencountrybears.com/",
        "pflag_tulsa": "https://tulsapflag.org/",
        "council_oak_chorus": "https://www.counciloakchorus.org/",
    }

    def scrape(self) -> List[Dict]:
        events = []

        # Scrape websites that have event listings
        for source_key, url in self.SOURCES.items():
            try:
                source_events = self._scrape_source(source_key, url)
                events.extend(source_events)
            except Exception as e:
                logger.error(f"[community_groups] Failed scraping {source_key}: {e}")

        # Add known recurring events for this week
        events.extend(self._get_recurring_events())

        return events

    def _scrape_source(self, source_key: str, url: str) -> List[Dict]:
        """Attempt to scrape event listings from a community group website."""
        soup = self.fetch_page(url)
        if not soup:
            return []

        events = []

        # Look for event-like containers
        containers = (
            soup.select(".event, .events-list li, article, .event-card, .sqs-block-content")
        )

        for container in containers[:20]:  # Limit to avoid noise
            try:
                name_el = container.select_one("h1, h2, h3, h4, .event-title, a")
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                if not name or len(name) < 5:
                    continue

                # Skip navigation links and non-event content
                skip_words = ["home", "about", "contact", "donate", "menu", "privacy", "terms"]
                if name.lower() in skip_words:
                    continue

                date_el = container.select_one("time, .date, [class*='date']")
                date_str = ""
                if date_el:
                    date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)
                date_str = self.parse_date_flexible(date_str)

                link_el = container.find("a", href=True)
                event_url = ""
                if link_el:
                    href = link_el["href"]
                    event_url = href if href.startswith("http") else url.rstrip("/") + "/" + href.lstrip("/")

                priority = 1 if "council_oak" in source_key else 2

                events.append(self.make_event(
                    name=name,
                    date=date_str,
                    venue=self._venue_for_source(source_key),
                    url=event_url,
                    priority=priority,
                ))
            except Exception as e:
                logger.debug(f"[community_groups] Parse error in {source_key}: {e}")

        self._random_delay()
        return events

    def _get_recurring_events(self) -> List[Dict]:
        """Generate entries for known recurring events happening this week."""
        events = []
        today = datetime.now()
        monday = today - timedelta(days=today.weekday())
        week_dates = [monday + timedelta(days=i) for i in range(7)]

        for d in week_dates:
            day_of_week = d.weekday()  # 0=Mon, 6=Sun
            day_of_month = d.day
            date_str = d.strftime("%Y-%m-%d")

            # PFLAG Tulsa: 1st Saturday, 7pm
            if day_of_week == 5 and day_of_month <= 7:
                events.append(self.make_event(
                    name="PFLAG Tulsa Monthly Meeting",
                    date=date_str,
                    time="7:00 PM",
                    venue="110 S Hartford Ave, Suite 2516, Tulsa",
                    description="Monthly support and education meeting for LGBTQ+ families and allies. Alternates between social/support and education formats.",
                    url="https://tulsapflag.org/",
                    priority=2,
                ))

            # Queer Women's Collective: 1st Wednesday
            if day_of_week == 2 and day_of_month <= 7:
                events.append(self.make_event(
                    name="Queer Women's Collective Happy Hour",
                    date=date_str,
                    time="6:00 PM",
                    venue="Varies (check social media)",
                    description="Monthly social gathering for queer women and allies. Good drinks, great people, zero pretension.",
                    url="https://www.facebook.com/queerwomenscollectivetulsa/",
                    priority=2,
                ))

            # Prime Timers: 2nd Tuesday, 7pm
            if day_of_week == 1 and 8 <= day_of_month <= 14:
                events.append(self.make_event(
                    name="Tulsa Area Prime Timers",
                    date=date_str,
                    time="7:00 PM",
                    venue="Dennis R. Neill Equality Center, 621 E 4th St",
                    description="Monthly social for mature gay and bisexual men (21+). Great conversation, welcoming community.",
                    url="https://okeq.org/okeq-events/tulsa-area-prime-timers/",
                    priority=2,
                ))

            # Green Country Bears: 2nd Thursday
            if day_of_week == 3 and 8 <= day_of_month <= 14:
                events.append(self.make_event(
                    name="Green Country Bears Monthly Meetup",
                    date=date_str,
                    time="7:00 PM",
                    venue="Restaurant (varies, check website)",
                    description="Monthly dinner meetup for bears and friends. Chill vibes, good food, friendly crowd.",
                    url="https://greencountrybears.com/",
                    priority=2,
                ))

            # Elote Drag Brunch: 2nd Saturday
            if day_of_week == 5 and 8 <= day_of_month <= 14:
                events.append(self.make_event(
                    name="Elote Drag Brunch",
                    date=date_str,
                    time="11:00 AM + 1:30 PM (two seatings)",
                    venue="Elote Cafe & Catering",
                    description="Monthly drag brunch with themed shows. All ages. Two seatings. Delicious food and fierce performances.",
                    url="https://www.elotetulsa.com/events",
                    priority=2,
                ))

        return events

    def _venue_for_source(self, source_key: str) -> str:
        """Return the default venue for a source."""
        venues = {
            "black_queer_tulsa": "Various locations in Tulsa",
            "studio_66": "Studio 66, Tulsa",
            "elote_events": "Elote Cafe & Catering",
            "green_country_bears": "Varies",
            "pflag_tulsa": "110 S Hartford Ave",
            "council_oak_chorus": "Tulsa Performing Arts Center",
        }
        return venues.get(source_key, "Tulsa")


def scrape() -> List[Dict]:
    """Module-level entry point."""
    return CommunityGroupsScraper().safe_scrape()
