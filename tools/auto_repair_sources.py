#!/usr/bin/env python3
"""Self-repairing scrapers - auto-recover a rendered_sites spec that broke.

When the health guard flags a rendered_sites source JUNK/DEAD, the usual cause
is a DOM change (a venue renamed its event-card class, or switched to JSON-LD).
This tool re-renders the page and re-derives a working extraction by trying, in
order: (1) JSON-LD on the rendered HTML, (2) a library of known-good event-card
selector patterns (the ones proven across our live specs), (3) a generic
"repeating block with a <time> tag" heuristic. If any yields >=1 dated event it
hot-fixes the spec in data/rendered_site_specs.json (after backing it up) and
verifies. If nothing works, it escalates the source to the blocked-on-William
registry (which the guard surfaces on the TODAY dashboard).

Most breakage fixes itself overnight; William only sees the genuinely unfixable.

Usage:
  python tools/auto_repair_sources.py                 # repair specs the guard marked broken
  python tools/auto_repair_sources.py --all-enabled    # re-test every enabled spec, repair any yielding 0
  python tools/auto_repair_sources.py --spec "BOK"     # repair one spec by name substring
  python tools/auto_repair_sources.py --dry-run        # show repairs without writing
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scraper.rendered_sites import RenderedSitesScraper, SPECS_FILE, _load_specs
from scraper.base import BaseScraper

HEALTH_FILE = REPO / "data" / "scraper_health.json"

# Known-good event-card patterns, harvested from the specs that work today.
# Each: (container, title, date, date_attr, date_format). date_attr/None.
SELECTOR_LIBRARY = [
    (".event-card", ".event-card__title", ".event-card__info", None, "auto"),
    ("article.eventlist-event", "h1.eventlist-title", "time.event-date", "datetime", "iso"),
    (".eventlist-event", ".eventlist-title", "time.event-date", "datetime", "iso"),
    (".rhpSingleEvent", "#eventTitle", ".singleEventDate", None, "auto"),
    (".eventItem", "h3.title", ".m-date__singleDate", None, "auto"),
    (".events-item", ".event-card-title", ".event-date", None, "%b %d, %Y"),
    (".event", ".event-title", "time", "datetime", "iso"),
    ("[class*='event-card']", "h2, h3, .title", "time, .date", "datetime", "iso"),
    ("article", "h2, h3", "time", "datetime", "iso"),
    ("li[class*='event']", "h3, h2, a", "time, .date", "datetime", "iso"),
]


def _dated(events):
    return [e for e in events if len(e.get("date", "")) == 10 and e["date"][:4].isdigit()]


def repair_spec(s: RenderedSitesScraper, spec: dict):
    """Return a repaired spec dict (with working strategy/selectors) or None."""
    html = s._render(spec["url"], spec.get("wait_until", "networkidle"),
                     spec.get("wait_ms", 2500))
    if not html:
        return None
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    # 1. JSON-LD (the venue may have added structured data)
    jl = s._extract_json_ld_from_soup(soup, spec["name"], int(spec.get("priority", 2)))
    if _dated(jl):
        out = dict(spec)
        out.update({"strategy": "json_ld", "enabled": True})
        for k in ("container", "title", "date", "date_attr", "date_format"):
            out.pop(k, None)
        return out

    # 2. Known-good selector library
    for container, title, date_sel, date_attr, date_fmt in SELECTOR_LIBRARY:
        trial = dict(spec)
        trial.update({"strategy": "dom", "container": container, "title": title,
                      "date": date_sel, "date_format": date_fmt})
        if date_attr:
            trial["date_attr"] = date_attr
        else:
            trial.pop("date_attr", None)
        got = _dated(s._extract_dom(html, trial))
        if len(got) >= 1:
            trial["enabled"] = True
            return trial

    # 3. Generic heuristic: repeating ancestor of <time datetime> tags
    times = soup.select("time[datetime]")
    if len(times) >= 2:
        # the common parent class of the time tags' grandparent is the card
        for t in times[:1]:
            anc = t.find_parent()
            for _ in range(3):
                if anc is None:
                    break
                cls = anc.get("class")
                if cls:
                    trial = dict(spec)
                    trial.update({"strategy": "dom", "container": "." + ".".join(cls[:1]),
                                  "title": "h1, h2, h3, a", "date": "time", "date_attr": "datetime",
                                  "date_format": "iso", "enabled": True})
                    if _dated(s._extract_dom(html, trial)):
                        return trial
                anc = anc.find_parent()
    return None


def _broken_from_health():
    if not HEALTH_FILE.exists():
        return []
    try:
        data = json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    names = []
    for r in data.get("results", []):
        src = r.get("source", "")
        if src.startswith("rendered_sites/") and r.get("status") in ("JUNK", "DEAD"):
            names.append(src.split("/", 1)[1])
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all-enabled", action="store_true")
    ap.add_argument("--spec", help="repair specs whose name contains this")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    specs = _load_specs()
    by_name = {s["name"]: s for s in specs}

    if args.spec:
        targets = [n for n in by_name if args.spec.lower() in n.lower()]
    elif args.all_enabled:
        targets = [s["name"] for s in specs
                   if s.get("enabled", True) and s.get("strategy") != "dead"]
    else:
        targets = _broken_from_health()
    if not targets:
        print("[auto-repair] no broken rendered_sites specs to repair.")
        return

    s = RenderedSitesScraper()
    repaired, escalated, still_ok = [], [], []
    try:
        for name in targets:
            spec = by_name.get(name)
            if not spec:
                continue
            # Confirm it's actually broken right now (skip ones still working).
            current = _dated(s._scrape_spec(spec)) if spec.get("strategy") != "dead" else []
            if current:
                still_ok.append(name)
                continue
            fixed = repair_spec(s, spec)
            if fixed:
                # Verify the repaired spec yields dated events.
                got = _dated(s._scrape_spec(fixed))
                if got:
                    repaired.append((name, fixed.get("strategy"), len(got)))
                    if not args.dry_run:
                        for i, sp in enumerate(specs):
                            if sp["name"] == name:
                                fixed["note"] = (sp.get("note", "") +
                                                 f" | auto-repaired {datetime.now():%Y-%m-%d}").strip()
                                specs[i] = fixed
                                break
                    continue
            escalated.append(name)
            if not args.dry_run:
                try:
                    from tools import blocked_items
                    blocked_items.add(
                        item=f"Repair TulsaGays scraper source: {name}",
                        reason="auto-repair could not re-derive a working extraction; needs a human look",
                        source=f"rendered_sites/{name}", since=f"{datetime.now():%Y-%m-%d}")
                except Exception:
                    pass
    finally:
        s._close_browser()

    if repaired and not args.dry_run:
        # Backup then write.
        bak = SPECS_FILE.with_suffix(".json.bak")
        try:
            bak.write_text(SPECS_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
        SPECS_FILE.write_text(json.dumps(specs, indent=2), encoding="utf-8")

    print(f"[auto-repair] {'DRY RUN -- ' if args.dry_run else ''}"
          f"repaired {len(repaired)}, escalated {len(escalated)}, still-ok {len(still_ok)}")
    for name, strat, n in repaired:
        print(f"  + REPAIRED {name} -> {strat} ({n} dated events)")
    for name in escalated:
        print(f"  ! ESCALATED {name} -> blocked-on-William (TODAY dashboard)")


if __name__ == "__main__":
    main()
