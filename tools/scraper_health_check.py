#!/usr/bin/env python3
"""Scraper health guard - detects SILENTLY broken TulsaGays scrapers.

A scraper is "silently broken" when it stops returning events without ever
erroring loudly: DNS death, a site that went JS-only, changed HTML structure,
or a parse that yields junk rows with no real dates. That is exactly how Elote,
black_queer_tulsa, and ~40 of the extended_calendars sources rotted unnoticed -
the weekly pipeline still produced 197 events because the aggregators (Google /
Facebook / Eventbrite) backfilled the gaps, so nothing ever looked wrong.

This guard runs every source, classifies each as OK / JUNK / DEAD by raw and
dated yield, writes data/scraper_health.json, diffs against the previous run,
and on NEW breakage (a source that was OK and is now JUNK/DEAD) writes an alert
to the vault action inbox so William sees it on the dashboard + Telegram digest.

Classification:
  OK   - returned at least one event with a parseable YYYY-MM-DD date
  JUNK - returned raw rows but ZERO had a real date (the Elote failure mode)
  DEAD - returned nothing, or the scraper raised
  SKIP - intentionally not probed this run (slow aggregator / --quick)

Usage:
  python tools/scraper_health_check.py            # web + community sources
  python tools/scraper_health_check.py --full     # also slow aggregators
  python tools/scraper_health_check.py --quick     # multi-site sub-sources only
  python tools/scraper_health_check.py --no-alert  # never write to action inbox
  python tools/scraper_health_check.py --json      # machine-readable summary only
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.disable(logging.CRITICAL)  # scrapers are noisy; the guard speaks for them

HEALTH_FILE = ROOT / "data" / "scraper_health.json"
# Vault action inbox (syncs to Obsidian + dashboard + Telegram digest).
PENDING_ACTIONS = Path(r"C:\Users\willi\.claude\pending-william-actions.md")

OK, JUNK, DEAD, SKIP = "OK", "JUNK", "DEAD", "SKIP"


def _is_dated(ev: dict) -> bool:
    """True if the event carries a real YYYY-MM-DD date (not '', not 'Jun20')."""
    d = (ev.get("date") or "").strip()
    return len(d) == 10 and d[:4].isdigit() and d[4] == "-"


def _classify(raw_count: int, dated_count: int) -> str:
    if raw_count == 0:
        return DEAD
    if dated_count == 0:
        return JUNK
    return OK


# ── Sub-source probes for the two big multi-site modules ──────────────────────

def _probe_community_groups() -> list:
    from scraper.community_groups import CommunityGroupsScraper
    s = CommunityGroupsScraper()
    out = []
    for key, url in s.SOURCES.items():
        t0 = time.time()
        try:
            if key in getattr(s, "SQUARESPACE_JSON_SOURCES", set()):
                ev = s._scrape_squarespace_json(key, url)
            else:
                ev = s._scrape_source(key, url)
            dated = sum(1 for e in ev if _is_dated(e))
            out.append({"source": f"community_groups/{key}", "url": url,
                        "raw": len(ev), "dated": dated,
                        "status": _classify(len(ev), dated),
                        "secs": round(time.time() - t0, 1)})
        except Exception as e:
            out.append({"source": f"community_groups/{key}", "url": url,
                        "raw": 0, "dated": 0, "status": DEAD,
                        "error": f"{type(e).__name__}: {str(e)[:80]}",
                        "secs": round(time.time() - t0, 1)})
    return out


def _probe_extended_calendars() -> list:
    import scraper.extended_calendars as ec
    import inspect
    cls = [c for _, c in inspect.getmembers(ec, inspect.isclass)
           if hasattr(c, "_scrape_site")][0]
    s = cls()
    out = []
    for url, name, category, lgbtq_only in ec.SITES:
        t0 = time.time()
        try:
            ev = s._scrape_site(url, name, lgbtq_only)
            dated = sum(1 for e in ev if _is_dated(e))
            out.append({"source": f"extended_calendars/{name}", "url": url,
                        "raw": len(ev), "dated": dated,
                        "status": _classify(len(ev), dated),
                        "secs": round(time.time() - t0, 1)})
        except Exception as e:
            out.append({"source": f"extended_calendars/{name}", "url": url,
                        "raw": 0, "dated": 0, "status": DEAD,
                        "error": f"{type(e).__name__}: {str(e)[:80]}",
                        "secs": round(time.time() - t0, 1)})
    return out


def _probe_rendered_sites() -> list:
    """Per-spec health for the config-driven rendered-site scraper (Playwright).
    Each enabled spec is run individually so one breaking (e.g. Cain's changes
    its DOM) is flagged on its own, not hidden in a module-level total."""
    from scraper.rendered_sites import RenderedSitesScraper, _load_specs
    s = RenderedSitesScraper()
    out = []
    try:
        for spec in _load_specs():
            if spec.get("strategy") == "dead" or not spec.get("enabled", True):
                continue
            t0 = time.time()
            try:
                ev = s._scrape_spec(spec)
                dated = sum(1 for e in ev if _is_dated(e))
                out.append({"source": f"rendered_sites/{spec['name']}", "url": spec.get("url", ""),
                            "raw": len(ev), "dated": dated,
                            "status": _classify(len(ev), dated),
                            "secs": round(time.time() - t0, 1)})
            except Exception as e:
                out.append({"source": f"rendered_sites/{spec['name']}", "url": spec.get("url", ""),
                            "raw": 0, "dated": 0, "status": DEAD,
                            "error": f"{type(e).__name__}: {str(e)[:80]}",
                            "secs": round(time.time() - t0, 1)})
    finally:
        s._close_browser()
    return out


def _probe_module(name: str, fn) -> dict:
    """Run a module-level scrape() and classify by dated yield."""
    t0 = time.time()
    try:
        ev = fn() or []
        dated = sum(1 for e in ev if _is_dated(e))
        return {"source": name, "raw": len(ev), "dated": dated,
                "status": _classify(len(ev), dated),
                "secs": round(time.time() - t0, 1)}
    except Exception as e:
        return {"source": name, "raw": 0, "dated": 0, "status": DEAD,
                "error": f"{type(e).__name__}: {str(e)[:80]}",
                "secs": round(time.time() - t0, 1)}


def _module_level_checks(full: bool) -> list:
    """Module-level scrape() checks for the non-multi-site scrapers.

    The slow aggregators (Google/Facebook/Eventbrite/Playwright/Slack) are only
    run with --full so the routine guard finishes in ~1-2 min, not ~10."""
    from scraper import (recurring, specific_orgs, twisted_arts, churches, bars,
                         ticketing_sites, okeq_calendar, qlist, homo_hotel,
                         tulsa_arts_district, community_calendars, instagram_orgs,
                         studio66, aa_meetings)
    mods = [
        ("recurring", recurring.scrape),
        ("specific_orgs", specific_orgs.scrape),
        ("twisted_arts", twisted_arts.scrape),
        ("churches", churches.scrape),
        ("bars", bars.scrape),
        ("ticketing_sites", ticketing_sites.scrape),
        ("okeq_calendar", okeq_calendar.scrape),
        ("qlist", qlist.scrape),
        ("homo_hotel", homo_hotel.scrape),
        ("tulsa_arts_district", tulsa_arts_district.scrape),
        ("community_calendars", community_calendars.scrape),
        ("instagram_orgs", instagram_orgs.scrape),
        ("studio_66", studio66.scrape),
        ("aa_meetings", aa_meetings.scrape),
    ]
    if full:
        from scraper import eventbrite_meetup, facebook_events, timetree_scraper
        mods += [
            ("eventbrite_meetup", eventbrite_meetup.scrape),
            ("facebook_events", facebook_events.scrape),
            ("timetree_scraper", timetree_scraper.scrape),
        ]
    return [_probe_module(n, f) for n, f in mods]


def run(full: bool = False, quick: bool = False) -> list:
    results = []
    results += _probe_community_groups()
    results += _probe_extended_calendars()
    results += _probe_rendered_sites()
    if not quick:
        results += _module_level_checks(full)
    return results


def _load_prev() -> dict:
    if HEALTH_FILE.exists():
        try:
            data = json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
            return {r["source"]: r["status"] for r in data.get("results", [])}
        except Exception:
            return {}
    return {}


def _write_health(results: list, now: str):
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    summary = {s: sum(1 for r in results if r["status"] == s)
               for s in (OK, JUNK, DEAD, SKIP)}
    HEALTH_FILE.write_text(json.dumps(
        {"checked_at": now, "summary": summary, "results": results},
        indent=2), encoding="utf-8")


def _alert_regressions(regressions: list, now: str):
    """Append NEW breakage to the vault action inbox (dashboard + Telegram)."""
    if not regressions or not PENDING_ACTIONS.parent.exists():
        return False
    lines = [f"\n## [{now}] TulsaGays scraper health: {len(regressions)} source(s) newly broken\n"]
    for r in regressions:
        why = r.get("error") or f"{r['raw']} raw rows, 0 with real dates" if r["status"] == JUNK else "0 events / unreachable"
        lines.append(f"- {r['source']} -> {r['status']} ({why}) :: {r.get('url','')}")
    lines.append("- Fix or mark known-dead. Full report: data/scraper_health.json\n")
    with open(PENDING_ACTIONS, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="also run slow aggregators")
    ap.add_argument("--quick", action="store_true", help="multi-site sub-sources only")
    ap.add_argument("--no-alert", action="store_true", help="never write to action inbox")
    ap.add_argument("--json", action="store_true", help="machine-readable summary only")
    args = ap.parse_args()

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    prev = _load_prev()
    results = run(full=args.full, quick=args.quick)

    # Regression = was OK (or unseen but now broken is also worth surfacing once)
    regressions = [r for r in results
                   if r["status"] in (JUNK, DEAD) and prev.get(r["source"]) == OK]
    recovered = [r for r in results
                 if r["status"] == OK and prev.get(r["source"]) in (JUNK, DEAD)]

    _write_health(results, now)
    alerted = False
    if regressions and not args.no_alert:
        alerted = _alert_regressions(regressions, now)

    if args.json:
        print(json.dumps({"checked_at": now,
                          "ok": sum(1 for r in results if r["status"] == OK),
                          "junk": sum(1 for r in results if r["status"] == JUNK),
                          "dead": sum(1 for r in results if r["status"] == DEAD),
                          "regressions": [r["source"] for r in regressions],
                          "recovered": [r["source"] for r in recovered]}, indent=2))
        return

    ok = [r for r in results if r["status"] == OK]
    junk = [r for r in results if r["status"] == JUNK]
    dead = [r for r in results if r["status"] == DEAD]
    print(f"TulsaGays scraper health - {now}")
    print(f"  OK={len(ok)}  JUNK={len(junk)}  DEAD={len(dead)}  (total {len(results)})")
    if junk:
        print("\nJUNK (returns rows but no real dates - the Elote failure mode):")
        for r in junk:
            print(f"  ~ {r['source']:42s} raw={r['raw']}")
    if dead:
        print("\nDEAD (0 events / unreachable):")
        for r in dead:
            print(f"  x {r['source']:42s} {r.get('error','')}")
    if regressions:
        print(f"\n*** {len(regressions)} NEW REGRESSION(S) since last run ***")
        for r in regressions:
            print(f"  ! {r['source']} -> {r['status']}")
        print(f"  Action inbox updated: {alerted}")
    if recovered:
        print(f"\n+++ {len(recovered)} RECOVERED since last run +++")
        for r in recovered:
            print(f"  + {r['source']}")
    print(f"\nReport: {HEALTH_FILE}")


if __name__ == "__main__":
    main()
