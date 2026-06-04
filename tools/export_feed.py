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


def build_feed(date_str=None):
    events = []
    if os.path.exists(EVENTS_CURRENT):
        try:
            data = json.load(open(EVENTS_CURRENT, encoding="utf-8"))
            events = data.get("events", []) if isinstance(data, dict) else data
        except Exception:
            events = []

    coverage = {}
    if os.path.exists(COVERAGE_FILE):
        try:
            c = json.load(open(COVERAGE_FILE, encoding="utf-8"))
            coverage = {"coverage_pct": c.get("coverage_pct"),
                        "covered": c.get("covered"), "total": c.get("total"),
                        "gaps": c.get("gaps")}
        except Exception:
            coverage = {}

    slim = [{"name": e.get("name"), "date": e.get("date"), "time": e.get("time"),
             "venue": e.get("venue"), "url": e.get("url")} for e in events if isinstance(e, dict)]

    return {
        "schema_version": SCHEMA_VERSION,
        "city": CITY,
        "generated": date_str or datetime.now().strftime("%Y-%m-%d"),
        "license": "Free to use with attribution to tulsagays.com",
        "coverage": coverage,
        "source_count": _source_count(),
        "event_count": len(slim),
        "events": slim,
    }


def run(date_str=None):
    os.makedirs(OUT_DIR, exist_ok=True)
    feed = build_feed(date_str)
    json.dump(feed, open(OUT_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"[export_feed] wrote {OUT_FILE}: {feed['event_count']} events, "
          f"{feed['source_count']} sources, coverage {feed['coverage'].get('coverage_pct')}%")
    return feed


if __name__ == "__main__":
    date = os.environ.get("SOURCE_GROWTH_DATE")
    run(date)
