"""Final holistic sanity review of the GENERATED deck (William 2026-07-09).

The last set of eyes before a deck is considered ready: after generate-all has
picked, written, and rendered everything, this re-examines the finished
slide_manifest.json the way a human editor would — "are these actually good,
distinct, live events, and did we pick the best ones?"

Two layers:
  1. DETERMINISTIC (always runs, no LLM):
     - no cancelled/postponed event featured or as EOTW (recomputed LIVE
       against current signals, never trusting flags persisted at scrape time)
     - no never-feature/service event featured or as EOTW
     - the featured picks per day are DISTINCT real events (venue+date dup
       check AND name similarity) — and so is the full shown list per day
     - a recurring-source event holding a featured slot while an LGBTQ one-off
       sits unfeatured in the same day's pool -> flagged with the suggested swap
  2. LLM EDITOR (haiku, --no-llm to skip, degrades soft):
     one small call per day: the featured picks + that day's alternates.
     Flags duplicates/cancelled (errors) and recurring-filler/better-pick
     suggestions (warnings, for the Monday review — never auto-swapped).

Verdict policy (never death-spiral the Monday post):
  - deterministic findings and LLM duplicate/cancelled -> ERRORS (exit 1)
  - LLM better-pick / recurring-filler -> WARNINGS (surface in review)
  - LLM unavailable -> warning; the deterministic layer still ran

Report persists to data/posts/{week}/final_review.json — preflight_post.py
reads it (and re-runs the deterministic layer inline), so a deck that never
had its final review, or failed it, cannot post.

Usage:
    python tools/final_deck_review.py [WEEK_KEY] [--no-llm]
    python tools/final_deck_review.py --selftest
Exit 0 = deck clean (warnings allowed). Exit 1 = blocking problems.
"""
import json
import os
import re
import sys
from datetime import datetime

for _stream in ("stdout", "stderr"):
    try:
        getattr(sys, _stream).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_this = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_this)
if _root not in sys.path:
    sys.path.insert(0, _root)

import config  # noqa: E402
from scraper.runner import (  # noqa: E402
    _are_similar,
    _is_cancelled,
    _is_never_feature,
    _same_event_by_venue,
)

_DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
              "Saturday", "Sunday"]

_LLM_SYSTEM = (
    "You are the final human-style editor of a weekly LGBTQ+ events carousel "
    "for Tulsa (@tulsagays). You review one day's FEATURED picks against the "
    "day's unfeatured ALTERNATES and flag only real problems. Be precise and "
    "conservative: a wrong flag wastes the operator's time, a missed duplicate "
    "or cancelled event embarrasses the account."
)


def _is_dup_pair(a: dict, b: dict) -> bool:
    """Two records that are the same real-world event."""
    if _same_event_by_venue(a, b):
        return True
    return (_are_similar(a.get("name", ""), b.get("name", ""))
            and (a.get("date") or "") == (b.get("date") or ""))


def _fmt(e: dict) -> str:
    return (f"{(e.get('name') or '')[:70]} | {e.get('date','')} | "
            f"{(e.get('time') or '')[:30]} | {(e.get('venue') or '')[:50]} | "
            f"{e.get('source','')}")


def _is_recurring(e: dict) -> bool:
    return (e.get("source") or "").lower() == "recurring"


# Weekly drag / performance is still marquee (domain rule: drag is EOTW
# priority #3) — never nag to swap it out for a craft night.
_PERF_KW = ("drag", "talent night", "open talent", "cabaret", "variety",
            "burlesque", "ball", "revue", "showcase")

# Names that read weekly-recurring even when the SOURCE isn't 'recurring'
# (aggregator listings of standing nights) — bad swap SUGGESTIONS.
_WEEKLYISH_KW = ("happy hour", "trivia", "farmers market", "farmer's market",
                 "bingo", "karaoke", "open mic", "game night", "brunch (",
                 "weekly", "every ", "monthly", "free pool", "run club",
                 "book club", "story time", "lunch special", "specials at",
                 "special at", "daily")


def _looks_weeklyish(e: dict) -> bool:
    nm = (e.get("name") or "").lower()
    return any(k in nm for k in _WEEKLYISH_KW)


def _is_perf(e: dict) -> bool:
    combo = ((e.get("name") or "") + " " + (e.get("venue") or "")).lower()
    return any(k in combo for k in _PERF_KW)


def _is_lgbtq(e: dict) -> bool:
    return bool(e.get("lgbtq_relevant")) or (e.get("flamingo") or 0) >= 4


# ── Layer 1: deterministic ────────────────────────────────────────────────────

