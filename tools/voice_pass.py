"""
tools/voice_pass.py — automatic featured/EOTW LLM voice pass.

The weekly pipeline generates slides with FAST rule-based copy (so it can never
hang past the post window). This tool is the automatic version of the old manual
"Step 2.1": right after generate-all picks the featured lineup, it LLM-rewrites
ONLY the events that actually appear on the slides (featured + EOTW, ~20 events)
into the RuPaul x Alicia x Dolly voice, writes them back to {week}_all.json, then
re-renders the deck with TULSAGAYS_SKIP_ENRICH=1 so the copy survives.

Why only the shown events: enriching all ~200 scraped events took ~1 hour and
stalled the Monday post, which is why the LLM was disabled entirely. The featured
set fits the wall-clock budget, so the slides get bespoke copy reliably and the
long-tail website events keep their rule-based floor.

Usage:
  python tools/voice_pass.py                 # this week: enrich featured+EOTW, re-render
  python tools/voice_pass.py --week 2026-W28
  python tools/voice_pass.py --dry-run       # show which events would be rewritten, no LLM/render
  python tools/voice_pass.py --no-render     # enrich + write JSON, skip the re-render
  python tools/voice_pass.py --budget 180    # cap LLM wall-clock seconds (default 240)
  python tools/voice_pass.py --selftest
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def _key(ev: dict) -> tuple:
    return (_norm(ev.get("name")), (ev.get("date") or "").strip())


def _shown_from_manifest(manifest: dict) -> tuple[list[dict], set]:
    """Return (featured_event_stubs, eotw_keys) — the events that actually appear
    on the SLIDES (the pink 'top pick' boxes) plus the EOTW. Deliberately NOT
    `all_shown` (that's every website event, ~200, which blows the budget). The
    long-tail website events keep their rule-based floor."""
    shown, seen = [], set()

    def _add(e):
        if isinstance(e, dict):
            k = _key(e)
            if k not in seen:
                seen.add(k)
                shown.append(e)

    for _day, evs in (manifest.get("featured_by_day") or {}).items():
        for e in (evs or []):
            _add(e)
    eotw = manifest.get("eotw")
    eotw_list = eotw if isinstance(eotw, list) else ([eotw] if eotw else [])
    eotw_keys = {_key(e) for e in eotw_list if isinstance(e, dict)}
    for e in eotw_list:
        _add(e)
    return shown, eotw_keys


def run_voice_pass(week: str = None, budget_s: int = 240,
                   dry_run: bool = False, render: bool = True) -> dict:
    from content import generator as g

    week = week or config.current_week_key()
    post_dir = os.path.join(config.DATA_DIR, "posts", week)
    manifest_path = os.path.join(post_dir, "slide_manifest.json")
    events_path = os.path.join(config.EVENTS_DIR, f"{week}_all.json")

    if not os.path.exists(manifest_path):
        return {"ok": False, "reason": f"no manifest at {manifest_path} (run generate-all first)"}
    if not os.path.exists(events_path):
        return {"ok": False, "reason": f"no events file at {events_path}"}

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    with open(events_path, encoding="utf-8") as f:
        raw = json.load(f)
    all_events = raw.get("events", raw) if isinstance(raw, dict) else raw

    shown_stubs, eotw_keys = _shown_from_manifest(manifest)
    shown_keys = {_key(e) for e in shown_stubs}

    # Resolve the shown stubs to the REAL objects in _all.json (mutate those).
    # FUZZY on purpose: the same event often exists under two records (a scrape
    # name + a recurring/renamed dupe, e.g. "DRAGNIFICENT! Drag Show" vs
    # "DRAGNIFICENT! at Club Majestic"). The render/preflight may resolve the
    # featured slide to EITHER record, so we must voice ALL near-duplicates or a
    # featured slide can still ship un-voiced and hard-block preflight.
    import re as _re

    def _loose(nm: str, dt: str) -> tuple:
        # alphanumeric-only first 12 chars: catches dedup dupes whose names diverge
        # after a shared head ("DRAGNIFICENT! Drag Show" vs "DRAGNIFICENT! at Club
        # Majestic" both -> "dragnificent") without over-matching short generic names.
        return (dt, _re.sub(r"[^a-z0-9]", "", nm)[:12])
    shown_loose = {_loose(nm, dt) for (nm, dt) in shown_keys}
    eotw_loose = {_loose(nm, dt) for (nm, dt) in eotw_keys}
    targets, seen_ids, matched_keys = [], set(), set()
    for ev in all_events:
        nm, dt = _key(ev)
        exact = (nm, dt) in shown_keys
        loose = _loose(nm, dt) in shown_loose
        if exact or loose:
            if id(ev) not in seen_ids:
                seen_ids.add(id(ev))
                if (nm, dt) in eotw_keys or _loose(nm, dt) in eotw_loose:
                    ev["is_eotw"] = True
                targets.append(ev)
            matched_keys.add((nm, dt))
    missing = [k for k in shown_keys if k not in matched_keys
               and _loose(*k) not in {_loose(*mk) for mk in matched_keys}]

    result = {"ok": True, "week": week, "shown": len(shown_keys),
              "matched": len(targets), "missing": len(missing),
              "targets": [t.get("name") for t in targets]}

    if dry_run:
        result["dry_run"] = True
        return result

    if not targets:
        result["ok"] = False
        result["reason"] = "no shown events resolved into the events file"
        return result

    stats = g.voice_enrich(targets, budget_s=budget_s)
    result["enrich"] = stats

    # HEAL DUPLICATES: the same event often exists as a recurring twin + a scraped
    # twin (DRAGNIFICENT). voice_enrich may LLM one and rule-fallback the other, and
    # the render can feature the templated twin over its voiced sibling. Within each
    # loose-key group, propagate the best (LLM, non-templated) copy to every twin so
    # whichever one the render features is voiced.
    try:
        from tools.preflight_post import _looks_templated as _tpl
    except Exception:
        _tpl = lambda _t: False
    groups = {}
    for ev in targets:
        groups.setdefault(_loose(*_key(ev)), []).append(ev)
    healed = 0
    for grp in groups.values():
        if len(grp) < 2:
            continue
        best = next((e for e in grp
                     if e.get("voice_source") == "llm" and not _tpl(e.get("description"))), None)
        if not best:
            continue
        for e in grp:
            if e is best:
                continue
            if _tpl(e.get("description")) or e.get("voice_source") != "llm":
                e["description"] = best.get("description", "")
                e["website_description"] = best.get("website_description", "")
                e["voice_passed"] = True
                e["voice_source"] = "llm"
                healed += 1
    result["healed_duplicates"] = healed

    # Persist (targets are references into all_events, so dump the whole list).
    with open(events_path, "w", encoding="utf-8") as f:
        if isinstance(raw, dict):
            raw["events"] = all_events
            json.dump(raw, f, ensure_ascii=False, indent=2)
        else:
            json.dump(all_events, f, ensure_ascii=False, indent=2)

    if render:
        env = os.environ.copy()
        env["TULSAGAYS_SKIP_ENRICH"] = "1"
        proj = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        r = subprocess.run([sys.executable, "main.py", "generate-all"],
                           cwd=proj, env=env, capture_output=True, text=True, timeout=900)
        result["render_rc"] = r.returncode
        if r.returncode != 0:
            result["ok"] = False
            result["render_tail"] = (r.stdout or r.stderr or "")[-500:]
    return result


def _selftest() -> int:
    """Prove matching + ranking without any network call."""
    from content import generator as g
    evs = [
        {"name": "Drag Brunch", "date": "2026-07-11", "venue": "Elote",
         "lgbtq_relevant": True},
        {"name": "Farmers Market", "date": "2026-07-11", "venue": "Kendall",
         "source": "recurring"},
        {"name": "Council Oak Chorale", "date": "2026-07-12", "is_eotw": True},
    ]
    ranks = [g._featured_rank(e) for e in evs]
    assert ranks[2] == 0, "EOTW must rank first"
    assert ranks[0] < ranks[1], "queer one-off must outrank recurring market"
    man = {"featured_by_day": {"Saturday": [{"name": "Drag Brunch", "date": "2026-07-11"}]},
           "eotw": {"name": "Council Oak Chorale", "date": "2026-07-12"}}
    shown, eotw_keys = _shown_from_manifest(man)
    assert (_norm("Council Oak Chorale"), "2026-07-12") in eotw_keys
    assert len(shown) == 2, shown
    # a featured event repeated across days is only voiced once (dedup by key)
    man2 = {"featured_by_day": {"Sat": [{"name": "Drag Brunch", "date": "2026-07-11"}],
                                "Sun": [{"name": "Drag Brunch", "date": "2026-07-11"}]}}
    shown2, _ = _shown_from_manifest(man2)
    assert len(shown2) == 1, shown2
    print("voice_pass selftest OK — ranking + manifest resolution pass")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week")
    ap.add_argument("--budget", type=int, default=240)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(_selftest())
    res = run_voice_pass(week=a.week, budget_s=a.budget,
                         dry_run=a.dry_run, render=not a.no_render)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
