"""Extended Tulsa event calendar scrapers — venues, tourism, arts, universities, libraries.

Uses a generic config-driven approach: JSON-LD first, then HTML fallback.
All events are filtered for LGBTQ relevance before returning.

Sources covered:
  TOURISM/CVB:
    TravelOK, Green Country OK, TulsaGo
  NEWS/MEDIA:
    TulsaKids, Tulsa Events (tulsa.events)
  CITY:
    City of Tulsa Special Events
  MUSEUMS & CULTURAL:
    Philbrook, Woody Guthrie Center, Greenwood Cultural Center, Tulsa Zoo, Gathering Place,
    Tulsa Garden Center, Oklahoma Aquarium, Discovery Lab, 101 Archer
  PERFORMING ARTS:
    Tulsa PAC, BOK Center, Cain's Ballroom, Tulsa Theater,
    Hard Rock Live, River Spirit Casino, The Church Studio,
    Cox Business Convention Center
  SPORTS/EXPO:
    ONEOK Field (Tulsa Drillers), FC Tulsa, Tulsa Oilers, Expo Square
  LIBRARIES:
    Tulsa City-County Library
  UNIVERSITIES:
    University of Tulsa, OSU-Tulsa, ORU, Tulsa Community College
  LGBTQ+:
    Tulsa Pride
  TICKETING/AGGREGATORS:
    SeatGeek Tulsa, Meetup Tulsa
  NEIGHBORHOOD/NICHE:
    Brookside Business Association, Cherry Street Farmers Market,
    Tulsa Farmers' Market, TulsaGo
"""

import sys
import os
import logging
import time
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper
from scraper import dynamic_sources as _dyn
from scraper.relevance import compile_lgbtq_keywords

logger = logging.getLogger(__name__)

LGBTQ_KEYWORDS = [
    # Explicit identity
    "lgbtq", "queer", "gay", "lesbian", "bi", "trans", "drag", "pride",
    "rainbow", "dyke", "nonbinary", "non-binary", "gender", "equality",
    "affirming", "inclusive", "homo", "sapphic", "two-spirit", "twospirit",
    # Queer-adjacent / community-coded
    "oddities", "curiosities",
    "burlesque", "cabaret",
    "feminist", "radical",
    "night market", "art market", "bazaar", "market",
    "wiz",
    "greenwood", "black wall street",
    "boots riley",
    # Cultural event types (effective at curated arts venues)
    "screening", "film festival", "documentary",
    "exhibition", "opening reception", "art opening",
    "workshop", "panel discussion", "panel", "lecture",
    "fundraiser", "benefit show", "benefit concert",
    "cultural festival", "heritage",
    "open mic", "poetry",
]


_LGBTQ_RX = compile_lgbtq_keywords(LGBTQ_KEYWORDS)


def _is_lgbtq_relevant(name: str, description: str = "") -> bool:
    combined = (name + " " + description).lower()
    return bool(_LGBTQ_RX.search(combined))


# ── Site configuration ─────────────────────────────────────────────────────
# Each entry: (url, display_name, category, lgbtq_only)
# lgbtq_only=False  → filter for LGBTQ keywords (general venues)
# lgbtq_only=True   → return ALL events (LGBTQ-specific orgs)

SITES: List[Tuple[str, str, str, bool]] = [
    # 2026-11-06 (F-3576): this list is now only the venues the generic static
    # parser can actually read. The nightly health guard probed all 39 old
    # entries and reported 44 DEAD sources while the same venues were covered,
    # or had been documented dead months earlier, in data/rendered_site_specs.json.
    # Every removed entry is kept in RETIRED_SITES below with its reason, and the
    # rendered spec is the single place a venue is wired. Do not re-add a URL here
    # that has a rendered spec; fix the spec instead.
    ("https://tulsa.events", "Tulsa Events", "media", False),
    ("https://philbrook.org/calendar/", "Philbrook Museum", "museum", False),
    ("https://woodyguthriecenter.org/events/", "Woody Guthrie Center", "museum", False),
    ("https://www.hardrockcasinotulsa.com/entertainment/", "Hard Rock Live Tulsa", "arts", False),
    # 2026-10-05: /events/ 404s; Squarespace moved the collection to /upcoming-events
    ("https://www.tulsafarmersmarket.org/upcoming-events", "Tulsa Farmers' Market", "neighborhood", False),
    # 2026-07-06: Meetup REMOVED from this list. The find-page URL ignores
    # userFreeform and geolocates by IP: from this machine (Mexico) it served
    # CDMX events that passed the LGBTQ filter labeled as Tulsa. Meetup is
    # covered by eventbrite_meetup.MeetupScraper, which pins
    # location=us--ok--tulsa explicitly. Never re-add an IP-geolocated URL here.
]

