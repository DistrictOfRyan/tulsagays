"""Scraper for major ticketing platforms: Ticketmaster, Songkick, AXS, and Do918.

Covers major Tulsa venues: BOK Center, Cain's Ballroom, Hard Rock Live, TPAC,
The Vanguard, River Spirit, and more. Events pass through runner.py filters.

Ticketmaster Discovery API: free tier, 2000 calls/day.
Get a key at developer.ticketmaster.com — add TICKETMASTER_API_KEY to .env.
Without a key, Ticketmaster scraping is skipped and other sources run.
"""

import sys
import os
import json
import logging
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

TICKETMASTER_API = "https://app.ticketmaster.com/discovery/v2/events.json"

# Tulsa-area venue search URLs for web-scraping fallback
SONGKICK_TULSA = "https://www.songkick.com/metro-areas/29100-us-tulsa"
DO918_EVENTS = "https://do918.com/events"
AXS_BOK = "https://www.axs.com/venues/101571/bok-center-tulsa-tickets"


def _get_week_range():
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return (
        monday.replace(hour=0, minute=0, second=0, microsecond=0),
        sunday.replace(hour=23, minute=59, second=59, microsecond=999999),
    )


class TicketingScraper(BaseScraper):
    """Scrape major ticketing platforms for Tulsa events this week."""

    source_name = "ticketing_sites"

    def scrape(self) -> List[Dict]:
        events = []
        monday, sunday = _get_week_range()

        # Ticketmaster Discovery API (primary — requires API key in .env)
        tm_key = getattr(config, "TICKETMASTER_API_KEY", "") or os.environ.get("TICKETMASTER_API_KEY", "")
        if tm_key:
            events.extend(self._scrape_ticketmaster(tm_key, monday, sunday))
        else:
            logger.info("[ticketing] No TICKETMASTER_API_KEY — skipping Ticketmaster. "
                        "Add key to .env to enable.")

        # Songkick web scrape (JSON-LD extraction)
        events.extend(self._scrape_songkick(monday, sunday))

        # Do918 web scrape
        events.extend(self._scrape_do918(monday, sunday))

        logger.info(f"[ticketing] Total: {len(events)} events from ticketing sites")
        return events

    # ── Ticketmaster Discovery API ────────────────────────────────────────

    def _scrape_ticketmaster(self, api_key: str, monday: datetime, sunday: datetime) -> List[Dict]:
        events = []
        start_dt = monday.strftime("%Y-%m-%dT00:00:00Z")
        end_dt = sunday.strftime("%Y-%m-%dT23:59:59Z")

        params = {
            "apikey": api_key,
            "city": "Tulsa",
            "stateCode": "OK",
            "countryCode": "US",
            "startDateTime": start_dt,
            "endDateTime": end_dt,
            "size": 100,
            "sort": "date,asc",
        }

        try:
            import urllib.request
            import urllib.parse
            url = TICKETMASTER_API + "?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            logger.warning(f"[ticketing] Ticketmaster API failed: {e}")
            return []

        raw_events = (data.get("_embedded") or {}).get("events") or []
        logger.info(f"[ticketing] Ticketmaster: {len(raw_events)} events from API")

        for ev in raw_events:
            try:
                name = ev.get("name", "").strip()
                if not name:
                    continue

                dates = ev.get("dates", {}).get("start", {})
                date_str = dates.get("localDate", "")
                time_str = ""
                if dates.get("localTime"):
                    try:
                        t = datetime.strptime(dates["localTime"], "%H:%M:%S")
                        time_str = t.strftime("%-I:%M %p").lstrip("0") or t.strftime("%I:%M %p")
                    except Exception:
                        time_str = dates["localTime"]

                venues = (ev.get("_embedded") or {}).get("venues") or []
                venue = ""
                if venues:
                    v = venues[0]
                    vname = v.get("name", "")
                    vcity = (v.get("city") or {}).get("name", "")
                    venue = f"{vname}, {vcity}" if vcity else vname

                url_tm = ev.get("url", "")

                events.append(self.make_event(
                    name=name,
                    date=date_str,
                    time=time_str,
                    venue=venue or "Tulsa, OK",
                    url=url_tm,
                    priority=3,
                ))
            except Exception as e:
                logger.debug(f"[ticketing] TM parse error: {e}")

        return events

    # ── Songkick web scrape ───────────────────────────────────────────────

    def _scrape_songkick(self, monday: datetime, sunday: datetime) -> List[Dict]:
        """Extract upcoming Tulsa concerts from Songkick's metro page."""
        soup = self.fetch_page(SONGKICK_TULSA)
        if not soup:
            return []

        events = []

        # Songkick embeds event data in JSON-LD and also in <li class="event-listings">
        json_ld_events = self._extract_json_ld_from_soup(soup, SONGKICK_TULSA, priority=3)
        if json_ld_events:
            logger.info(f"[ticketing] Songkick JSON-LD: {len(json_ld_events)} events")
            for e in json_ld_events:
                date_str = e.get("date", "")
                if not date_str:
                    continue
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    if monday <= dt <= sunday:
                        events.append(e)
                except ValueError:
                    pass
            return events

        # Fallback: parse event listings from HTML
        listings = soup.select("li.event-listings-element, li.concert, .events-table-details")
        for item in listings[:50]:
            try:
                name_el = item.select_one(".summary a, .event-details h3, a.event-link")
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                if not name or len(name) < 4:
                    continue

                date_el = item.select_one("time, .date, [class*='date']")
                date_str = ""
                if date_el:
                    dt_attr = date_el.get("datetime", "")
                    date_str = self.parse_date_flexible(dt_attr or date_el.get_text(strip=True))

                if date_str:
                    try:
                        dt = datetime.strptime(date_str, "%Y-%m-%d")
                        if not (monday <= dt <= sunday):
                            continue
                    except ValueError:
                        continue

                venue_el = item.select_one(".venue, [class*='venue']")
                venue = venue_el.get_text(strip=True) if venue_el else "Tulsa, OK"

                link = name_el.get("href", "")
                url = f"https://www.songkick.com{link}" if link.startswith("/") else link

                events.append(self.make_event(
                    name=name,
                    date=date_str,
                    time="",
                    venue=venue,
                    url=url,
                    priority=3,
                ))
            except Exception as e:
                logger.debug(f"[ticketing] Songkick parse error: {e}")

        logger.info(f"[ticketing] Songkick HTML fallback: {len(events)} events this week")
        return events

    # ── Do918 web scrape ──────────────────────────────────────────────────

    def _scrape_do918(self, monday: datetime, sunday: datetime) -> List[Dict]:
        """Scrape Do918 — Tulsa's local event guide."""
        soup = self.fetch_page(DO918_EVENTS)
        if not soup:
            return []

        events = []

        # Try JSON-LD first
        json_ld_events = self._extract_json_ld_from_soup(soup, DO918_EVENTS, priority=3)
        if json_ld_events:
            in_week = [e for e in json_ld_events if self._in_week(e.get("date", ""), monday, sunday)]
            logger.info(f"[ticketing] Do918 JSON-LD: {len(in_week)} events this week")
            return in_week

        # HTML fallback
        items = soup.select("article, .event-card, .event-item, [class*='event']")
        for item in items[:40]:
            try:
                name_el = item.select_one("h1, h2, h3, h4, a")
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                if not name or len(name) < 4:
                    continue

                date_el = item.select_one("time, .date, [class*='date']")
                date_str = ""
                if date_el:
                    date_str = self.parse_date_flexible(
                        date_el.get("datetime", "") or date_el.get_text(strip=True)
                    )

                if date_str and not self._in_week(date_str, monday, sunday):
                    continue

                link_el = item.find("a", href=True)
                url = link_el["href"] if link_el else DO918_EVENTS
                if url.startswith("/"):
                    url = "https://do918.com" + url

                events.append(self.make_event(
                    name=name,
                    date=date_str,
                    time="",
                    venue="Tulsa, OK",
                    url=url,
                    priority=3,
                ))
            except Exception as e:
                logger.debug(f"[ticketing] Do918 parse error: {e}")

        logger.info(f"[ticketing] Do918 HTML: {len(events)} events")
        return events

    def _in_week(self, date_str: str, monday: datetime, sunday: datetime) -> bool:
        if not date_str:
            return False
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return monday <= dt <= sunday
        except ValueError:
            return False


def scrape() -> List[Dict]:
    """Module-level entry point."""
    return TicketingScraper().safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    events = scrape()
    print(f"\nTicketing Sites: {len(events)} found")
    for e in events:
        print(f"  {e.get('date','?')} | {e['name'][:55]} | {e.get('venue','')[:30]}")
