"""Config-driven rendered-site scraper - revives JS-rendered venue calendars.

Many Tulsa venue / calendar sites serve a JavaScript shell: a plain `requests`
fetch sees no events, so extended_calendars silently returned zero for ~39 of
them. This module renders each site with Playwright and extracts events using a
per-site spec from data/rendered_site_specs.json, so adding/repairing a site is
a data edit, not new code.

Spec schema (one object per site in data/rendered_site_specs.json):
  {
    "name": "Philbrook Museum",          # display + source label
    "url": "https://philbrook.org/calendar/",
    "strategy": "json_ld" | "dom" | "json" | "ical" | "dead",
    "enabled": true,
    "priority": 2,
    "lgbtq_only": false,                 # if false, runner relevance filter applies
    "wait_until": "networkidle",         # playwright goto wait (default domcontentloaded)
    "wait_ms": 2500,                      # extra settle after load
    # strategy "dom":
    "container": ".event-card",          # CSS selector, repeating event block
    "title": "h3",                        # CSS selector within container
    "date": "time",                       # CSS selector within container
    "date_attr": "datetime",             # read this attribute instead of text (optional)
    "date_format": "iso",                # "iso" | "auto" | a strptime format
    "link": "a", "link_attr": "href",   # optional
    # strategy "json" (optional):
    "json_venue_key": "location",        # per-event venue (else spec name)
    "json_link_key": "uri",              # per-event link, joined onto url
    "json_link_prefix": "/event/",       # prepended to json_link_key value
    # strategy "ical":
    "ics_url": "https://.../events.ics", # optional override (else url)
    # strategy "json_ld" (optional):
    "metro_only": true,                   # drop events whose schema.org addressLocality
                                          # is not in config.METRO_CITIES (2026-11-06)
    "note": "..."
  }

A spec with strategy "dead" is skipped (kept for the record). Every path
degrades to [] on failure - one bad site never aborts the rest.

Run standalone:  python scraper/rendered_sites.py [--only NAME] [--list]
"""

import argparse
import html as _html
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urljoin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper

logger = logging.getLogger(__name__)

SPECS_FILE = Path(__file__).resolve().parent.parent / "data" / "rendered_site_specs.json"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36")


