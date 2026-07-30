"""
tools/auto_fix_deck.py — deterministic self-healer for the weekly deck.

Why this exists
---------------
The Monday prep (task-runner tulsagays_weekly_prep) hits a HARD preflight gate.
When the gate blocks on a *content* problem the old "self-repair" only ran
tools/dedupe_descriptions.py — which fixes duplicate *text*, not the two
failure modes that actually recur:

  1. DUPLICATE  — the same real-world event featured twice on a day (e.g. the
     recurring "Gaymer Night at YBR" template colliding with a scraped
     "Mario Kart Gaymer Night" — same bar, same night). Caught 2026-07-27 (W31),
     blocked the post; nothing actionable reached William.
  2. CANCELLED / corrupt — a featured entry that is cancelled/postponed OR
     carries an impossible time (the "The Dink … Pickleball" @ 3:00 AM garbage,
     also W31).

Both are already *diagnosed* precisely by tools/final_deck_review.py, which
emits llm_day_reports[day] = [{slot, type, why, swap_with}] with hard-error
types {"duplicate","cancelled"}. This tool AUTOMATES the exact manual repair:
read that structured verdict, suppress the offending source event
(never_feature=True in {week}_all.json), re-render with SKIP_ENRICH, and
re-review — looping until the deck is clean or we run out of rounds.

It is deterministic and idempotent: suppressing a never_feature event twice is
a no-op, and generate-all reads the events file fresh each render so a
never_feature flag reliably drops the event from the next lineup.

Usage
-----
  python tools/auto_fix_deck.py                 # this week: heal, re-render, loop
  python tools/auto_fix_deck.py --week 2026-W31
  python tools/auto_fix_deck.py --dry-run       # report what it WOULD suppress, no writes/render
  python tools/auto_fix_deck.py --max-rounds 3
  python tools/auto_fix_deck.py --no-render     # apply suppressions, skip the re-render
  python tools/auto_fix_deck.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

# Reuse the review's own judgement helpers so we never drift from the gate.
from tools.final_deck_review import (  # noqa: E402
    run_for_week,
    _is_dup_pair,
    _is_recurring,
)

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ── event-file helpers ────────────────────────────────────────────────────────

def _events_path(week: str) -> str:
    return os.path.join(config.EVENTS_DIR, f"{week}_all.json")


def _load_events(week: str):
    """Return (container, events_list). container is the raw JSON object so we
    can write it back preserving the dict/list shape."""
    p = _events_path(week)
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    events = data.get("events", data) if isinstance(data, dict) else data
    return data, events


def _save_events(week: str, container) -> None:
    p = _events_path(week)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(container, f, ensure_ascii=False, indent=2)


def _manifest_path(week: str) -> str:
    return os.path.join(config.DATA_DIR, "posts", week, "slide_manifest.json")


def _load_manifest(week: str) -> dict:
    with open(_manifest_path(week), "r", encoding="utf-8") as f:
        return json.load(f)


def _key(e: dict) -> tuple:
    """Identity for matching a featured event back to its source record."""
    return ((e.get("name") or "").strip().lower(),
            (e.get("date") or "").strip(),
            (e.get("venue") or "").strip().lower())


def _find_source(events: list, target: dict):
    """Locate the {week}_all.json record matching a featured event."""
    tk = _key(target)
    for e in events:
        if _key(e) == tk:
            return e
    # looser fallback: name+date only
    for e in events:
        if ((e.get("name") or "").strip().lower() == tk[0]
                and (e.get("date") or "").strip() == tk[1]):
            return e
    return None


# ── impossible-time detector (fast deterministic pre-pass) ────────────────────

def _impossible_time(t: str) -> bool:
    """A featured event at 12:00-6:59 AM is almost always corrupt or an
    end-time mis-parse (real nightlife lists as PM). The LLM classes these as
    'cancelled'; we catch them without waiting for a round-trip."""
    t = (t or "").strip().upper()
    m = re.match(r"^(\d{1,2}):(\d{2})\s*AM$", t)
    if not m:
        return False
    h = int(m.group(1))
    return h == 12 or h <= 6


# ── the healer ────────────────────────────────────────────────────────────────

def _suppress(ev: dict) -> bool:
    if ev.get("never_feature") is True:
        return False
    ev["never_feature"] = True
    return True


def _pick_keeper(group: list) -> dict:
    """Given a set of duplicate featured events, choose the one to KEEP.
    Prefer: a real (scraped) source over 'recurring', a real URL, then the more
    specific (longer) name. This mirrors the manual W31 fix (kept the scraped
    'Mario Kart Gaymer Night', dropped the recurring 'Gaymer Night at YBR')."""
    def score(e):
        return (
            0 if _is_recurring(e) else 1,        # non-recurring wins
            1 if (e.get("url") or "").strip() else 0,
            len((e.get("name") or "")),
        )
    return max(group, key=score)


def _apply_fixes(week: str, review: dict, dry_run: bool) -> list:
    """Apply suppress/dedup fixes for a *single already-computed* review.
    Returns a list of human-readable actions. One review == one LLM call; the
    caller owns the review lifecycle so we never double-spend the LLM."""
    actions: list = []
    container, events = _load_events(week)
    manifest = _load_manifest(week)
    fbd = manifest.get("featured_by_day", {})

    # 1) Deterministic: impossible/corrupt times in any featured slot.
    for day in DAYS:
        for e in fbd.get(day, []):
            if _impossible_time(e.get("time")):
                src = _find_source(events, e)
                if src and (dry_run or _suppress(src)):
                    actions.append(f"{day}: suppressed corrupt-time '{e.get('name')}' "
                                   f"(time={e.get('time')!r})")

    # 2) LLM verdict: duplicate / cancelled per day (the authoritative gate).
    day_reports = review.get("llm_day_reports", {}) or {}

    for day in DAYS:
        issues = day_reports.get(day, []) or []
        featured = fbd.get(day, [])
        for iss in issues:
            typ = (iss.get("type") or "").lower()
            slot = str(iss.get("slot") or "")
            m = re.match(r"[Ff](\d+)", slot)
            if not m:
                continue
            idx = int(m.group(1))
            if idx >= len(featured):
                continue
            flagged = featured[idx]

            if typ == "cancelled":
                src = _find_source(events, flagged)
                if src and (dry_run or _suppress(src)):
                    actions.append(f"{day}: suppressed cancelled/corrupt "
                                   f"'{flagged.get('name')}' — {iss.get('why','')[:80]}")

            elif typ == "duplicate":
                # Build the duplicate group: the flagged slot + any other
                # featured event that day the review would call the same event.
                group = [flagged] + [
                    other for j, other in enumerate(featured)
                    if j != idx and _is_dup_pair(flagged, other)
                ]
                if len(group) < 2:
                    # review flagged a dup but we can't see the sibling in the
                    # featured list — fall back to suppressing the flagged one.
                    group = [flagged]
                    keeper = None
                else:
                    keeper = _pick_keeper(group)
                for e in group:
                    if keeper is not None and _key(e) == _key(keeper):
                        continue
                    src = _find_source(events, e)
                    if src and (dry_run or _suppress(src)):
                        actions.append(f"{day}: deduped '{e.get('name')}' "
                                       f"(kept '{keeper.get('name') if keeper else '?'}')")
                # keeper inherits a time if it lacks one (the LLM's note:
                # "F0 missing a time suggests it inherits F1's 7:00 PM").
                if keeper is not None and not (keeper.get("time") or "").strip():
                    donor = next((e.get("time") for e in group
                                  if (e.get("time") or "").strip()), "")
                    if donor:
                        ks = _find_source(events, keeper)
                        if ks and not dry_run:
                            ks["time"] = donor
                        actions.append(f"{day}: '{keeper.get('name')}' inherits time {donor}")

    if actions and not dry_run:
        _save_events(week, container)
    return actions


def _render(week: str) -> tuple:
    env = dict(os.environ)
    env["TULSAGAYS_SKIP_ENRICH"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "main.py", "generate-all"],
                       cwd=repo, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=3000, env=env)
    return r.returncode, ((r.stdout or "") + (r.stderr or ""))[-800:]


def run(week: str | None = None, max_rounds: int = 3,
        dry_run: bool = False, render: bool = True) -> dict:
    """Heal the deck until the LLM review reports no hard errors, or max_rounds.

    Returns {week, clean, rounds, actions, remaining_errors}."""
    week = week or config.current_week_key()
    all_actions: list = []
    rounds = 0
    clean = False
    remaining: list = []

    for rounds in range(1, max_rounds + 1):
        # ONE LLM review per round = the diagnosis. The next round's review is
        # what verifies the re-rendered deck, so we never double-spend the LLM.
        review = run_for_week(week, use_llm=True)
        remaining = review.get("errors", []) or []
        if not remaining:
            clean = True
            break

        actions = _apply_fixes(week, review, dry_run)
        all_actions.extend(f"[r{rounds}] {a}" for a in actions)
        if not actions:
            # gate still fails but we found nothing to suppress — stop, escalate.
            break
        if dry_run or not render:
            break
        rc, tail = _render(week)
        if rc != 0:
            all_actions.append(f"[r{rounds}] RE-RENDER FAILED rc={rc}: {tail[-200:]}")
            break

    return {
        "week": week,
        "clean": clean,
        "rounds": rounds,
        "actions": all_actions,
        "remaining_errors": remaining,
    }


def _selftest() -> int:
    assert _impossible_time("3:00 AM") is True
    assert _impossible_time("12:30 AM") is True
    assert _impossible_time("7:00 PM") is False
    assert _impossible_time("9:00 AM") is False
    assert _impossible_time("") is False
    a = {"name": "Mario Kart Gaymer Night", "source": "ybr_ig",
         "url": "http://x", "venue": "YBR", "date": "2026-07-27"}
    b = {"name": "Gaymer Night at YBR", "source": "recurring",
         "url": "", "venue": "YBR", "date": "2026-07-27"}
    keeper = _pick_keeper([a, b])
    assert keeper is a, "keeper should be the scraped, url-bearing record"
    print("selftest OK")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", default=None)
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(_selftest())
    res = run(week=args.week, max_rounds=args.max_rounds,
              dry_run=args.dry_run, render=not args.no_render)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    # exit 0 = clean, 1 = still blocked (so callers/gates can branch)
    sys.exit(0 if res["clean"] else 1)


if __name__ == "__main__":
    main()