def deterministic_pass(manifest: dict) -> tuple:
    """Return (errors, warnings) from the rule layer. Pure + fast: preflight
    re-runs this inline on every gate check."""
    errors, warnings = [], []
    eotw = manifest.get("eotw", [])
    featured_by_day = manifest.get("featured_by_day", {})
    all_shown = manifest.get("all_shown", [])

    # 1a. Cancelled / never-feature in the highlight slots, recomputed live.
    for e in eotw:
        if _is_cancelled(e):
            errors.append(f"[final] EOTW is CANCELLED/postponed: '{e.get('name')}'")
        elif e.get("never_feature") or _is_never_feature(e):
            errors.append(f"[final] EOTW is a never-feature/service event: '{e.get('name')}'")
    for day, evs in featured_by_day.items():
        for e in evs:
            if _is_cancelled(e):
                errors.append(f"[final] {day} features a CANCELLED/postponed event: '{e.get('name')}'")
            elif e.get("never_feature") or _is_never_feature(e):
                errors.append(f"[final] {day} features a never-feature/service event: '{e.get('name')}'")

    # 1a.2 PARTNER-SOURCE gate (William 2026-07-27). Yellow Brick Road is a
    # partner we promote; on 2026-07-27 we published YBR nights that weren't
    # happening (a stale hardcoded flyer + a stale IG post projected forward) and
    # YBR called it out. YBR events may ONLY come from their live Instagram
    # (source 'ybr_ig'). A featured YBR event from any other source (recurring
    # assumption, google_events, etc.) is a HARD block — never post a ghost event
    # for a partner. See [[feedback_tulsagays_ybr_ig_only]].
    def _is_ybr(e):
        v = (e.get("venue") or "").lower()
        return ("yellow brick" in v) or ("ybr" in v) or ("2630 e 15th" in v)
    for day, evs in featured_by_day.items():
        for e in evs:
            if _is_ybr(e) and (e.get("source") or "") != "ybr_ig":
                errors.append(
                    f"[final] {day} features a YBR event NOT from YBR's Instagram "
                    f"(source='{e.get('source')}'): '{e.get('name')}'. YBR is a "
                    f"partner — only live @tulsaybr (ybr_ig) events may be featured.")

    # 1b. Featured picks per day must be distinct real events.
    for day, evs in featured_by_day.items():
        for i in range(len(evs)):
            for j in range(i + 1, len(evs)):
                if _is_dup_pair(evs[i], evs[j]):
                    errors.append(
                        f"[final] {day} features the SAME event twice: "
                        f"'{evs[i].get('name')}' / '{evs[j].get('name')}'")

    # 1c. The full shown list per day must be duplicate-free too ("N more
    # events" and the website list both come from it).
    by_date = {}
    for e in all_shown:
        by_date.setdefault(e.get("date") or "?", []).append(e)
    for d, evs in sorted(by_date.items()):
        for i in range(len(evs)):
            for j in range(i + 1, len(evs)):
                if _is_dup_pair(evs[i], evs[j]):
                    errors.append(
                        f"[final] {d} shown list carries a duplicate: "
                        f"'{evs[i].get('name')}' / '{evs[j].get('name')}'")

    # 1d. Prefer one-offs: a recurring-source event holding a featured slot
    # while an LGBTQ one-off sits unfeatured that day is a suspect pick.
    # Warning, not a block — gay-first can legitimately put a recurring LGBTQ
    # event over a non-LGBTQ one-off, so only a same-or-better swap fires.
    for day, evs in featured_by_day.items():
        feat_keys = {(e.get("name"), e.get("date")) for e in evs}
        dates = {e.get("date") for e in evs if e.get("date")}
        pool = [e for e in all_shown
                if e.get("date") in dates
                and (e.get("name"), e.get("date")) not in feat_keys]
        for e in evs:
            # Weekly drag/performance is marquee by domain rule — no nag.
            if not _is_recurring(e) or _is_perf(e):
                continue
            swaps = [c for c in pool
                     if _is_lgbtq(c) and not _is_recurring(c)
                     and not _looks_weeklyish(c)
                     and not (c.get("never_feature") or _is_never_feature(c))
                     and not _is_cancelled(c)
                     and not _is_dup_pair(c, e)]
            if swaps:
                warnings.append(
                    f"[final] {day} features recurring '{e.get('name')}' while "
                    f"one-off LGBTQ candidate(s) sit unfeatured: "
                    + "; ".join(f"'{s.get('name')}'" for s in swaps[:3]))
    return errors, warnings


# ── Layer 2: LLM editor ───────────────────────────────────────────────────────

