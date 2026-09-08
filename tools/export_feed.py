"""Public data feed export (Rung 6 seed: the read-API layer).

A live multi-city intelligence network needs a backend other tools can consume.
The reachable, no-hosting-required slice: emit a consolidated JSON feed to
docs/api/feed.json, which GitHub Pages already serves at
https://tulsagays.com/api/feed.json . That is a real public read-API endpoint,
not a stub -- other city tools, partners, or your own dashboards can pull it.

The feed bundles: this week's events, the coverage scorecard (how complete the
queer-org census coverage is), and live source counts. Full bidirectional API +
multi-city federation + partnerships remain blocked (hosting/money/external).

Run after coverage_report.py + the weekly elevate_blog refresh.
"""

import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper import dynamic_sources as dyn

# Event source, in priority order (2026-09-08 fix).
#
# THE BUG: this module used to read only docs/events-current.json. That file is
# NOT the week's events. tools/elevate_blog.py writes it as the top-8 feed for a
# small blog-page widget (`for e in week_events[:8]`). So docs/api/feed.json
# shipped "event_count": 8 while docs/index.html rendered 270 event cards for
# the same day, and docs/llms.txt advertises this endpoint to AI crawlers as
# "Machine-readable feed of this week's LGBTQ+ Tulsa events". Crawlers following
# llms.txt received 3% of the week, half of it Circle Cinema showtimes.
#
# THE FIX: prefer data/events/<week>_rendered.json, which tools/gen_website_html.py
# writes as the EXACT list of events it renders as cards (same list the homepage
# Event JSON-LD is built from). Feed count then equals card count by construction.
# Fall back to <week>_all.json (pre-filter, still the whole week) and only then to
# the 8-item widget file, so a partial repo still produces something.
RENDERED_FILE = os.path.join(config.DATA_DIR, "events",
                             f"{config.current_week_key()}_rendered.json")
WEEK_ALL_FILE = os.path.join(config.DATA_DIR, "events",
                             f"{config.current_week_key()}_all.json")
EVENTS_CURRENT = os.path.join(config.PROJECT_DIR, "docs", "events-current.json")
COVERAGE_FILE = os.path.join(config.DATA_DIR, "coverage_report.json")
OUT_DIR = os.path.join(config.PROJECT_DIR, "docs", "api")
OUT_FILE = os.path.join(OUT_DIR, "feed.json")

SCHEMA_VERSION = "1.0"
CITY = "Tulsa"


def _source_count():
    n = len(getattr(config, "SOURCES", {}))
    try:
        from scraper import facebook_events as fbe
        n += len(getattr(fbe, "PAGE_URLS", [])) + len(getattr(fbe, "GROUP_URLS", []))
    except Exception:
        pass
    try:
        from scraper import extended_calendars as ec
        n += len(getattr(ec, "SITES", []))
    except Exception:
        pass
    n += len(dyn.partner_keywords())
    return n


def _load_events():
    """Return (events, source_path) using the best available week source."""
    for path in (RENDERED_FILE, WEEK_ALL_FILE, EVENTS_CURRENT):
        if not os.path.exists(path):
            continue
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        evs = data.get("events", []) if isinstance(data, dict) else data
        if isinstance(evs, list) and evs:
            return [e for e in evs if isinstance(e, dict)], path
    return [], None


def build_feed(date_str=None):
    events, src_path = _load_events()

    coverage = {}
    if os.path.exists(COVERAGE_FILE):
        try:
            c = json.load(open(COVERAGE_FILE, encoding="utf-8"))
            coverage = {"coverage_pct": c.get("coverage_pct"),
                        "covered": c.get("covered"), "total": c.get("total"),
                        "gaps": c.get("gaps")}
        except Exception:
            coverage = {}

    # NOTE (2026-09-08): deliberately NO per-event site URL here. The /e/ share
    # pages are named by tools/gen_website_html.py::_card_id, which slugs
    # name-date-HOUR (formatted hour, 60-char truncation, collision suffixes) and
    # is NOT the same scheme as the Event JSON-LD @id in that same file. Emitting
    # a third guess at the slug would publish links that 404, so the feed carries
    # only the organizer url the event actually has.
    slim = [{"name": e.get("name"), "date": e.get("date"), "time": e.get("time"),
             "venue": e.get("venue"), "url": e.get("url")} for e in events]

    return {
        "schema_version": SCHEMA_VERSION,
        "city": CITY,
        "generated": date_str or datetime.now().strftime("%Y-%m-%d"),
        "license": "Free to use with attribution to tulsagays.com",
        "coverage": coverage,
        "source_count": _source_count(),
        "event_count": len(slim),
        "events_source": os.path.relpath(src_path, config.PROJECT_DIR).replace("\\", "/") if src_path else None,
        "events": slim,
    }


def run(date_str=None):
    os.makedirs(OUT_DIR, exist_ok=True)
    feed = build_feed(date_str)
    json.dump(feed, open(OUT_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"[export_feed] wrote {OUT_FILE}: {feed['event_count']} events "
          f"(from {feed['events_source']}), {feed['source_count']} sources, "
          f"coverage {feed['coverage'].get('coverage_pct')}%")
    return feed


if __name__ == "__main__":
    date = os.environ.get("SOURCE_GROWTH_DATE")
    run(date)
