"""Scraper for QLIST app - LGBTQ+ event aggregator for Tulsa."""

import sys
import os
import logging
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)


class QListScraper(BaseScraper):
    """Scrape events from qlist.app for Tulsa."""

    source_name = "qlist"
    URL = "https://qlist.app/cities/Oklahoma/Tulsa/163"

    def scrape(self) -> List[Dict]:
        soup = self.fetch_page(self.URL)
        if not soup:
            return []

        events = []

        # QLIST uses structured event cards
        event_cards = (
            soup.select(".event-card")
            or soup.select("[class*='event']")
            or soup.select("article")
            or soup.select(".card")
        )

        for card in event_cards:
            try:
                name_el = card.select_one("h2, h3, h4, .event-title, .card-title")
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                if not name or len(name) < 3:
                    continue

                # Date
                date_el = card.select_one("time, .event-date, .date, [class*='date']")
                date_str = ""
                if date_el:
                    date_str = date_el.get("datetime", "") or date_el.get_text(strip=True)
                date_str = self.parse_date_flexible(date_str)

                # Time
                time_el = card.select_one(".event-time, .time, [class*='time']")
                time_str = time_el.get_text(strip=True) if time_el else ""

                # Venue
                venue_el = card.select_one(".venue, .location, [class*='venue'], [class*='location']")
                venue = venue_el.get_text(strip=True) if venue_el else ""

                # Description
                desc_el = card.select_one("p, .description, .event-description")
                description = desc_el.get_text(strip=True)[:500] if desc_el else ""

                # URL
                link_el = card.find("a", href=True)
                url = ""
                if link_el:
                    href = link_el["href"]
                    url = href if href.startswith("http") else f"https://qlist.app{href}"

                events.append(self.make_event(
                    name=name,
                    date=date_str,
                    time=time_str,
                    venue=venue,
                    description=description,
                    url=url,
                    priority=2,
                ))
            except Exception as e:
                logger.debug(f"[qlist] Failed to parse card: {e}")
                continue

        self._random_delay()
        return events


def scrape() -> List[Dict]:
    """Module-level entry point."""
    return QListScraper().safe_scrape()