# Removed 2026-11-06. name -> (old url, disposition, reason). "rendered" means the
# venue is scraped by a data/rendered_site_specs.json spec of the same name, which
# was verified to return dated events that day.
RETIRED_SITES = {
    "TravelOK": ("https://travelok.com/listings/view_feature/category.lodging/city.tulsa", "retired",
                 "URL is a hotel/lodging directory, not events; tourism aggregator, venues are scraped directly"),
    "Green Country Oklahoma": ("https://www.greencountryok.com/cities/tulsa/festivals-events-in-tulsa", "retired",
                               "Simpleview widget yields 0 event blocks (re-verified 2026-07-06); low-value tourism aggregator"),
    "TulsaGo": ("https://tulsago.com/experience", "rendered", "rendered json_ld spec, 21 dated events on 2026-11-06"),
    "TulsaKids Magazine": ("https://www.tulsakids.com/calendar/", "retired",
                           "events live in a cross-origin Time.ly iframe with no public feed (export/ics returns HTML); "
                           "kids programming is quarantined by the sanity check anyway"),
    "City of Tulsa": ("https://www.cityoftulsa.org/government/departments/parks-recreation/events/", "retired",
                      "page is site chrome only; civic/government listings are dropped as off-topic by the runner"),
    "Greenwood Cultural Center": ("https://www.greenwoodculturalcenter.com/events", "retired",
                                  ".com shows a Wix 'domain not connected' page; the center moved to greenwoodculturalcenter.org "
                                  "(Wix, client-rendered, no structured events as of 2026-11-06)"),
    "1921 Tulsa Race Massacre Memorial": ("https://1921tulsamassacre.org/events", "retired",
                                          "domain parked/expired (redirects to an ad page, invalid cert)"),
    "Tulsa Zoo": ("https://www.tulsazoo.org/events/", "rendered",
                  "rendered dom spec, 9 dated events on 2026-11-06 after the networkidle-timeout fix"),
    "Gathering Place": ("https://www.gatheringplace.org/parkcalendar/", "rendered",
                        "rendered json spec on the tokened SiteWrench API, wired 2026-11-06"),
    "Tulsa Garden Center": ("https://www.tulsagardencenter.com/events/", "retired",
                            "/events/ is a 404; site moved to tulsagardencenter.org whose /calendar has no structured events (2026-11-06)"),
    "Oklahoma Aquarium": ("https://www.okaquarium.org/events/", "retired",
                          "/events/ 404; /31/Events has dates only inside news prose, no repeatable event markup"),
    "101 Archer": ("https://101archer.com/events/", "retired", "domain does not resolve (NXDOMAIN)"),
    "Tulsa PAC": ("https://www.tulsapac.com/events/", "rendered",
                  "tulsapac.com is a Ticketmaster Account Manager shell; the rendered 'Tulsa PAC' spec now reads Celebrity "
                  "Attractions' Broadway series at the PAC (10 dated shows on 2026-11-06)"),
    "BOK Center": ("https://www.bokcenter.com/events", "rendered", "rendered dom spec, 12 dated events on 2026-11-06"),
    "Cain's Ballroom": ("https://cainsballroom.com/events/", "rendered",
                        "rendered dom spec, 38 dated events on 2026-11-06 after the networkidle-timeout fix"),
    "Tulsa Theater": ("https://tulsatheater.com/events/", "rendered", "rendered dom spec, 14 dated events on 2026-11-06"),
    "River Spirit Casino": ("https://www.riverspirittulsa.com/entertainment/", "rendered",
                            "static parse returned undated junk (JUNK); rendered dom spec returns 4 dated events"),
    "The Church Studio": ("https://www.thechurchstudio.com/events/", "retired",
                          "Tribe list view never renders and the REST feed is 404 (re-checked 2026-11-06); "
                          "tickets sell per-event on Universe.com"),
    "Cox Business Convention Center": ("https://www.coxcentertulsa.com/events/", "retired",
                                       "hard Cloudflare challenge to every automated client"),
    "Tulsa Drillers (ONEOK Field)": ("https://www.milb.com/tulsa/schedule/", "retired",
                                     "mainstream sports, which the runner drops as off-topic"),
    "FC Tulsa": ("https://www.fctulsa.com/schedule/", "retired", "mainstream sports, which the runner drops as off-topic"),
    "Tulsa Oilers": ("https://www.tulsaoilers.com/schedule/", "retired", "mainstream sports, which the runner drops as off-topic"),
    "Expo Square": ("https://www.exposquare.com/events/", "rendered",
                    "rendered dom spec revived 2026-11-06 (horse/livestock and gun shows excluded)"),
    "Tulsa City-County Library": ("https://events.tulsalibrary.org/", "rendered",
                                  "rendered json spec on the Communico API, wired 2026-11-06 "
                                  "(408 events/21 days parsed; weekly scrape keeps LGBTQ matches only)"),
    "University of Tulsa": ("https://calendar.utulsa.edu/", "rendered",
                            "calendar.utulsa.edu moved to Trumba on 2026-11-06 (CNAME utulsa.trumba.com, cert mismatch); "
                            "rendered json spec reads trumba.com/calendars/utulsa.json"),
    "OSU-Tulsa": ("https://tulsa.okstate.edu/calendar/", "rendered",
                  "rendered json_ld spec on events.tulsa.okstate.edu, 24 dated events on 2026-11-06"),
    "ORU": ("https://www.oru.edu/events/", "retired",
            "404; the only ORU feed (student association Google Calendar) was abandoned in 2013"),
    "Tulsa Community College": ("https://www.tulsacc.edu/about-tcc/events/", "rendered",
                                "rendered json spec on calendar.tulsacc.edu LiveWhale, 100 dated events on 2026-11-06"),
    "Tulsa Pride": ("https://tulsapride.org/", "retired",
                    "homepage has no event list markup; the one annual date (Tulsa Pride Festival & Parade, 2026-10-17) is in "
                    "data/manual_events.json and OKEQ's calendar is scraped by okeq_calendar"),
    "Goff Center / Goff Fest": ("https://goff-fest.com/events/", "retired",
                                "single annual June festival in free text; covered by data/manual_events.json and the "
                                "@goff_fest Instagram source"),
    "SeatGeek Tulsa": ("https://seatgeek.com/tulsa-oklahoma-tickets", "retired", "DataDome CAPTCHA to every automated client"),
    "Brookside Tulsa": ("https://www.brooksidetulsa.com/events/", "retired", "domain now redirects to a realtor site"),
    "Cherry Street Farmers Market": ("https://www.cherrystreetfarmersmarket.com/events/", "retired",
                                     "domain does not resolve; the market runs under Tulsa Farmers' Market, which is still scraped"),
}

