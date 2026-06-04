"""Extra discovery angles for the source-growth engine (Rung 3: multi-modal).

Beyond the venue miner and the generic SEARCH_SEEDS, this adds two independent,
verifiable discovery inputs:

  1. gap_targets()         -- turn coverage_report.json GAPS (known orgs the
     scraper can't see) into precise, named search queries. Gap-driven beats
     blind: instead of "tulsa queer group," search "Loud & Queer Fest Tulsa
     2026 facebook." The weekly web pass runs these FIRST.
  2. ingest_community_tips() -- a path for human-submitted leads. Drop a tip
     into data/community_tips.json and it becomes a candidate for review.
     This is how a reader/board-member tip enters the pipeline.

Future angles (need live auth, not built here): FB related-pages graph off
trusted pages, Instagram, Eventbrite/Meetup org APIs. Scaffolded conceptually;
those harvesters attach to the same registry.add_candidate sink when added.

`--selftest` proves both without network or touching real candidate data.
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from self_improve import source_registry as registry

COVERAGE_FILE = os.path.join(config.DATA_DIR, "coverage_report.json")
TIPS_FILE = os.path.join(config.DATA_DIR, "community_tips.json")


# ── 1. gap-driven query targeting ────────────────────────────────────────────
def gap_targets(report=None):
    """Return targeted search queries for every current coverage gap.

    Reads data/coverage_report.json (written by coverage_report.py). Each gap
    org yields 2 precise queries: a Facebook-scoped one and a generic events
    one, seeded with the org's real name.
    """
    if report is None:
        if not os.path.exists(COVERAGE_FILE):
            return []
        report = json.load(open(COVERAGE_FILE, encoding="utf-8"))
    queries = []
    for g in report.get("gap_list", []):
        name = g["name"].split(" / ")[0].split("(")[0].strip()
        queries.append(f"{name} Tulsa facebook events")
        queries.append(f"{name} Tulsa 2026 calendar OR meetup OR instagram")
    return queries


# ── 2. community tip intake ──────────────────────────────────────────────────
def _tip_type(tip):
    url = (tip.get("url") or "").lower()
    if "facebook.com/groups" in url:
        return "fb_group", tip.get("url"), ""
    if "facebook.com" in url:
        return "fb_page", tip.get("url"), ""
    if url.startswith("http"):
        return "calendar", tip.get("url"), ""
    return "org_keyword", "", tip.get("name", "")


def ingest_community_tips(path=TIPS_FILE, base_conf=55):
    """Convert data/community_tips.json entries into review-queued candidates.

    Tips are unverified human leads, so they enter at modest confidence (queued
    for William, never auto-promoted). Schema per tip:
        {"name": "...", "url": "https://...", "note": "who/what", "submitted_by": "..."}
    Returns dict of outcome counts.
    """
    if not os.path.exists(path):
        return {"added": 0, "known": 0, "exists": 0, "total": 0}
    try:
        tips = json.load(open(path, encoding="utf-8"))
    except Exception:
        return {"added": 0, "known": 0, "exists": 0, "total": 0, "error": "unreadable"}
    tips = tips.get("tips", tips) if isinstance(tips, dict) else tips

    counts = {"added": 0, "known": 0, "exists": 0, "total": 0}
    for tip in tips:
        if not isinstance(tip, dict) or not (tip.get("name") or tip.get("url")):
            continue
        counts["total"] += 1
        ctype, url, kw = _tip_type(tip)
        res = registry.add_candidate(
            ctype=ctype,
            name=tip.get("name", url or kw),
            url=url, kw=kw,
            confidence=base_conf,
            evidence=f"Community tip: {tip.get('note', 'no note')}"
                     + (f" (via {tip['submitted_by']})" if tip.get("submitted_by") else ""),
            discovered_via="community-tip",
        )
        counts[res] = counts.get(res, 0) + 1
    return counts


def _selftest():
    # gap_targets from a synthetic report
    report = {"gap_list": [
        {"name": "Loud & Queer Fest", "type": "event", "note": ""},
        {"name": "Community Hope UCC", "type": "church", "note": ""},
    ]}
    q = gap_targets(report)
    assert len(q) == 4, q
    assert any("Loud & Queer Fest Tulsa facebook" in x for x in q), q
    assert any("Community Hope UCC" in x for x in q), q

    # tip typing
    assert _tip_type({"url": "https://www.facebook.com/groups/123"})[0] == "fb_group"
    assert _tip_type({"url": "https://www.facebook.com/SomePage"})[0] == "fb_page"
    assert _tip_type({"url": "https://example.org/events"})[0] == "calendar"
    assert _tip_type({"name": "Some Org"})[0] == "org_keyword"
    print(f"discovery_inputs selftest: passed ({len(q)} gap queries, tip-typing ok)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--tips", action="store_true", help="ingest community tips now")
    ap.add_argument("--gaps", action="store_true", help="print gap-target queries")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(_selftest())
    if args.gaps:
        for q in gap_targets():
            print(q)
    if args.tips:
        print(ingest_community_tips())
    if not (args.gaps or args.tips):
        print("gap targets:", len(gap_targets()), "| run with --gaps or --tips")
