"""Scrape broad Tulsa community event calendars and filter for LGBTQ-relevant results.

Sources:
- Visit Tulsa: https://www.visittulsa.com/events/
- Downtown Tulsa: https://downtowntulsa.com/experience/calendar
- Tulsa Arts District: https://thetulsaartsdistrict.org/events/list/
- Public Radio Tulsa: https://www.publicradiotulsa.org/community-calendar
- TulsaPeople: https://www.tulsapeople.com/local-events/
- ValueNews: https://valuenews.com/calendar-of-events
- AllEvents.in Tulsa: https://allevents.in/tulsa
- Tulsa World Events: https://tulsaworld.com/events/
- Gilcrease UnCrease Series: https://my.gilcrease.org/uncrease

Filter: only keep events whose name or description contains LGBTQ keywords.
"""

import sys
import os
import json
import re
import logging
import time
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

LGBTQ_KEYWORDS = [
    "lgbtq", "queer", "gay", "lesbian", "bi", "trans", "drag", "pride",
    "rainbow", "dyke", "nonbinary", "non-binary", "gender", "equality",
    "affirming", "inclusive", "homo", "sapphic",
]


def _is_lgbtq_relevant(name: str, description: str = "") -> bool:
    """Return True if the event appears LGBTQ-relevant."""
    combined = (name + " " + description).lower()
    return any(kw in combined for kw in LGBTQ_KEYWORDS)


