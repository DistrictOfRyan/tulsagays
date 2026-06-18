"""Scraper for QLIST app - LGBTQ+ event aggregator for Tulsa."""

import sys
import os
import re
import logging
from datetime import datetime
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


class QListScraper(BaseScraper):
    """Scrape events from qlist.app for Tulsa.

    qlist renders each event as a `.cluster-event` div (wrapped in an
    /events/Tulsa/<slug>/<id> anchor) with inline-styled children: a bold
    title, a description line, and a date line carrying a calendar icon. The
    old guessed selectors (.event-card/.card/article) matched nothing, so the
    source silently produced 0. This parses the real structure.
    """

    source_name = "qlist"
    URL = "https://qlist.app/cities/Oklahoma/Tulsa/163"

    def scrape(self) -> List[Dict]:
        soup = self.fetch_page(self.URL)
        if not soup:
            return []

        events = []
        seen = set()
        cards = soup.select(".cluster-event")
        for card in cards:
            try:
                ev = self._parse_card(card)
                if not ev:
                    continue
                key = (ev["name"], ev["date"])  # page renders each card twice
                if key in seen:
                    continue
                seen.add(key)
                events.append(ev)
            except Exception as e:
                logger.debug(f"[qlist] Failed to parse card: {e}")
                continue

        logger.info(f"[qlist] Parsed {len(events)} unique events from {len(cards)} cards")
        self._random_delay()
        return events

    def _parse_card(self, card) -> Optional[Dict]:
        # Leaf text divs in document order: [title, description, ...]; the date
        # line is the div that holds the calendar <img>.
        text_divs = [d for d in card.find_all("div")
                     if d.get_text(strip=True) and not d.find("div")]
        if not text_divs:
            return None

        name = text_divs[0].get_text(" ", strip=True)
        if not name or len(name) < 3:
            return None

        description = ""
        if len(text_divs) > 1:
            description = text_divs[1].get_text(" ", strip=True)[:500]

        date_div = next((d for d in card.find_all("div") if d.find("img")), None)
        raw_date = date_div.get_text(" ", strip=True) if date_div else ""
        date_str = self._parse_start_date(raw_date)

        anchor = card.find_parent("a", href=True) or card.find("a", href=True)
        url = ""
        if anchor:
            href = anchor["href"]
            url = href if href.startswith("http") else f"https://qlist.app{href}"

        return self.make_event(
            name=name, date=date_str, time="", venue="",
            description=description, url=url, priority=2,
        )

    @staticmethod
    def _parse_start_date(raw: str) -> str:
        """Extract the START date from qlist's date line.

        Formats seen: 'Thu, 18 Jun - 25 Jul', 'Sat, 20 - 21 Jun',
        'Mon, 22 - 29 Jun (Various dates)', 'Thu, 25 Jun (Various dates)'.
        Strategy: first day-number + first month token in the string. Year is
        inferred (next year if the month/day already passed > 60 days ago).
        """
        if not raw:
            return ""
        txt = raw.replace("\xa0", " ")
        day_m = re.search(r"\b(\d{1,2})\b", txt)
        mon_m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
                          txt, re.IGNORECASE)
        if not day_m or not mon_m:
            return ""
        day = int(day_m.group(1))
        month = _MONTHS[mon_m.group(1).lower()[:3]]
        today = datetime.now()
        year = today.year
        try:
            candidate = datetime(year, month, day)
        except ValueError:
            return ""
        if (today - candidate).days > 60:
            candidate = candidate.replace(year=year + 1)
        return candidate.strftime("%Y-%m-%d")


def scrape() -> List[Dict]:
    """Module-level entry point."""
    return QListScraper().safe_scrape()