def _load_specs() -> List[Dict]:
    if not SPECS_FILE.exists():
        logger.warning("[rendered_sites] no specs file at %s", SPECS_FILE)
        return []
    try:
        return json.loads(SPECS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("[rendered_sites] specs parse failed: %s", e)
        return []


class RenderedSitesScraper(BaseScraper):
    source_name = "rendered_sites"

    def __init__(self):
        super().__init__()
        self._pw = None
        self._browser = None

    # ── Playwright lifecycle (lazy, shared across sites in one run) ────────────
    def _ensure_browser(self):
        if self._browser is not None:
            return self._browser
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        return self._browser

    def _close_browser(self):
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._browser = None
        self._pw = None

    def _render(self, url: str, wait_until: str, wait_ms: int) -> Optional[str]:
        pg = None
        try:
            br = self._ensure_browser()
            pg = br.new_page(user_agent=_UA)
            try:
                pg.goto(url, timeout=30000, wait_until=wait_until or "domcontentloaded")
            except Exception as e:
                # "networkidle" never settles on sites that keep polling (analytics,
                # chat widgets, ticketing beacons), but their DOM finished rendering
                # long before the 30s cap. Until 2026-11-06 a timeout here threw the
                # whole rendered page away, so Philbrook, Tulsa Zoo, Cain's Ballroom
                # and Discovery Lab silently returned 0 events. Keep what rendered;
                # only a navigation that never committed (still about:blank) or a
                # non-timeout error (DNS, TLS) counts as a failed render.
                if type(e).__name__ != "TimeoutError" or (pg.url or "about:blank") == "about:blank":
                    raise
                logger.info("[rendered_sites] %s: '%s' wait timed out, using the DOM as rendered",
                            url, wait_until)
            if wait_ms:
                pg.wait_for_timeout(int(wait_ms))
            return pg.content()
        except Exception as e:
            logger.warning("[rendered_sites] render failed %s: %s %s",
                           url, type(e).__name__, str(e)[:120])
            return None
        finally:
            if pg is not None:
                try:
                    pg.close()
                except Exception:
                    pass

    # ── date parsing ──────────────────────────────────────────────────────────
    @staticmethod
    def _parse_date(raw: str, fmt: str) -> str:
        """Return YYYY-MM-DD or '' from a raw date string per the spec format."""
        if not raw:
            return ""
        raw = raw.strip()
        if fmt == "iso" or fmt == "":
            # ISO8601 (with or without time) - take the date part.
            m = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
            if m:
                return m.group(1)
        if fmt and fmt not in ("iso", "auto"):
            try:
                return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
        # auto / fallback: try the base flexible parser, then common patterns.
        flexible = BaseScraper.parse_date_flexible(raw)
        if re.match(r"\d{4}-\d{2}-\d{2}", flexible or ""):
            return flexible[:10]
        # last resort: pull a "Month DD, YYYY" substring out of noisy text like
        # "June 19, 2026 @ 6:00 PM - 8:00 PM" or "October 29 & 30, 2026".
        m = re.search(r"([A-Z][a-z]+)\s+(\d{1,2})(?:[^,]*?)?,?\s*(\d{4})", raw)
        if m:
            for mfmt in ("%B %d %Y", "%b %d %Y"):
                try:
                    return datetime.strptime(
                        f"{m.group(1)} {m.group(2)} {m.group(3)}", mfmt
                    ).strftime("%Y-%m-%d")
                except ValueError:
                    continue
        return ""

    # ── extraction strategies ───────────────────────────────────────────────
    def _extract_dom(self, html: str, spec: Dict) -> List[Dict]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        container = spec.get("container")
        if not container:
            return []
        title_sel = spec.get("title")
        date_sel = spec.get("date")
        date_attr = spec.get("date_attr")
        date_fmt = spec.get("date_format", "auto")
        link_sel = spec.get("link")
        link_attr = spec.get("link_attr", "href")
        venue = spec["name"]
        base_url = spec["url"]
        priority = int(spec.get("priority", 2))
        events = []
        for block in soup.select(container)[:40]:
            try:
                t_el = block.select_one(title_sel) if title_sel else block
                # get_text(" ", ...) keeps a separator between nested spans —
                # bare strip=True concatenated "July"+"11" into unparseable
                # "July11" (killed BOK Center and Green Country dates).
                name = (t_el.get_text(" ", strip=True) if t_el else "").strip()
                if not name or len(name) < 4:
                    continue
                # Take the FIRST match that parses as a date, not just the first
                # match. 2026-11-06: Eventbrite put an urgency label ("Going fast",
                # "Almost full") in the first <p> of each card, so Magic City Books
                # read the label as its date and returned 0 events.
                date_str, d_els, date_idx = "", [], None
                if date_sel:
                    d_els = block.select(date_sel)
                    for i, d_el in enumerate(d_els):
                        d_raw = (d_el.get(date_attr, "") if date_attr else d_el.get_text(" ", strip=True)) or ""
                        date_str = self._parse_date(d_raw, date_fmt)
                        if date_str:
                            date_idx = i
                            break
                elif date_attr:
                    date_str = self._parse_date(block.get(date_attr, ""), date_fmt)
                if not date_str:
                    continue  # an event with no real date is useless downstream
                # Optional per-event venue. An organizer page (a bookstore's
                # Eventbrite) lists events held elsewhere; labelling them with the
                # organizer's name sends readers to the wrong building.
                #   venue_sel: CSS within the block
                #   venue_after_date: true -> the venue_sel match right after the date
                ev_venue = venue
                vsel = spec.get("venue_sel")
                if vsel:
                    if spec.get("venue_after_date") and vsel == date_sel and date_idx is not None:
                        v_cands = d_els[date_idx + 1:date_idx + 2]
                    else:
                        v_cands = block.select(vsel)[:1]
                    v_txt = v_cands[0].get_text(" ", strip=True) if v_cands else ""
                    if v_txt and len(v_txt) <= 120 and not self._parse_date(v_txt, "auto"):
                        ev_venue = v_txt
                url = base_url
                if link_sel:
                    l_el = block.select_one(link_sel)
                    if l_el and l_el.get(link_attr):
                        url = urljoin(base_url, l_el.get(link_attr))
                events.append(self.make_event(
                    name=name, date=date_str, venue=ev_venue, url=url, priority=priority))
            except Exception:
                continue
        return events

    def _extract_ical(self, spec: Dict) -> List[Dict]:
        """Minimal iCal VEVENT parse (DTSTART + SUMMARY). No external dep."""
        ics = spec.get("ics_url") or spec["url"]
        soup_text = None
        try:
            r = self.session.get(ics, timeout=20)
            r.raise_for_status()
            soup_text = r.text
        except Exception as e:
            logger.warning("[rendered_sites] ical fetch failed %s: %s", ics, e)
            return []
        if "BEGIN:VCALENDAR" in soup_text:
            self.last_read = {"ok": True, "items": soup_text.count("BEGIN:VEVENT")}
        events = []
        venue = spec["name"]
        priority = int(spec.get("priority", 2))
        cur = {}
        for line in soup_text.splitlines():
            line = line.strip()
            if line == "BEGIN:VEVENT":
                cur = {}
            elif line.startswith("SUMMARY"):
                cur["name"] = line.split(":", 1)[-1].strip()
            elif line.startswith("DTSTART"):
                val = line.split(":", 1)[-1].strip()
                m = re.match(r"(\d{4})(\d{2})(\d{2})", val)
                if m:
                    cur["date"] = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            elif line == "END:VEVENT":
                if cur.get("name") and cur.get("date"):
                    events.append(self.make_event(
                        name=cur["name"], date=cur["date"], venue=venue,
                        url=spec["url"], priority=priority))
        return events

    def _extract_json(self, spec: Dict) -> List[Dict]:
        """Fetch a same-origin JSON event API and extract per the spec.

        Spec fields: json_url (else url), json_path (dotted path to the list,
        e.g. 'upcoming' or 'events'), json_title_key (default 'title'),
        json_date_key (default 'startDate'), json_date_format
        ('epoch_ms' | 'iso' | a strptime format).

        Added 2026-11-06 for APIs that need a date window or a page token:
          json_params   query params; a dict/list value is sent JSON-encoded
                        (Communico's req={...}). "{today}" and "{token}" are
                        filled in every param, header and the json_url.
          json_headers  extra request headers (e.g. X-Requested-With).
          json_token_page + json_token_regex
                        fetch this page and take regex group 1 as {token}
                        (SiteWrench calendars rotate a per-page token)."""
        api = spec.get("json_url") or spec["url"]
        ctx = {"{today}": datetime.now().strftime("%Y-%m-%d"), "{token}": ""}

        def fill(val: str) -> str:
            for k, v in ctx.items():
                val = val.replace(k, v)
            return val

        if spec.get("json_token_page") and spec.get("json_token_regex"):
            try:
                tr = self.session.get(spec["json_token_page"], timeout=20)
                tr.raise_for_status()
                m = re.search(spec["json_token_regex"], tr.text)
            except Exception as e:
                logger.warning("[rendered_sites] %s: token page fetch failed: %s", spec["name"], e)
                return []
            if not m:
                logger.warning("[rendered_sites] %s: token not found on %s",
                               spec["name"], spec["json_token_page"])
                return []
            ctx["{token}"] = m.group(1)
        params = None
        if spec.get("json_params"):
            params = {}
            for k, v in spec["json_params"].items():
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, separators=(",", ":"))
                params[k] = fill(str(v))
        headers = {k: fill(str(v)) for k, v in (spec.get("json_headers") or {}).items()} or None
        try:
            r = self.session.get(fill(api), params=params, headers=headers, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.warning("[rendered_sites] json fetch failed %s: %s", api, e)
            return []
        # Walk dotted json_path to the list (supports top-level list too).
        node = data
        path_ok = True
        for part in (spec.get("json_path") or "").split("."):
            if not part:
                continue
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                path_ok = False  # key renamed/missing: a broken feed, never IDLE
                node = []
        items = node if isinstance(node, list) else []
        if path_ok and isinstance(node, list):
            self.last_read = {"ok": True, "items": len(items)}
        tk = spec.get("json_title_key", "title")
        dk = spec.get("json_date_key", "startDate")
        dfmt = spec.get("json_date_format", "epoch_ms")
        # Optional per-event venue/link keys (added 2026-09-02 for the Presence
        # club API, whose events carry a real room like "MP 544"). Absent these,
        # behaviour is unchanged: venue falls back to the spec name.
        vk = spec.get("json_venue_key")
        lk = spec.get("json_link_key")
        venue = spec["name"]
        priority = int(spec.get("priority", 2))
        events = []
        for it in items:
            if not isinstance(it, dict):
                continue
            # WordPress / Tribe APIs return titles HTML-escaped ("Men&#8217;s
            # Soccer"). Unescape here or the entity ships to the slide + website.
            name = _html.unescape(str(it.get(tk, ""))).strip()
            rawd = it.get(dk, "")
            date_str = ""
            try:
                if dfmt == "epoch_ms" and rawd:
                    date_str = datetime.fromtimestamp(int(rawd) / 1000).strftime("%Y-%m-%d")
                elif dfmt == "iso":
                    date_str = str(rawd)[:10]
                else:
                    date_str = self._parse_date(str(rawd), dfmt)
            except (ValueError, OverflowError, OSError, TypeError):
                date_str = ""
            if not name or not date_str or not re.match(r"\d{4}-\d{2}-\d{2}", date_str):
                continue
            ev_venue = venue
            if vk:
                cand = _html.unescape(str(it.get(vk) or "")).strip()
                if cand:
                    ev_venue = cand
            ev_url = spec["url"]
            if lk:
                cand = str(it.get(lk) or "").strip()
                if cand:
                    ev_url = urljoin(spec["url"],
                                     spec.get("json_link_prefix", "") + cand)
            events.append(self.make_event(name=name, date=date_str, venue=ev_venue,
                                          url=ev_url, priority=priority))
        return events

    def _scrape_spec(self, spec: Dict) -> List[Dict]:
        """Extract one spec's raw events, with no exclude/relevance filtering
        applied. The health guard and auto-repair call this directly, so it
        measures whether the page still parses, not whether today's calendar
        happens to be all excluded/irrelevant content (2026-11-09: Expo Square
        parsed 5 clean events during Color Breed Congress week, but
        exclude_title_regex used to run in here too, so the health guard saw 0
        and escalated a working scraper as broken). `_keep_for_production`
        applies exclude_title_regex and require_lgbtq_match after this."""
        return self._scrape_spec_raw(spec)

    @staticmethod
    def _keep_for_production(spec: Dict, evs: List[Dict]) -> List[Dict]:
        """`exclude_title_regex` (optional) drops notices/irrelevant events that
        share a calendar with real events ("Early Park Closure", a week-long
        breed congress at Expo Square). `require_lgbtq_match` (optional) keeps
        only LGBTQ-keyword events in the weekly scrape. For high-volume general
        feeds (the library runs ~285 events a fortnight, almost all storytimes
        and classes) the trusted-venue path would otherwise flood the website.
        The health guard calls _scrape_spec directly (not this), so it still
        measures whether the feed parses at all, independent of either filter."""
        rx = spec.get("exclude_title_regex")
        if rx and evs:
            pat = re.compile(rx)
            evs = [e for e in evs if not pat.search(e.get("name", ""))]
        if not spec.get("require_lgbtq_match"):
            return evs
        from scraper.extended_calendars import _is_lgbtq_relevant
        return [e for e in evs if _is_lgbtq_relevant(e.get("name", ""), e.get("description", ""))]

    def _scrape_spec_raw(self, spec: Dict) -> List[Dict]:
        # last_read lets the health guard tell an API feed that answered with
        # nothing scheduled (IDLE: a seasonal farmers market, a club calendar
        # between terms) from one that failed to answer (DEAD). Set by the json
        # and ical readers only; a DOM page with no matching blocks stays DEAD
        # because that is indistinguishable from selector rot.
        self.last_read = {"ok": False, "items": None}
        strat = spec.get("strategy", "dom")
        if strat == "dead" or not spec.get("enabled", True):
            return []
        if strat == "ical":
            return self._extract_ical(spec)
        if strat == "json":
            return self._extract_json(spec)
        if spec.get("render") is False:
            # Server-rendered page behind an anti-bot interstitial that challenges
            # headless Chromium but not a plain HTTP client (108 Contemporary's
            # SiteGround "Checking your browser...", 2026-11-06).
            try:
                r = self.session.get(spec["url"], timeout=20)
                r.raise_for_status()
                html = r.text
            except Exception as e:
                logger.warning("[rendered_sites] fetch failed %s: %s", spec["url"], e)
                return []
        else:
            html = self._render(spec["url"], spec.get("wait_until", "domcontentloaded"),
                                 spec.get("wait_ms", 2000))
        if not html:
            return []
        from bs4 import BeautifulSoup
        if strat == "json_ld":
            soup = BeautifulSoup(html, "html.parser")
            evs = self._extract_json_ld_from_soup(
                soup, spec["name"], int(spec.get("priority", 2)))
            # A room name alone ("Riffs", "Track 5.") is meaningless to a reader;
            # anchor it to the complex when the spec names one.
            parent = spec.get("venue_parent")
            if parent:
                for ev in evs:
                    v = (ev.get("venue") or "").strip().rstrip(".")
                    if v and v != spec["name"] and parent.lower() not in v.lower():
                        ev["venue"] = f"{v} at {parent}"
            if spec.get("metro_only"):
                evs = self._drop_out_of_metro(soup, evs, spec["name"])
            return evs
        return self._extract_dom(html, spec)

    @staticmethod
    def _drop_out_of_metro(soup, evs: List[Dict], name: str) -> List[Dict]:
        """`metro_only` (optional, json_ld only): drop events whose schema.org
        address names a city outside config.METRO_CITIES. Regional aggregators
        file distant towns under one metro (Songkick's "Tulsa" page carried
        Fort Smith, AR and Pocola shows on 2026-11-06), and the json_ld venue is
        the place name only, so the runner's region filter has no city to read.
        Matched on the event url; an event whose markup names no city is kept."""
        import config
        metro = {c.lower() for c in getattr(config, "METRO_CITIES", [])}
        city_by_url: Dict[str, str] = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or script.get_text() or "")
            except Exception:
                continue
            items = data if isinstance(data, list) else (
                data.get("@graph", [data]) if isinstance(data, dict) else [])
            for it in items:
                if not isinstance(it, dict) or not it.get("url"):
                    continue
                loc = it.get("location")
                if isinstance(loc, list):
                    loc = next((l for l in loc if isinstance(l, dict)), None)
                addr = loc.get("address") if isinstance(loc, dict) else None
                city = addr.get("addressLocality") if isinstance(addr, dict) else None
                if isinstance(city, str) and city.strip():
                    city_by_url[it["url"]] = city.strip()
        kept, dropped = [], []
        for ev in evs:
            city = city_by_url.get(ev.get("url", ""))
            (kept if city is None or city.lower() in metro else dropped).append(ev)
        if dropped:
            logger.info("[rendered_sites] %s: dropped %d out-of-metro events (%s)", name,
                        len(dropped), ", ".join(sorted({city_by_url[e["url"]] for e in dropped})))
        return kept

    def scrape(self) -> List[Dict]:
        specs = _load_specs()
        all_events = []
        try:
            for spec in specs:
                if spec.get("strategy") == "dead" or not spec.get("enabled", True):
                    continue
                try:
                    raw = self._scrape_spec(spec)
                    ev = self._keep_for_production(spec, raw)
                    if len(ev) != len(raw):
                        logger.info("[rendered_sites] %s: %d events (%d parsed, kept LGBTQ matches only)",
                                    spec["name"], len(ev), len(raw))
                    else:
                        logger.info("[rendered_sites] %s: %d events", spec["name"], len(ev))
                    all_events.extend(ev)
                except Exception as e:
                    logger.warning("[rendered_sites] %s crashed: %s", spec.get("name"), e)
        finally:
            self._close_browser()
        return all_events


def scrape() -> List[Dict]:
    return RenderedSitesScraper().safe_scrape()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="run only specs whose name contains this")
    ap.add_argument("--list", action="store_true", help="list specs and exit")
    args = ap.parse_args()
    specs = _load_specs()
    if args.list:
        for s in specs:
            print(f"  [{s.get('strategy','?'):8s}] {s['name']}  <- {s['url']}")
        print(f"({len(specs)} specs)")
        sys.exit(0)
    s = RenderedSitesScraper()
    out = []
    try:
        for spec in specs:
            if args.only and args.only.lower() not in spec["name"].lower():
                continue
            if spec.get("strategy") == "dead" or not spec.get("enabled", True):
                continue
            ev = s._scrape_spec(spec)
            dated = [e for e in ev if len(e.get("date", "")) == 10]
            flag = "" if dated else "  <-- 0 dated"
            kept = s._keep_for_production(spec, ev)
            if len(kept) != len(ev):
                flag += f"  (weekly scrape keeps {len(kept)} LGBTQ matches)"
            print(f"  {spec['name']:42s} {len(ev):3d} events ({len(dated)} dated){flag}", flush=True)
            out.extend(ev)
    finally:
        s._close_browser()
    print(f"\nTOTAL: {len(out)} events")