def _llm_call(prompt: str) -> str:
    try:
        from content.generator import _call_claude_cli
    except Exception as e:
        print(f"[final] LLM unavailable (import: {e})")
        return ""
    try:
        return _call_claude_cli(prompt, _LLM_SYSTEM, model="haiku", timeout=240) or ""
    except TypeError:
        return _call_claude_cli(prompt, _LLM_SYSTEM, model="haiku") or ""


_LLM_ERROR_TYPES = {"duplicate", "cancelled"}
_LLM_TYPES = {"duplicate", "cancelled", "recurring_filler", "better_pick"}


def llm_pass(manifest: dict, max_alternates: int = 10) -> tuple:
    """Return (errors, warnings, day_reports). Empty on LLM failure — the
    caller records that the LLM layer did not run."""
    errors, warnings, day_reports = [], [], {}
    featured_by_day = manifest.get("featured_by_day", {})
    all_shown = manifest.get("all_shown", [])
    for day in _DAY_ORDER:
        evs = featured_by_day.get(day) or []
        if not evs:
            continue
        dates = {e.get("date") for e in evs if e.get("date")}
        feat_keys = {(e.get("name"), e.get("date")) for e in evs}
        alternates = [e for e in all_shown
                      if e.get("date") in dates
                      and (e.get("name"), e.get("date")) not in feat_keys
                      and not (e.get("never_feature") or _is_never_feature(e))
                      and not _is_cancelled(e)][:max_alternates]
        f_lines = [f"F{i} | {_fmt(e)}" for i, e in enumerate(evs)]
        a_lines = [f"A{i} | {_fmt(e)}" for i, e in enumerate(alternates)]
        prompt = (
            f"DAY: {day}\n"
            "FEATURED picks (printed as the day's highlights; format: "
            "slot | name | date | time | venue | source):\n"
            + "\n".join(f_lines)
            + "\n\nALTERNATES from the same day (not featured):\n"
            + ("\n".join(a_lines) if a_lines else "(none)")
            + "\n\nFlag ONLY real problems:\n"
              "- duplicate: two FEATURED slots are the same real-world event "
              "(same venue/date, possibly renamed)\n"
              "- cancelled: a FEATURED entry is cancelled or postponed\n"
              "- recurring_filler: a FEATURED weekly/recurring item while a "
              "clearly better one-off sits in ALTERNATES\n"
              "- better_pick: an ALTERNATE is clearly a stronger highlight "
              "(one-off, LGBTQ+, fun) than a FEATURED pick\n"
              'Return ONLY JSON, no prose: {"issues": [{"slot": "F1", '
              '"type": "duplicate", "why": "<short>", "swap_with": "A2"}]} '
              'or {"issues": []} if the day is good.'
        )
        out = _llm_call(prompt)
        if not out:
            return [], [], {}  # LLM layer down — caller records it
        m = re.search(r"\{.*\}", out, re.S)
        if not m:
            continue
        try:
            verdict = json.loads(m.group(0))
        except ValueError:
            continue
        issues = [i for i in (verdict.get("issues") or [])
                  if isinstance(i, dict) and (i.get("type") in _LLM_TYPES)]
        day_reports[day] = issues
        for i in issues:
            slot = str(i.get("slot") or "?")
            try:
                nm = evs[int(slot.lstrip("Ff"))].get("name")
            except (ValueError, IndexError):
                nm = slot
            swap = ""
            sw = str(i.get("swap_with") or "")
            try:
                swap = f" -> swap with '{alternates[int(sw.lstrip('Aa'))].get('name')}'"
            except (ValueError, IndexError):
                pass
            line = (f"[final-llm] {day} {i.get('type')}: '{nm}' — "
                    f"{(i.get('why') or '')[:160]}{swap}")
            (errors if i.get("type") in _LLM_ERROR_TYPES else warnings).append(line)
    return errors, warnings, day_reports


# ── Orchestration ─────────────────────────────────────────────────────────────

