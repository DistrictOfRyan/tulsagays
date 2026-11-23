"""Replay the Event of the Week picker over past weeks.

    python tools/eotw_replay.py --from 2026-W33 --to 2026-W48          # table
    python tools/eotw_replay.py --check --from 2026-W33 --to 2026-W48  # exit 1 on a repeat
    python tools/eotw_replay.py --week 2026-W48 --json                 # one week, JSON

Each week's candidates are that week's listings (data/events/<wk>_all.json,
rows dated inside the Mon-Sun window). Each replayed week sees the picks the
replay itself made for the earlier weeks in the range (so a repeat the new
picker would cause is caught), and the shipped heroes from slide_manifest.json
for weeks before the range. Manual pins (data/manual_eotw.json) and the
confirmed-row preference work exactly as in production.

--check fails on any AUTO pick (not HHHH, not a manual pin) that is:
  * DRAGNIFICENT (William 2026-11-23: the weekly show should not be the hero),
  * the same series as a hero in the previous 12 weeks, or
  * at the same building as a non-HHHH hero in the previous 3 weeks.

Built 2026-11-23 after 15 of 17 weeks (W31-W47) put an Equality Center event
in the hero slot. Approximate: main.py also dedups each day before picking,
which this replay skips, so a pick here can differ from the deck in name only.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import eotw_selector as S  # noqa: E402

DATA = os.path.join(ROOT, "data")


def _week_rows(wk):
    rows = S._load_json(os.path.join(DATA, "events", f"{wk}_all.json"))
    if isinstance(rows, dict):
        rows = rows.get("events") or []
    return [e for e in (rows or []) if isinstance(e, dict) and S._in_week(e, wk)]


def _shipped(wk):
    m = S._load_json(os.path.join(DATA, "posts", wk, "slide_manifest.json")) or {}
    return [e for e in (m.get("eotw") or []) if isinstance(e, dict)]


def _confirmed_for(wk):
    # Production only prefers confirmed rows since the truth system (W38); weeks
    # before it have no truth_report.json and were picked over every row.
    if not os.path.exists(os.path.join(DATA, "posts", wk, "truth_report.json")):
        return None
    try:
        from tools.truth_status import load
        return load(wk).featurable
    except Exception:
        return None


def _weeks(start, end):
    out, wk = [], start
    while True:
        out.append(wk)
        if wk == end or len(out) > 200:
            return out
        wk = S._shift_week(wk, 1)


def _slim(e, fresh=None, pinned=False):
    d = {"name": e.get("name"), "venue": e.get("venue"), "date": e.get("date"),
         "source": e.get("source"), "pinned": pinned, "hhhh": S._is_hh(e)}
    if fresh is not None:
        d.update(S.explain(e, fresh))
    return d


MAX_VENUE_SHARE = 0.25


def replay(weeks, chain=True):
    sim = {}      # week -> new picks (events)
    report = {}
    violations = []
    auto_venues = []
    for wk in weeks:
        rows = _week_rows(wk)
        fresh = S.Freshness.for_week(wk, history_override=sim if chain else None)
        pins = S.load_manual_eotw(wk)
        picks = S.select_eotw_list(rows, week_key=wk, confirmed=_confirmed_for(wk), fresh=fresh)
        sim[wk] = picks
        new = [_slim(p, fresh, pinned=bool(pins)) for p in picks]
        report[wk] = {"candidates": len(rows),
                      "old": [_slim(e) for e in _shipped(wk)],
                      "new": new}
        # Violations, judged against the history this week actually saw.
        hist = []
        for k in range(1, S.SERIES_COOLDOWN_WEEKS + 1):
            pw = S._shift_week(wk, -k)
            heroes = sim.get(pw) if (chain and pw in sim) else _shipped(pw)
            hist += [(k, h) for h in (heroes or [])]
        for p, slim in zip(picks, new):
            if slim["pinned"] or slim["hhhh"] or S._is_council(p) or S._is_landmark(p):
                continue
            name = p.get("name") or ""
            auto_venues.append((wk, S._series_key(p)[2]))
            if "dragnificent" in name.lower():
                violations.append(f"{wk}: DRAGNIFICENT auto-picked ({name})")
            key = S._series_key(p)
            for k, h in hist:
                if S._same_series(key, S._series_key(h)):
                    violations.append(f"{wk}: '{name}' repeats series of '{h.get('name')}' ({k} wk ago)")
                    break
            vk = key[2]
            for k, h in hist:
                if k == 1 and vk and not (S._is_hh(h) or S._is_landmark(h)) and S._series_key(h)[2] == vk:
                    violations.append(f"{wk}: '{name}' at {vk}, the hero venue last week ('{h.get('name')}')")
                    break
    # No building may dominate: William's complaint was the Equality Center in
    # 15 of 17 hero slots. Over the range, no venue may hold more than
    # MAX_VENUE_SHARE of the weeks (auto picks only; pins, HHHH, landmarks out).
    weeks_with = {}
    for wk, vk in auto_venues:
        if vk:
            weeks_with.setdefault(vk, set()).add(wk)
    cap = max(1, int(MAX_VENUE_SHARE * len(weeks)))
    for vk, wks in sorted(weeks_with.items()):
        if len(wks) > cap:
            violations.append(f"{vk} holds an auto hero in {len(wks)} of {len(weeks)} weeks (cap {cap})")
    return report, violations, weeks_with


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    ap.add_argument("--week")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.week:
        weeks, chain = [a.week], False
    elif a.start and a.end:
        weeks, chain = _weeks(a.start, a.end), True
    else:
        ap.error("give --week WK or --from WK --to WK")
    report, violations, weeks_with = replay(weeks, chain=chain)
    old_eqc = sum(1 for r in report.values()
                  if any(S._venue_key(o.get("venue") or "") == "equality-center" for o in r["old"]))
    new_eqc = sum(1 for r in report.values()
                  if any(S._venue_key(n.get("venue") or "") == "equality-center" for n in r["new"]))
    summary = {"weeks": len(report), "equality_center_weeks_old": old_eqc,
               "equality_center_weeks_new": new_eqc,
               "auto_hero_weeks_by_venue": {k: len(v) for k, v in weeks_with.items()}}
    if a.json:
        print(json.dumps({"weeks": report, "violations": violations, "summary": summary},
                         ensure_ascii=False, indent=1))
    else:
        for wk, r in report.items():
            print(f"{wk}  ({r['candidates']} listings)")
            print("   was: " + (" || ".join(f"{o['name']} @ {o['venue']}" for o in r["old"]) or "-"))
            for n in r["new"]:
                tag = "PIN " if n["pinned"] else ""
                print(f"   now: {tag}{n['name']} @ {n['venue']} ({n['date']})"
                      f"  [tier {n.get('tier')}, {n.get('reason', '')}]")
            if not r["new"]:
                print("   now: -")
        print()
        print(f"Equality Center in the hero slot: {old_eqc} of {len(report)} weeks shipped, "
              f"{new_eqc} of {len(report)} replayed")
        print(f"{len(violations)} violation(s)")
        for v in violations:
            print("  - " + v)
    if a.check and violations:
        sys.exit(1)


if __name__ == "__main__":
    main()
