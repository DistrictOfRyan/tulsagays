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
  3. TRUTH-GATE unconfirmed — a featured/EOTW slot whose event never got a
     positive confirmation from tools/verify_week_truth.py (added 2026-10-18
     after W38-W42 each blocked on a different unconfirmed filler; see the
     inline comment at the truth-gate step below).

(1) and (2) are already *diagnosed* precisely by tools/final_deck_review.py,
which emits llm_day_reports[day] = [{slot, type, why, swap_with}] with
hard-error types {"duplicate","cancelled"}. This tool AUTOMATES the exact
manual repair: read that structured verdict, suppress the offending source
event (never_feature=True in {week}_all.json), re-render with SKIP_ENRICH,
and re-review — looping until the deck is clean or we run out of rounds.
(3) is diagnosed by tools/preflight_post.py reading truth_report.json
directly and is handled the same way: suppress and let the next render pick
a different candidate.

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


def _truth_blockers(week: str, manifest: dict, events: list, final_round: bool) -> list:
    """Featured/EOTW rows to demote, as [(manifest_row, source_row_or_None,
    why_kept_or_None, reason)]: rows preflight's truth gate would block and, in
    the final round, rows a HARD preflight error names. why_kept is set for a
    row this round must leave alone (see step 1c in _apply_fixes)."""
    from tools.truth_status import load as _truth_load, protected_from_demotion
    ts = _truth_load(week)
    if not ts.report_present or not ts.report_has_confirmed:
        # No source re-read ran: preflight blocks that on its own (HARD). Demoting
        # every featured row against an empty confirmed set would gut the deck.
        return []
    fbd = manifest.get("featured_by_day", {})
    eotw = list(manifest.get("eotw", []))
    eotw_keys = {(e.get("name"), e.get("date")) for e in eotw}
    featured = eotw + [e for day in DAYS for e in fbd.get(day, [])]
    feat_keys = {(e.get("name"), e.get("date")) for e in featured}

    # A demotion only helps when something confirmed can take the slot. The
    # picker (main.py) already seats confirmed rows first, so an unconfirmed
    # featured row usually means its day has no confirmed spare, and demoting it
    # would leave the day under 3 featured: a HARD block instead of a SOFT one.
    shown = manifest.get("all_shown", []) or []
    spares: dict = {}
    for r in shown:
        if (r.get("name"), r.get("date")) in feat_keys or r.get("never_feature"):
            continue
        if ts.featurable(_find_source(events, r) or r):
            spares.setdefault(r.get("date"), []).append(r)

    def _eotw_alternative(skip_key) -> bool:
        try:
            from eotw_selector import select_eotw
        except Exception:
            return False
        pool = [r for r in shown if (r.get("name"), r.get("date")) != skip_key
                and ts.featurable(_find_source(events, r) or r)]
        return select_eotw(pool) is not None

    # FINAL ROUND ONLY: a HARD preflight error that names one featured row is a
    # problem with that row's record, and the same demote-and-replace repair
    # applies. W44 replay (2026-10-27): the pre-change deck also carried "[venue]
    # featured/EOTW 'Spotlight Student Art Exhibition | McFarlin Library'
    # CONTRADICTS ITSELF" (copy says McFarlin Library, venue line says University
    # of Tulsa), and no rung of the ladder could clear it. Read from the
    # preflight_status.json the ladder's last preflight wrote; only rows still
    # featured in the current manifest count, so a stale line is harmless.
    hard_named: dict = {}
    if final_round:
        try:
            with open(os.path.join(config.DATA_DIR, "posts", week, "preflight_status.json"),
                      encoding="utf-8") as f:
                _st = json.load(f)
            _hard = _st.get("hard_errors")
            if _hard is None:
                from tools.preflight_post import is_soft_error
                _hard = [x for x in _st.get("errors", []) if not is_soft_error(x)]
            for line in _hard:
                if line.startswith(("[events] manual EOTW", "[overlap]", "[caption]", "[setup]")):
                    continue
                for e in featured:
                    if f"'{e.get('name')}'" in line:
                        hard_named.setdefault((e.get("name"), e.get("date")), line)
        except Exception:
            hard_named = {}

    out, seen = [], set()
    for e in featured:
        k = (e.get("name"), e.get("date"))
        if k in seen:
            continue
        seen.add(k)
        src = _find_source(events, e)
        hard_line = hard_named.get(k)
        if ts.confirmed(src or e) and not hard_line:
            continue
        if final_round:
            why = protected_from_demotion(src or e, week)
        else:
            why = "lgbtq_relevant: needs a real check, not a guess" if (src or {}).get("lgbtq_relevant") is True else None
        if not why:
            if k in eotw_keys:
                if not _eotw_alternative(k):
                    why = "no confirmed Event-of-the-Week candidate to replace it"
            elif spares.get(k[1]):
                spares[k[1]].pop()
            else:
                why = f"no confirmed replacement on {k[1]}: demoting it would leave the day short of 3"
        reason = (f"named in a HARD preflight error: {hard_line[:140]}" if hard_line
                  else "not confirmed by its source or a recorded check")
        out.append((e, src, why, reason))
    return out


