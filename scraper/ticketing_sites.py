"""Ticketing platforms. Only the Ticketmaster Discovery API path is left, and it
runs only when TICKETMASTER_API_KEY is set (it never has been).

RETIRED 2026-11-06. This module returned 0 on every scrape (W43-W45 logs and a
sandboxed full scrape on 2026-11-06). Real responses, 2026-11-06:
  Songkick  www.songkick.com/metro-areas/29100-us-tulsa -> HTTP 406, empty body.
            Two faults: 29100 is not Tulsa (Tulsa is 1826-us-tulsa), and every
            Songkick cache MISS answers plain HTTP clients with 406 (control: the
            London metro page, a CDN HIT, answered 200 with 304 KB). Headless
            Chromium gets the page, so Songkick now lives in
            data/rendered_site_specs.json as "Songkick Tulsa" (json_ld, metro_only):
            44 dated Tulsa-metro concerts on 2026-11-06 after dropping 6 Fort Smith,
            Pocola and Ramona rows. The nightly guard measures it there.
  Do918     do918.com -> no A record (8.8.8.8 answers the name with no address;
            Python: NameResolutionError). Gone.
  AXS       axs.com/venues/101571/... -> HTTP 403 "AXS Access Info" bot page. It was
            never called by this module anyway.
  Ticketmaster  Discovery API without a key -> HTTP 401
            "Failed to resolve API Key variable request.queryparam.apikey".
            No key exists in config, .env or ~/.credentials/api_keys.env, and getting
            one means creating a developer account. Not worth it: the venues it covers
            are already read directly by rendered specs (BOK Center, Cain's Ballroom,
            Tulsa Theater, Hard Rock Live, Tulsa PAC via Celebrity Attractions) and by
            Songkick, which lists Ticketmaster-sold shows too. If a key is ever set,
            the path below runs again with no code change.
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

# Read by health tooling: why a 0 from this module is expected, not an outage.
RETIRED = ("2026-11-06: Songkick moved to rendered spec 'Songkick Tulsa'; Do918 has no DNS; "
           "Ticketmaster runs only if TICKETMASTER_API_KEY is set (never has been)")


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
        tm_key = getattr(config, "TICKETMASTER_API_KEY", "") or os.environ.get("TICKETMASTER_API_KEY", "")
        if not tm_key:
            logger.info("[ticketing] retired 2026-11-06: no TICKETMASTER_API_KEY; Songkick is the "
                        "'Songkick Tulsa' rendered spec, Do918 has no DNS. Returning 0.")
            return []
        monday, sunday = _get_week_range()
        events = self._scrape_ticketmaster(tm_key, monday, sunday)
        logger.info(f"[ticketing] Ticketmaster: {len(events)} events")
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
                        # "%-I" raises ValueError on Windows, which used to leave "19:00:00".
                        time_str = f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"
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

def scrape() -> List[Dict]:
    """Module-level entry point."""
    return TicketingScraper().safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    events = scrape()
    print(f"\nTicketing Sites: {len(events)} found")
    for e in events:
        print(f"  {e.get('date','?')} | {e['name'][:55]} | {e.get('venue','')[:30]}")