class CommunityCalendarScraper(BaseScraper):
    """Scrape general Tulsa event calendars and filter for LGBTQ content."""

    source_name = "community_calendars"

    def scrape(self) -> List[Dict]:
        all_events = []

        all_events.extend(self._scrape_visit_tulsa())
        all_events.extend(self._scrape_downtown_tulsa())
        all_events.extend(self._scrape_tulsa_arts_district())
        all_events.extend(self._scrape_public_radio_tulsa())
        all_events.extend(self._scrape_tulsa_people())
        all_events.extend(self._scrape_value_news())
        all_events.extend(self._scrape_allevents())
        all_events.extend(self._scrape_tulsa_world())
        all_events.extend(self._scrape_gilcrease())

        lgbtq_events = [e for e in all_events if _is_lgbtq_relevant(e.get("name", ""), e.get("description", ""))]
        logger.info(
            f"[community_calendars] {len(all_events)} total scraped, "
            f"{len(lgbtq_events)} LGBTQ-relevant kept"
        )
        return lgbtq_events

    # ── Visit Tulsa ────────────────────────────────────────────────────────

    def _scrape_visit_tulsa(self) -> List[Dict]:
        url = "https://www.visittulsa.com/events/"
        soup = self.fetch_page(url)
        if not soup:
            logger.info("[community_calendars] Visit Tulsa: no response")
            return []

        events = []

        # Try JSON-LD first
        events = self._extract_json_ld(soup, "Visit Tulsa", priority=2)
        if events:
            self._random_delay()
            return events

        # Generic event containers
        containers = (
            soup.select(".event-card")
            or soup.select(".tribe-events-calendar-list__event")
            or soup.select(".type-tribe_events")
            or soup.select("[class*='event']")
        )
        for container in containers[:30]:
            event = self._parse_generic_container(container, "Visit Tulsa", url, 2)
            if event:
                events.append(event)

        self._random_delay()
        return events

    # ── Downtown Tulsa ─────────────────────────────────────────────────────

    def _scrape_downtown_tulsa(self) -> List[Dict]:
        url = "https://downtowntulsa.com/experience/calendar"
        soup = self.fetch_page(url)
        if not soup:
            logger.info("[community_calendars] Downtown Tulsa: no response")
            return []

        events = self._extract_json_ld(soup, "Downtown Tulsa", priority=2)
        if events:
            self._random_delay()
            return events

        containers = (
            soup.select(".event-card")
            or soup.select(".tribe-events-calendar-list__event")
            or soup.select("[class*='event-item']")
            or soup.select("article")
        )
        for container in containers[:30]:
            event = self._parse_generic_container(container, "Downtown Tulsa", url, 2)
            if event:
                events.append(event)

        self._random_delay()
        return events

    # ── Tulsa Arts District ────────────────────────────────────────────────

    def _scrape_tulsa_arts_district(self) -> List[Dict]:
        url = "https://thetulsaartsdistrict.org/events/list/"
        max_retries = 2

        for attempt in range(max_retries):
            try:
                self._rotate_user_agent()
                resp = self.session.get(url, timeout=20)

                if resp.status_code == 429:
                    wait = 10 * (attempt + 1)
                    logger.warning(f"[community_calendars] Arts District 429, waiting {wait}s")
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                soup_obj = __import__("bs4", fromlist=["BeautifulSoup"]).BeautifulSoup(
                    resp.text, "html.parser"
                )

                events = self._extract_json_ld(soup_obj, "Tulsa Arts District", priority=2)
                if events:
                    self._random_delay()
                    return events

                containers = (
                    soup_obj.select(".tribe-events-calendar-list__event")
                    or soup_obj.select(".type-tribe_events")
                    or soup_obj.select(".tribe-events-list-event")
                )
                for container in containers[:30]:
                    event = self._parse_tribe_container(container, url)
                    if event:
                        events.append(event)

                self._random_delay()
                return events

            except Exception as e:
                logger.warning(f"[community_calendars] Arts District attempt {attempt+1} failed: {e}")
                time.sleep(5)

        logger.error("[community_calendars] Tulsa Arts District failed after retries")
        return []

    # ── Public Radio Tulsa ─────────────────────────────────────────────────

    def _scrape_public_radio_tulsa(self) -> List[Dict]:
        url = "https://www.publicradiotulsa.org/community-calendar"
        soup = self.fetch_page(url)
        if not soup:
            logger.info("[community_calendars] Public Radio Tulsa: no response")
            return []

        events = self._extract_json_ld(soup, "Public Radio Tulsa", priority=2)
        if events:
            self._random_delay()
            return events

        containers = (
            soup.select(".event")
            or soup.select(".calendar-event")
            or soup.select("[class*='event']")
        )
        for container in containers[:30]:
            event = self._parse_generic_container(container, "Public Radio Tulsa", url, 2)
            if event:
                events.append(event)

        self._random_delay()
        return events

    # ── TulsaPeople ────────────────────────────────────────────────────────

    def _scrape_tulsa_people(self) -> List[Dict]:
        url = "https://www.tulsapeople.com/local-events/"
        soup = self.fetch_page(url)
        if not soup:
            logger.info("[community_calendars] TulsaPeople: no response")
            return []

        events = self._extract_json_ld(soup, "Tulsa", priority=2)
        if events:
            self._random_delay()
            return events

        # TulsaPeople uses The Events Calendar (tribe) plugin
        containers = (
            soup.select(".tribe-events-calendar-list__event")
            or soup.select(".type-tribe_events")
            or soup.select(".tribe-events-list-event")
            or soup.select(".eventlist-event")
            or soup.select("[class*='event-item']")
            or soup.select("article.post")
        )
        events = []
        for container in containers[:30]:
            event = self._parse_tribe_container(container, url) or \
                    self._parse_generic_container(container, "Tulsa", url, 2)
            if event:
                events.append(event)

        self._random_delay()
        return events

    # ── ValueNews ──────────────────────────────────────────────────────────

    def _scrape_value_news(self) -> List[Dict]:
        url = "https://valuenews.com/calendar-of-events"
        soup = self.fetch_page(url)
        if not soup:
            logger.info("[community_calendars] ValueNews: no response")
            return []

        events = self._extract_json_ld(soup, "Tulsa", priority=2)
        if events:
            self._random_delay()
            return events

        # ValueNews community calendar — try common patterns
        containers = (
            soup.select(".tribe-events-calendar-list__event")
            or soup.select(".type-tribe_events")
            or soup.select(".calendar-event")
            or soup.select(".event-listing")
            or soup.select("[class*='event']")
            or soup.select("article")
        )
        events = []
        for container in containers[:30]:
            event = self._parse_tribe_container(container, url) or \
                    self._parse_generic_container(container, "Tulsa", url, 2)
            if event:
                events.append(event)

        self._random_delay()
        return events

    # ── AllEvents.in ───────────────────────────────────────────────────────

    def _scrape_allevents(self) -> List[Dict]:
        # AllEvents.in uses a React frontend — try the search API first, then fall back to HTML
        api_url = "https://allevents.in/api/index.php"
        params = {
            "city": "Tulsa",
            "state": "Oklahoma",
            "country": "US",
            "format": "json",
            "page": 1,
            "limit": 50,
        }
        data = self.fetch_json(api_url, params=params)
        if data and isinstance(data, dict):
            items = data.get("data", data.get("events", data.get("results", [])))
            if isinstance(items, list) and items:
                events = []
                for item in items[:40]:
                    name = item.get("event_name") or item.get("name") or item.get("title", "")
                    if not name:
                        continue
                    start = item.get("start_time") or item.get("start") or item.get("date", "")
                    date_str = str(start)[:10] if start else ""
                    time_str = str(start)[11:16] if start and "T" in str(start) else ""
                    venue_info = item.get("venue") or item.get("location") or {}
                    venue = venue_info.get("name", "Tulsa") if isinstance(venue_info, dict) else str(venue_info)[:80]
                    description = (item.get("description") or item.get("event_description") or "")[:500]
                    event_url = item.get("event_url") or item.get("url") or "https://allevents.in/tulsa"
                    events.append(self.make_event(
                        name=name, date=date_str, time=time_str,
                        venue=venue, description=description, url=event_url, priority=2
                    ))
                if events:
                    self._random_delay()
                    return events

        # Fallback: scrape HTML listing page
        url = "https://allevents.in/tulsa"
        soup = self.fetch_page(url)
        if not soup:
            logger.info("[community_calendars] AllEvents.in: no response")
            return []

        events = self._extract_json_ld(soup, "Tulsa", priority=2)
        if events:
            self._random_delay()
            return events

        containers = (
            soup.select(".event-item")
            or soup.select("[class*='event-card']")
            or soup.select("[itemtype*='Event']")
            or soup.select("li.item")
        )
        events = []
        for container in containers[:30]:
            event = self._parse_generic_container(container, "Tulsa", url, 2)
            if event:
                events.append(event)

        self._random_delay()
        return events

    # ── Tulsa World ────────────────────────────────────────────────────────

    def _scrape_tulsa_world(self) -> List[Dict]:
        url = "https://tulsaworld.com/events/"
        soup = self.fetch_page(url)
        if not soup:
            logger.info("[community_calendars] Tulsa World: no response")
            return []

        # Tulsa World often has JSON-LD for structured article/event data
        events = self._extract_json_ld(soup, "Tulsa", priority=2)
        if events:
            self._random_delay()
            return events

        # Common newspaper CMS event patterns
        containers = (
            soup.select(".event-listing")
            or soup.select(".event-item")
            or soup.select("[class*='event-card']")
            or soup.select(".tribe-events-calendar-list__event")
            or soup.select(".type-tribe_events")
            or soup.select("article[class*='event']")
            or soup.select("article")
        )
        events = []
        for container in containers[:30]:
            event = self._parse_tribe_container(container, url) or \
                    self._parse_generic_container(container, "Tulsa", url, 2)
            if event:
                events.append(event)

        self._random_delay()
        return events

    # ── Gilcrease UnCrease ─────────────────────────────────────────────────

    def _scrape_gilcrease(self) -> List[Dict]:
        """Scrape Gilcrease Museum's UnCrease series — free community arts program,
        March-May 2026, local artists and performers, some LGBTQ-aligned events."""
        url = "https://my.gilcrease.org/uncrease"
        soup = self.fetch_page(url)
        if not soup:
            # Try alternate URL
            soup = self.fetch_page("https://gilcrease.org/events")
        if not soup:
            logger.info("[community_calendars] Gilcrease: no response")
            return []

        events = self._extract_json_ld(soup, "Gilcrease Museum", priority=2)
        if events:
            self._random_delay()
            return events

        containers = (
            soup.select(".event")
            or soup.select(".program-item")
            or soup.select("[class*='event']")
            or soup.select("article")
            or soup.select(".content-item")
        )
        events = []
        for container in containers[:20]:
            event = self._parse_generic_container(container, "Gilcrease Museum", url, 2)
            if event:
                # Tag as UnCrease series if not already in description
                if "uncrease" not in event.get("description", "").lower():
                    event["description"] = ("UnCrease series — free community arts. " + event["description"])[:500]
                events.append(event)

        self._random_delay()
        return events

    # ── Shared helpers ─────────────────────────────────────────────────────

    def _extract_json_ld(self, soup, venue_default: str, priority: int) -> List[Dict]:
        """Extract Event items from JSON-LD script blocks."""
        events = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw = script.string
                if not raw:
                    continue
                data = json.loads(raw)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") not in ("Event", "SocialEvent", "MusicEvent"):
                        continue
                    name = item.get("name", "")
                    if not name:
                        continue
                    start = item.get("startDate", "")
                    date_str = start[:10] if start else ""
                    time_str = ""
                    if "T" in start:
                        time_str = start.split("T")[1][:5]
                    location = item.get("location", {})
                    venue = venue_default
                    if isinstance(location, dict):
                        venue = location.get("name", venue_default)
                    description = item.get("description", "")[:500]
                    url = item.get("url", "")
                    events.append(self.make_event(
                        name=name,
                        date=date_str,
                        time=time_str,
                        venue=venue,
                        description=description,
                        url=url,
                        priority=priority,
                    ))
            except Exception:
                continue
        return events

    def _parse_generic_container(self, container, venue_default: str, base_url: str, priority: int) -> Optional[Dict]:
        """Parse a generic event container."""
        name_el = container.select_one("h1, h2, h3, h4, .event-title, .tribe-event-url")
        if not name_el:
            return None
        name = name_el.get_text(strip=True)
        if not name or len(name) < 5:
            return None

        link = container.find("a", href=True)
        url = ""
        if link:
            href = link["href"]
            url = href if href.startswith("http") else base_url.rstrip("/") + "/" + href.lstrip("/")

        date_el = container.select_one("time, [class*='date'], abbr")
        date_str = ""
        if date_el:
            raw = date_el.get("datetime", "") or date_el.get("title", "") or date_el.get_text(strip=True)
            date_str = self.parse_date_flexible(raw[:10] if len(raw) > 10 else raw)

        desc_el = container.select_one("p, [class*='description'], [class*='excerpt']")
        description = desc_el.get_text(strip=True)[:500] if desc_el else ""

        return self.make_event(
            name=name,
            date=date_str,
            venue=venue_default,
            description=description,
            url=url,
            priority=priority,
        )

    def _parse_tribe_container(self, container, base_url: str) -> Optional[Dict]:
        """Parse a The Events Calendar (tribe) container."""
        name_el = (
            container.select_one(".tribe-events-calendar-list__event-title")
            or container.select_one(".tribe-events-list-event-title")
            or container.select_one("h2, h3")
        )
        if not name_el:
            return None
        name = name_el.get_text(strip=True)
        if not name or len(name) < 5:
            return None

        link = name_el.find("a", href=True) or container.find("a", href=True)
        url = ""
        if link:
            href = link["href"]
            url = href if href.startswith("http") else base_url + href

        date_el = container.select_one("time, [class*='date']")
        date_str = ""
        if date_el:
            raw = date_el.get("datetime", "") or date_el.get_text(strip=True)
            if raw and "T" in raw:
                raw = raw[:10]
            date_str = self.parse_date_flexible(raw)

        venue_el = container.select_one("[class*='venue']")
        venue = venue_el.get_text(strip=True) if venue_el else "Tulsa Arts District"

        desc_el = container.select_one("p, [class*='description']")
        description = desc_el.get_text(strip=True)[:500] if desc_el else ""

        return self.make_event(
            name=name,
            date=date_str,
            venue=venue,
            description=description,
            url=url,
            priority=2,
        )


def scrape() -> List[Dict]:
    """Module-level entry point."""
    return CommunityCalendarScraper().safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    results = scrape()
    for e in results:
        print(f"  [{e['source']}] {e['date']} | {e['name']} | {e['venue']}")
    print(f"\nTotal LGBTQ-relevant: {len(results)} events")