def run_for_week(week_key=None, use_llm=True) -> dict:
    week_key = week_key or config.current_week_key()
    post_dir = os.path.join(config.DATA_DIR, "posts", week_key)
    manifest_path = os.path.join(post_dir, "slide_manifest.json")
    if not os.path.exists(manifest_path):
        report = {"week": week_key, "ok": False,
                  "errors": [f"[final] no slide_manifest.json in {post_dir} — run generate first"],
                  "warnings": [], "llm_ran": False}
        _print_report(report)
        return report

    manifest = json.load(open(manifest_path, encoding="utf-8"))
    errors, warnings = deterministic_pass(manifest)

    llm_ran = False
    day_reports = {}
    if use_llm:
        le, lw, day_reports = llm_pass(manifest)
        llm_ran = bool(day_reports) or bool(le or lw)
        # Dedup: skip LLM findings that restate a deterministic error.
        errors += [x for x in le if not _restates(x, errors)]
        warnings += [x for x in lw if not _restates(x, warnings)]
        if not llm_ran:
            warnings.append("[final] LLM editor layer did not run — deterministic checks only")
    else:
        warnings.append("[final] LLM editor layer skipped (--no-llm)")

    report = {
        "week": week_key,
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "manifest_mtime": os.path.getmtime(manifest_path),
        "llm_ran": llm_ran,
        "errors": errors,
        "warnings": warnings,
        "llm_day_reports": day_reports,
        "ok": not errors,
    }
    with open(os.path.join(post_dir, "final_review.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    _print_report(report)
    return report


def _restates(llm_line: str, existing: list) -> bool:
    """An LLM finding about an event already flagged deterministically."""
    names = re.findall(r"'([^']{4,})'", llm_line)
    return any(n in x for n in names for x in existing)


def _print_report(report: dict):
    print(f"\n=== FINAL DECK REVIEW — {report.get('week')} ===")
    for e in report.get("errors", []):
        print(f"  ERROR   {e}")
    for w in report.get("warnings", []):
        print(f"  warning {w}")
    if report.get("ok"):
        print("[OK] final review clean — deck is good to go"
              + ("" if report.get("llm_ran") else " (rules layer only)"))
    else:
        print(f"[BLOCKED] {len(report['errors'])} problem(s) — fix and regenerate before posting.")


# ── Selftest ──────────────────────────────────────────────────────────────────

def _selftest() -> int:
    fails = []

    def check(name, cond):
        print(f"  [{'ok ' if cond else 'FAIL'}] {name}")
        if not cond:
            fails.append(name)

    elote_a = {"name": "Elote Drag Brunch", "date": "2026-07-11",
               "venue": "Elote Cafe & Catering, 514 S Boston Ave",
               "source": "recurring", "lgbtq_relevant": True}
    elote_b = {"name": "Drag Brunch : jul. 11th - stars, stripes & sequins",
               "date": "2026-07-11", "venue": "Elote Cafe & Catering",
               "source": "community_groups", "lgbtq_relevant": True}
    cancelled = {"name": "(Cancelled) Clothing Swap!", "date": "2026-07-11",
                 "venue": "Equality Center", "source": "okeq"}
    oneoff = {"name": "Pride Pool Party", "date": "2026-07-11",
              "venue": "The Hunt Club", "source": "eventbrite",
              "lgbtq_relevant": True}
    recurring = {"name": "Karaoke Tuesdays", "date": "2026-07-11",
                 "venue": "Tulsa Eagle", "source": "recurring",
                 "lgbtq_relevant": True}

    # The exact W28 Saturday deck must BLOCK.
    bad = {"eotw": [], "featured_by_day": {"Saturday": [elote_a, elote_b, cancelled]},
           "all_shown": [elote_a, elote_b, cancelled]}
    errs, _ = deterministic_pass(bad)
    check("W28 Saturday deck blocks", len(errs) >= 2)
    check("dup detected", any("SAME event twice" in e for e in errs))
    check("cancelled detected", any("CANCELLED" in e for e in errs))

    # A clean day passes.
    good = {"eotw": [oneoff], "featured_by_day": {"Saturday": [oneoff, elote_b]},
            "all_shown": [oneoff, elote_b]}
    errs, warns = deterministic_pass(good)
    check("clean deck passes", not errs)

    # Recurring featured while a one-off sits unfeatured -> warning only.
    sub = {"eotw": [], "featured_by_day": {"Saturday": [recurring]},
           "all_shown": [recurring, oneoff]}
    errs, warns = deterministic_pass(sub)
    check("recurring-over-oneoff is warning not error",
          not errs and any("one-off LGBTQ candidate" in w for w in warns))

    # Cancelled EOTW blocks.
    errs, _ = deterministic_pass({"eotw": [cancelled], "featured_by_day": {}, "all_shown": []})
    check("cancelled EOTW blocks", any("EOTW is CANCELLED" in e for e in errs))

    print(f"\n[{'OK' if not fails else 'X'}] selftest: {5 - len(fails)}/5 passed")
    return 1 if fails else 0


def main(argv):
    if "--selftest" in argv:
        sys.exit(_selftest())
    use_llm = "--no-llm" not in argv
    week = next((a for a in argv[1:] if not a.startswith("--")), None)
    report = run_for_week(week, use_llm=use_llm)
    sys.exit(0 if report.get("ok") else 1)


if __name__ == "__main__":
    main(sys.argv)
