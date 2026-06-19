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
    "strategy": "json_ld" | "dom" | "ical" | "dead",
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
    # strategy "ical":
    "ics_url": "https://.../events.ics", # optional override (else url)
    "note": "..."
  }

A spec with strategy "dead" is skipped (kept for the record). Every path
degrades to [] on failure - one bad site never aborts the rest.

Run standalone:  python scraper/rendered_sites.py [--only NAME] [--list]
"""

import argparse
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
        try:
            br = self._ensure_browser()
            pg = br.new_page(user_agent=_UA)
            pg.goto(url, timeout=30000, wait_until=wait_until or "domcontentloaded")
            if wait_ms:
                pg.wait_for_timeout(int(wait_ms))
            html = pg.content()
            pg.close()
            return html
        except Exception as e:
            logger.warning("[rendered_sites] render failed %s: %s %s",
                           url, type(e).__name__, str(e)[:120])
            return None

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
                name = (t_el.get_text(strip=True) if t_el else "").strip()
                if not name or len(name) < 4:
                    continue
                d_raw = ""
                if date_sel:
                    d_el = block.select_one(date_sel)
                    if d_el is not None:
                        d_raw = (d_el.get(date_attr, "") if date_attr else d_el.get_text(strip=True)) or ""
                elif date_attr:
                    d_raw = block.get(date_attr, "")
                date_str = self._parse_date(d_raw, date_fmt)
                if not date_str:
                    continue  # an event with no real date is useless downstream
                url = base_url
                if link_sel:
                    l_el = block.select_one(link_sel)
                    if l_el and l_el.get(link_attr):
                        url = urljoin(base_url, l_el.get(link_attr))
                events.append(self.make_event(
                    name=name, date=date_str, venue=venue, url=url, priority=priority))
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
        ('epoch_ms' | 'iso' | a strptime format)."""
        api = spec.get("json_url") or spec["url"]
        try:
            r = self.session.get(api, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.warning("[rendered_sites] json fetch failed %s: %s", api, e)
            return []
        # Walk dotted json_path to the list (supports top-level list too).
        node = data
        for part in (spec.get("json_path") or "").split("."):
            if not part:
                continue
            if isinstance(node, dict):
                node = node.get(part, [])
        items = node if isinstance(node, list) else []
        tk = spec.get("json_title_key", "title")
        dk = spec.get("json_date_key", "startDate")
        dfmt = spec.get("json_date_format", "epoch_ms")
        venue = spec["name"]
        priority = int(spec.get("priority", 2))
        events = []
        for it in items:
            if not isinstance(it, dict):
                continue
            name = str(it.get(tk, "")).strip()
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
            events.append(self.make_event(name=name, date=date_str, venue=venue,
                                          url=spec["url"], priority=priority))
        return events

    def _scrape_spec(self, spec: Dict) -> List[Dict]:
        strat = spec.get("strategy", "dom")
        if strat == "dead" or not spec.get("enabled", True):
            return []
        if strat == "ical":
            return self._extract_ical(spec)
        if strat == "json":
            return self._extract_json(spec)
        html = self._render(spec["url"], spec.get("wait_until", "domcontentloaded"),
                             spec.get("wait_ms", 2000))
        if not html:
            return []
        from bs4 import BeautifulSoup
        if strat == "json_ld":
            soup = BeautifulSoup(html, "html.parser")
            return self._extract_json_ld_from_soup(
                soup, spec["name"], int(spec.get("priority", 2)))
        return self._extract_dom(html, spec)

    def scrape(self) -> List[Dict]:
        specs = _load_specs()
        all_events = []
        try:
            for spec in specs:
                if spec.get("strategy") == "dead" or not spec.get("enabled", True):
                    continue
                try:
                    ev = self._scrape_spec(spec)
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
            print(f"  {spec['name']:42s} {len(ev):3d} events ({len(dated)} dated){flag}")
            out.extend(ev)
    finally:
        s._close_browser()
    print(f"\nTOTAL: {len(out)} events")