# Merge in calendar sites discovered + promoted by the weekly source-growth
# engine (data/dynamic_sources.json). De-duped by URL.
SITES = _dyn.merge_unique(SITES, _dyn.calendar_sites())


class ExtendedCalendarsScraper(BaseScraper):
    """Scrape all extended Tulsa calendar sources and filter for LGBTQ relevance."""

    source_name = "extended_calendars"

    def scrape(self) -> List[Dict]:
        all_events = []
        for url, name, category, lgbtq_only in SITES:
            try:
                events = self._scrape_site(url, name, lgbtq_only)
                all_events.extend(events)
                logger.info(f"[extended_calendars] {name}: {len(events)} events")
            except Exception as e:
                logger.warning(f"[extended_calendars] {name} failed: {e}")
        logger.info(f"[extended_calendars] Total: {len(all_events)} events across {len(SITES)} sites")
        return all_events

    def _scrape_site(self, url: str, site_name: str, lgbtq_only: bool) -> List[Dict]:
        """Generic scraper: JSON-LD first, then HTML. Filter for LGBTQ if not lgbtq_only site."""
        soup = self.fetch_page(url)
        if not soup:
            return []

        events = []

        # 1. Try JSON-LD structured data (works on ~40% of modern sites)
        events = self._extract_json_ld(soup, site_name)

        # 2. Try Localist platform (used by universities and libraries)
        if not events:
            events = self._extract_localist(soup, site_name, url)

        # 3. Try The Events Calendar (tribe) plugin (used by ~30% of WP sites)
        if not events:
            events = self._extract_tribe(soup, site_name, url)

        # 4. Generic HTML fallback
        if not events:
            events = self._extract_generic(soup, site_name, url)

        # Filter unless LGBTQ-specific org
        if not lgbtq_only:
            events = [e for e in events if _is_lgbtq_relevant(e.get("name", ""), e.get("description", ""))]

        self._random_delay()
        return events

    def _extract_json_ld(self, soup, site_name: str) -> List[Dict]:
        """Extract Event items from JSON-LD blocks.

        Delegates to the shared BaseScraper helper (2026-10-12). This method used
        to carry its own duplicate parser that never got the shared method's
        fixes: its "@graph" unwrap only fired when the wrapping node's own
        @type=="WebPage" (misses the common Yoast shape where @graph sits beside
        @context with no @type at all, e.g. TulsaKids), and it never looked
        inside mainEntity/hasPart at all, so Hard Rock Live Tulsa (43 real
        MusicEvents nested under a WebPage's mainEntity) and Philbrook (10 real
        Events nested under a CollectionPage's hasPart) silently returned 0
        events despite valid structured data on the page. Diagnosed live
        2026-10-12 per project tulsagays-extended-calendars-extraction-bug.
        """
        return self._extract_json_ld_from_soup(soup, venue_default=site_name, priority=2)

    def _extract_localist(self, soup, site_name: str, base_url: str) -> List[Dict]:
        """Extract events from Localist platform (used by Tulsa Library, UTulsa, OSU-Tulsa)."""
        events = []
        # Localist uses specific data attributes
        containers = (
            soup.select(".lw_events_summary_item")
            or soup.select("[data-id][class*='event']")
            or soup.select(".em-item")
            or soup.select(".event-node")
        )
        for container in containers[:30]:
            name_el = container.select_one(".lw_events_title a, h3 a, h2 a, .event-title a")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 4:
                continue
            url = name_el.get("href", "")
            if url and not url.startswith("http"):
                from urllib.parse import urljoin
                url = urljoin(base_url, url)
            date_el = container.select_one("time, .lw_events_time, [class*='date']")
            date_str = ""
            if date_el:
                raw = date_el.get("datetime", "") or date_el.get_text(strip=True)
                date_str = self.parse_date_flexible(raw[:10] if len(raw) > 10 else raw)
            desc_el = container.select_one(".lw_events_description, p, [class*='desc']")
            description = desc_el.get_text(strip=True)[:400] if desc_el else ""
            events.append(self.make_event(
                name=name, date=date_str, venue=site_name,
                description=description, url=url, priority=2
            ))
        return events

    def _extract_tribe(self, soup, site_name: str, base_url: str) -> List[Dict]:
        """Extract events from The Events Calendar (tribe) WordPress plugin."""
        events = []
        containers = (
            soup.select(".tribe-events-calendar-list__event")
            or soup.select(".type-tribe_events")
            or soup.select(".tribe-events-list-event")
            or soup.select(".tribe-event")
        )
        for container in containers[:30]:
            name_el = (
                container.select_one(".tribe-events-calendar-list__event-title")
                or container.select_one(".tribe-events-list-event-title")
                or container.select_one("h2, h3")
            )
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 4:
                continue
            link = name_el.find("a", href=True) or container.find("a", href=True)
            url = ""
            if link:
                href = link["href"]
                url = href if href.startswith("http") else base_url + href
            date_el = container.select_one("time, [class*='date'], abbr")
            date_str = ""
            if date_el:
                raw = date_el.get("datetime", "") or date_el.get_text(strip=True)
                if raw and "T" in raw:
                    raw = raw[:10]
                date_str = self.parse_date_flexible(raw)
            venue_el = container.select_one("[class*='venue']")
            venue = venue_el.get_text(strip=True) if venue_el else site_name
            desc_el = container.select_one("p, [class*='description']")
            description = desc_el.get_text(strip=True)[:400] if desc_el else ""
            events.append(self.make_event(
                name=name, date=date_str, venue=venue or site_name,
                description=description, url=url, priority=2
            ))
        return events

    def _extract_generic(self, soup, site_name: str, base_url: str) -> List[Dict]:
        """Generic HTML extraction — tries common event container patterns."""
        events = []
        containers = (
            soup.select(".event-item")
            or soup.select(".event-card")
            or soup.select(".event-listing")
            or soup.select("[class*='event-row']")
            or soup.select("[itemtype*='schema.org/Event']")
            or soup.select("article[class*='event']")
        )
        for container in containers[:30]:
            name_el = container.select_one("h1, h2, h3, h4, .event-title, .title, [class*='event-name']")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 4:
                continue
            link = container.find("a", href=True)
            url = ""
            if link:
                href = link["href"]
                url = href if href.startswith("http") else base_url.rstrip("/") + "/" + href.lstrip("/")
            date_el = container.select_one("time, [class*='date'], [class*='time']")
            date_str = ""
            if date_el:
                raw = date_el.get("datetime", "") or date_el.get_text(strip=True)
                date_str = self.parse_date_flexible(raw[:10] if len(raw) > 10 else raw)
            desc_el = container.select_one("p, [class*='desc'], [class*='excerpt']")
            description = desc_el.get_text(strip=True)[:400] if desc_el else ""
            events.append(self.make_event(
                name=name, date=date_str, venue=site_name,
                description=description, url=url, priority=2
            ))
        return events


def scrape() -> List[Dict]:
    """Module-level entry point."""
    return ExtendedCalendarsScraper().safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scrape()
    for e in results:
        print(f"  [{e['source']}] {e['date']} | {e['name']} | {e['venue']}")
    print(f"\nTotal LGBTQ-relevant: {len(results)} events across extended sources")
