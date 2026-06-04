"""Coverage report: how much of Tulsa's known queer universe does the scraper see?

Turns "every gay group in Tulsa represented" from a vibe into a number. Reads
tulsa_queer_org_census.json (the known universe) and checks each org two ways:

  SOURCE  -- represented as a live scraper source (FB page/group, partner
             keyword, config SOURCE, or census alias appears in those lists)
  EVENTS  -- actually produced >=1 event in the recent scrape window

An org is COVERED if either is true. The GAP list (known orgs with neither) is
the weekly discovery target -- search for those by name first.

Writes data/coverage_report.json and prints a scorecard. `--selftest` proves
the matching logic on synthetic data.
"""

import os
import sys
import json
import glob
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper import dynamic_sources as dyn

CENSUS_FILE = os.path.join(config.PROJECT_DIR, "tulsa_queer_org_census.json")
REPORT_FILE = os.path.join(config.DATA_DIR, "coverage_report.json")


def _load_census():
    data = json.load(open(CENSUS_FILE, encoding="utf-8"))
    return data.get("orgs", [])


def _live_source_blob():
    """One big lowercased string of every live source identifier."""
    parts = []
    # config SOURCES
    for s in getattr(config, "SOURCES", {}).values():
        parts.append((s.get("name", "") + " " + s.get("url", "")).lower())
    # partner keywords + venue sets
    parts += [k.lower() for k in getattr(config, "COMMUNITY_PARTNER_KEYWORDS", [])]
    for vs in ("TRUE_GAY_BAR_VENUES", "QUEER_FRIENDLY_VENUES"):
        parts += [k.lower() for k in getattr(config, vs, set())]
    # dynamic sources
    parts += [u.lower() for u in dyn.fb_page_urls()]
    parts += [u.lower() for u in dyn.fb_group_urls()]
    parts += [c[0].lower() for c in dyn.calendar_sites()]
    parts += [k.lower() for k in dyn.partner_keywords()]
    # hardcoded FB page/group lists
    try:
        from scraper import facebook_events as fbe
        parts += [u.lower() for u in getattr(fbe, "PAGE_URLS", [])]
        parts += [u.lower() for u in getattr(fbe, "GROUP_URLS", [])]
    except Exception:
        pass
    return " || ".join(parts)


def _recent_event_blob(weeks=6):
    files = sorted(glob.glob(os.path.join(config.EVENTS_DIR, "*_all.json")),
                   key=os.path.getmtime)[-weeks:]
    chunks = []
    for f in files:
        try:
            data = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        events = data.get("events", []) if isinstance(data, dict) else data
        for e in events:
            if isinstance(e, dict):
                chunks.append((e.get("name", "") + " " + e.get("venue", "") + " " +
                               e.get("url", "") + " " + e.get("description", "")).lower())
    return " || ".join(chunks)


def compute(census, source_blob, event_blob):
    covered, gaps = [], []
    for org in census:
        aliases = [a.lower() for a in org.get("aliases", []) if a]
        in_source = any(a in source_blob for a in aliases)
        in_events = any(a in event_blob for a in aliases)
        rec = {"id": org["id"], "name": org["name"], "type": org.get("type", ""),
               "as_source": in_source, "has_recent_events": in_events,
               "note": org.get("note", "")}
        (covered if (in_source or in_events) else gaps).append(rec)
    total = len(census)
    pct = round(100 * len(covered) / total, 1) if total else 0.0
    return {"total": total, "covered": len(covered), "gaps": len(gaps),
            "coverage_pct": pct, "covered_list": covered, "gap_list": gaps}


def run():
    census = _load_census()
    report = compute(census, _live_source_blob(), _recent_event_blob())
    json.dump(report, open(REPORT_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"=== TulsaGays coverage: {report['covered']}/{report['total']} "
          f"({report['coverage_pct']}%) of the known queer universe ===")
    if report["gap_list"]:
        print(f"\n{len(report['gap_list'])} GAP(S) -> discovery targets this week:")
        for g in report["gap_list"]:
            print(f"  - {g['name']} ({g['type']}) -- {g['note']}")
    else:
        print("\nNo gaps: every known org is represented. Time to expand the census.")
    return report


def _selftest():
    census = [
        {"id": "a", "name": "Covered By Source", "aliases": ["alpha club"]},
        {"id": "b", "name": "Covered By Events", "aliases": ["beta night"]},
        {"id": "c", "name": "Real Gap", "aliases": ["gamma collective"]},
    ]
    source_blob = "facebook.com/alphaclub || alpha club"
    event_blob = "beta night at some venue || other stuff"
    r = compute(census, source_blob, event_blob)
    assert r["total"] == 3, r
    assert r["covered"] == 2, r
    assert r["gaps"] == 1, r
    assert r["coverage_pct"] == 66.7, r
    gap_names = [g["name"] for g in r["gap_list"]]
    assert gap_names == ["Real Gap"], gap_names
    # real census file must load + parse
    real = _load_census()
    assert len(real) >= 20, f"census too small: {len(real)}"
    assert any("fellowship" in (a.lower()) for o in real for a in o.get("aliases", [])), \
        "Fellowship Congregational (William's craft-club ask) missing from census"
    print(f"coverage_report selftest: assertions passed (synthetic 2/3=66.7%, "
          f"real census {len(real)} orgs, Fellowship present)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(_selftest())
    run()