def _apply_fixes(week: str, review: dict, dry_run: bool, final_round: bool = False,
                 notes: list | None = None) -> list:
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

    # 1b) Deterministic: the YBR PARTNER-SOURCE rule (added 2026-09-07).
    #
    # final_deck_review.deterministic_pass hard-blocks a featured Yellow Brick
    # Road event whose source is not 'ybr_ig'. Until now this healer could not
    # touch that class at all - it only ever read the LLM's duplicate/cancelled
    # verdicts - so a single stale YBR row dead-ended the ENTIRE Monday post.
    # That is not hypothetical: W31, W32, W33 and W37 all ended as "PREP BLOCKED
    # at preflight after self-repair", and W37's block was one YBR flyer that a
    # manual ledger had projected onto four consecutive Wednesdays.
    #
    # The repair is the rule's own remedy, written down in
    # [[feedback_tulsagays_ybr_ig_only]]: "If the IG scrape has a bad week, YBR
    # simply isn't featured - under-promote a partner rather than post a ghost
    # event." So suppress the offending row and let the day fill from the pool.
    # This never relaxes the gate; it just stops the gate from costing a week.
    def _is_ybr(e):
        v = (e.get("venue") or "").lower()
        return ("yellow brick" in v) or ("ybr" in v) or ("2630 e 15th" in v)

    for day in DAYS:
        for e in fbd.get(day, []):
            if _is_ybr(e) and (e.get("source") or "") != "ybr_ig":
                src = _find_source(events, e)
                if src and (dry_run or _suppress(src)):
                    actions.append(
                        f"{day}: suppressed YBR event from source="
                        f"'{e.get('source')}' '{e.get('name')}' - partner rule: only "
                        f"live @tulsaybr (ybr_ig) events may be featured")

    # 1c) Deterministic: TRUTH-GATE unconfirmed featured/EOTW slots (added
    # 2026-10-18, fixing F-1834/F-0160/F-1819/F-1797).
    #
    # tools/preflight_post.py hard-blocks ANY featured or EOTW slot whose
    # event is not positively confirmed by verify_week_truth.py (present in
    # truth_report.json's "confirmed" list) or a recorded human_verified
    # check, unless it's a tracked recurring event in a fresh/stale ledger
    # tier. This is NOT a gap in verify_week_truth.py's apply_fixes() -- that
    # function deliberately leaves "unverifiable" rows alone, because most of
    # a week's ~77 unverifiable rows are real events a scraper just could not
    # machine-parse a date from, and hiding them from the SITE would be wrong.
    # But a scarce FEATURED/EOTW slot needs positive proof, and five straight
    # weeks (W38-W42) each blocked on a different low-value filler event
    # (non-LGBTQ, thin calendar-index source, e.g. W42's "Under the Influence
    # Film Series" sourced only from the generic UTulsa calendar index) that
    # got promoted into a featured slot and then failed this gate, with
    # nothing auto-correcting it -- a human had to catch it every Monday.
    # The gate's own error message names the remedy: "...verify it ... or
    # unfeature it." So: same pattern as the YBR partner rule above --
    # suppress the offending source event (never_feature=True) so the next
    # render's slot-filler promotes a different, hopefully-confirmed,
    # candidate instead. This never touches hide_from_site / the public
    # listing -- only featuring.
    #
    # SAFETY GATE (added same day, before this ever shipped): checked live
    # against the real stuck W42 data, an unguarded version of this step
    # would have unfeatured 'Tulsa Pride 2026', 'Tulsa Pride x EBA Happy
    # Hour', and 'Escandalo - Tulsa Pride Weekend Dance Competition' --
    # Pride Weekend's own highest-value content, unconfirmed only because
    # their source is a Facebook redirect URL (400) or a club IG manual
    # entry the verifier can't fetch, not because the event is fake. Auto-
    # suppressing on "unconfirmed" alone would silently strip exactly the
    # events most worth featuring. So this only auto-suppresses when the
    # event's own lgbtq_relevant flag is NOT True -- the low-value filler
    # case (student art exhibitions, theatre-season listings, a university
    # president's film series) that caused every W38-W42 block. An
    # lgbtq_relevant event that fails the truth gate is left blocking on
    # purpose: it needs a real human_verified check (open the source, record
    # evidence_url), not a guess.
    #
    # FINAL ROUND (2026-10-27). The lgbtq_relevant exemption above is right for an
    # ordinary round, and it is also why W44 still blocked: its blockers WERE
    # lgbtq_relevant ('Intersex Awareness Day', 'The Sunday Spotlight', 'TAFF
    # 2024'), so this step skipped every one and a person had to step in. The prep
    # degrade ladder therefore calls a last round with final_round=True, which
    # demotes ANY unconfirmed featured row except the ones a person or a deal put
    # there: a data/manual_eotw.json pin, an active featured_partners.json partner,
    # or a _FLAGSHIP_KEYWORDS night (tools/truth_status.protected_from_demotion).
    # Demote means never_feature=True; the row stays on the website.
    # "Confirmed" is tools/truth_status.py, the same definition preflight uses.
    for e, src, why_kept, reason in _truth_blockers(week, manifest, events, final_round):
        if why_kept:
            if notes is not None:
                notes.append(f"truth-gate: kept '{e.get('name')}' {e.get('date')} ({why_kept}); {reason}")
            continue
        if src and (dry_run or _suppress(src)):
            actions.append(
                f"truth-gate{' (final round)' if final_round else ''}: suppressed featured/EOTW "
                f"'{e.get('name')}' {e.get('date')} — {reason}")

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
        dry_run: bool = False, render: bool = True, final_round: bool = False) -> dict:
    """Heal the deck until neither the LLM review nor preflight's truth gate has
    anything left to fix, or max_rounds.

    Returns {week, clean, rounds, actions, remaining_errors, truth_blockers, notes}."""
    week = week or config.current_week_key()
    all_actions: list = []
    notes: list = []
    rounds = 0
    clean = False
    remaining: list = []
    truth_left: list = []

    for rounds in range(1, max_rounds + 1):
        # ONE LLM review per round = the diagnosis. The next round's review is
        # what verifies the re-rendered deck, so we never double-spend the LLM.
        review = run_for_week(week, use_llm=True)
        remaining = review.get("errors", []) or []
        # The truth blockers are computed EVERY round, independent of the LLM
        # (2026-10-27). Until now the truth step ran only inside _apply_fixes,
        # and _apply_fixes ran only when the LLM review reported an error: W44's
        # review came back errors: [] and the healer quit "clean" over six
        # featured rows preflight was about to block.
        try:
            _c, _ev = _load_events(week)
            truth_left = [f"'{e.get('name')}' {e.get('date')}"
                          for e, _s, _w, _r in _truth_blockers(week, _load_manifest(week), _ev, final_round)]
        except Exception as _tbx:
            truth_left = []
            notes.append(f"[r{rounds}] truth blockers not computed: {_tbx}")
        if not remaining and not truth_left:
            clean = True
            break

        actions = _apply_fixes(week, review, dry_run, final_round=final_round, notes=notes)
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
        "truth_blockers": truth_left,
        "notes": sorted(set(notes)),
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

    # Truth blockers (2026-10-27): W44's blockers were lgbtq_relevant, so an
    # ordinary round keeps them and only the final round demotes; and nothing is
    # demoted when the day has no confirmed row to take its slot.
    import tempfile
    import tools.truth_status as _ts_mod
    _orig_load = _ts_mod.load
    _orig_data = config.DATA_DIR
    try:
        config.DATA_DIR = tempfile.mkdtemp(prefix="afd_selftest_")   # never read the real week's status
        _ts_mod.load = lambda wk=None: _ts_mod.TruthStatus(
            "2026-W44", {("Conf A", "2026-11-01"), ("Conf B", "2026-11-01"),
                         ("Conf Spare", "2026-10-27"), ("Conf Mon", "2026-10-26"),
                         ("Conf Mon2", "2026-10-26")},
            {}, True, True, ledger=None)
        sun = [{"name": "Conf A", "date": "2026-11-01"}, {"name": "Conf B", "date": "2026-11-01"},
               {"name": "The Sunday Spotlight", "date": "2026-11-01"}]
        tue = [{"name": "TAFF 2024", "date": "2026-10-27"}, {"name": "x2", "date": "2026-10-27"},
               {"name": "x3", "date": "2026-10-27"}]
        man = {"eotw": [], "featured_by_day": {"Sunday": sun, "Tuesday": tue},
               "all_shown": sun + tue + [{"name": "Conf Spare", "date": "2026-10-27"}]}
        evs = [dict(r, lgbtq_relevant=True) for r in man["all_shown"]]
        normal = {e["name"]: w for e, _s, w, _r in _truth_blockers("2026-W44", man, evs, False)}
        final = {e["name"]: w for e, _s, w, _r in _truth_blockers("2026-W44", man, evs, True)}
        assert normal["TAFF 2024"] and "lgbtq_relevant" in normal["TAFF 2024"], normal
        assert final["TAFF 2024"] is None, f"final round demotes the lgbtq filler: {final}"
        assert final["x2"] and "short of 3" in final["x2"], "only one confirmed spare on Tuesday"
        assert final["The Sunday Spotlight"] and "short of 3" in final["The Sunday Spotlight"], final
        assert "Conf A" not in final, "confirmed rows are never blockers"

        # A HARD error naming one CONFIRMED featured row (the W44 replay's
        # "[venue] ... CONTRADICTS ITSELF") is demoted in the final round only,
        # and only because a confirmed spare exists that day.
        mon = [{"name": "Conf Mon", "date": "2026-10-26"}, {"name": "Conf Mon2", "date": "2026-10-26"},
               {"name": "Conf A", "date": "2026-11-01"}]
        man2 = {"eotw": [], "featured_by_day": {"Monday": mon[:2]},
                "all_shown": mon[:2] + [{"name": "Conf Spare", "date": "2026-10-26"}]}
        _ts_mod.load = lambda wk=None: _ts_mod.TruthStatus(
            "2026-W44", {("Conf Mon", "2026-10-26"), ("Conf Mon2", "2026-10-26"),
                         ("Conf Spare", "2026-10-26")}, {}, True, True, ledger=None)
        os.makedirs(os.path.join(config.DATA_DIR, "posts", "2026-W44"), exist_ok=True)
        with open(os.path.join(config.DATA_DIR, "posts", "2026-W44", "preflight_status.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"hard_errors": ["[venue] featured/EOTW 'Conf Mon2' CONTRADICTS ITSELF: copy vs venue"],
                       "soft_errors": []}, f)
        n2 = _truth_blockers("2026-W44", man2, man2["all_shown"], False)
        f2 = {e["name"]: (w, r) for e, _s, w, r in _truth_blockers("2026-W44", man2, man2["all_shown"], True)}
        assert not n2, "an ordinary round leaves confirmed rows alone"
        assert "Conf Mon2" in f2 and f2["Conf Mon2"][0] is None and "HARD" in f2["Conf Mon2"][1], f2
        assert "Conf Mon" not in f2, "only the row the HARD error names"
    finally:
        _ts_mod.load = _orig_load
        config.DATA_DIR = _orig_data
    print("selftest OK")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", default=None)
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--final-round", action="store_true",
                    help="degrade-ladder round: demote unconfirmed featured rows even when "
                         "lgbtq_relevant, unless pinned / partner / flagship")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(_selftest())
    res = run(week=args.week, max_rounds=args.max_rounds,
              dry_run=args.dry_run, render=not args.no_render,
              final_round=args.final_round)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    # exit 0 = clean, 1 = still blocked (so callers/gates can branch)
    sys.exit(0 if res["clean"] else 1)


if __name__ == "__main__":
    main()
