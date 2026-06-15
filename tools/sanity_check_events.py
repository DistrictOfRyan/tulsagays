"""
Event sanity checker — runs AFTER scrape, BEFORE descriptions/slides/website.

Born from the 2026-W24 embarrassments William called out:
  - "Owasso city council / chamber breakfast" class events on a gay events site
  - a soda-bottle collectors convention apparently at 10 PM (end-time parsing bug,
    but implausible times must also be CAUGHT, not just not-created)
  - truncated Google Events names ("2026 June Small Business Workshop ...")
  - "Information and Tickets" scraper-artifact cards

Two passes over data/events/<week>_all.json:

  1. RULES (always): re-applies the runner's junk-name / spam / off-topic
     filters to whatever is in the file (catches manual additions, Wednesday
     last-minute injects, and any scraper that bypassed the runner), plus
     local checks: truncated/garbled names, missing venue/time, implausible
     start hour for the event type.
  2. LLM (default on, --no-llm to skip): one `claude -p` call over the kept
     events asking for drop/flag verdicts on anything that makes no sense on
     a Tulsa LGBTQ+/community events guide. Fail-open: if the CLI/API is
     unavailable the rules verdicts still apply.

DROPPED events are moved to data/events/<week>_quarantine.json (never deleted
outright, so a wrong drop is recoverable). FLAGGED events stay but carry a
`sanity_flags` list that preflight_post.py surfaces before the Monday post.
A machine-readable report lands at data/events/<week>_sanity_report.json.

Idempotent. Usage:
    python tools/sanity_check_events.py [WEEK_KEY] [--no-llm] [--dry-run]
Exit 0 = ran (report written). Exit 1 = could not run (missing file etc.).
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402

# Reuse the runner's filter logic so the two never drift apart.
from scraper.runner import (  # noqa: E402
    _is_junk_name,
    _is_spam_noise,
    _is_offtopic_noise,
    _is_lgbtq_relevant,
    _clean_time_text,
    _parse_time_token,
    _TIME_TOKEN_RX,
)
from eotw_selector import _is_youth_nongay  # noqa: E402  under-18 non-gay screen


# ── Rules: garbled / truncated names ─────────────────────────────────────────

_MOJIBAKE_MARKERS = ("�", "Ã©", "Ã¨")
# 'â' followed by a non-letter is the classic UTF-8-as-latin1 signature
# ("â€™", "â¥", "â¢", ...). No real Tulsa event name contains it.
_MOJIBAKE_RX = re.compile(r"â[^a-zA-Z\s]|â\s")


def _name_problems(name: str) -> list:
    problems = []
    if name.rstrip().endswith(("...", "…")):
        problems.append("truncated name (ends with ellipsis — Google Events cut it off)")
    if any(m in name for m in _MOJIBAKE_MARKERS) or _MOJIBAKE_RX.search(name):
        problems.append("garbled characters in name (mojibake)")
    return problems


# ── Rules: implausible start time for the event type ─────────────────────────
# (keywords, earliest_ok_hour, latest_ok_START_hour) — 24h clock.
_TIME_PLAUSIBILITY = (
    (("storytime", "story time", "toddler", "babies", "kids "), 8, 18),
    (("breakfast",), 6, 11),
    (("brunch",), 8, 15),
    (("farmers market", "farmer's market"), 7, 18),
    (("painting", "pottery", "craft", "crochet", "knit", "fiber arts",
      "book club", "workshop", "collectors"), 7, 21),
    (("yoga", "meditation", "sound bath"), 5, 21),
    (("city council", "council meeting", "commission"), 7, 19),
)


def _start_hour(time_str: str):
    """Best-effort start hour from a (possibly already normalized) time string."""
    if not time_str:
        return None
    cleaned = _clean_time_text(time_str)
    parts = re.split(r"\s*(?:-|\bto\b)\s*", cleaned, maxsplit=1, flags=re.IGNORECASE)
    start_s = parts[0].strip()
    end_hint = None
    if len(parts) == 2:
        em = _TIME_TOKEN_RX.match(parts[1].strip())
        if em and em.group(3):
            end_hint = em.group(3).upper()
    hm = _parse_time_token(start_s, meridiem_hint=end_hint)
    return hm[0] if hm else None


def _time_problems(ev: dict) -> list:
    problems = []
    tstr = (ev.get("time") or "").strip()
    if not tstr:
        return problems
    hour = _start_hour(tstr)
    if hour is None:
        # Unparseable strings like "Doors 9 PM, Show 10 PM" are fine; flag only
        # strings that contain digits but yield nothing usable.
        if not re.search(r"\d", tstr):
            problems.append(f"non-time time field: '{tstr}'")
        return problems
    text = (ev.get("name") or "").lower() + " " + (ev.get("description") or "")[:120].lower()
    for kws, lo, hi in _TIME_PLAUSIBILITY:
        if any(k in text for k in kws):
            if not (lo <= hour <= hi):
                problems.append(
                    f"implausible start time {tstr} for a "
                    f"'{kws[0]}'-type event (expected {lo:02d}:00-{hi:02d}:00)")
            break
    return problems


# ── Rules pass ───────────────────────────────────────────────────────────────

def rules_pass(events: list) -> tuple:
    """Return (kept, dropped, n_flagged). Mutates kept events' sanity_flags."""
    kept, dropped = [], []
    n_flagged = 0
    for ev in events:
        name = (ev.get("name") or "").strip()
        # Hard drops — same logic the runner applies at scrape time, re-applied
        # here so manual/late additions and stale files get the same standard.
        if _is_junk_name(name):
            dropped.append((ev, "junk/navigation name"))
            continue
        # Under-18 programming that isn't explicitly LGBTQ — removed from the guide
        # (e.g. a pet-rock class / storytime at the library). Queer youth events are
        # protected by the LGBTQ check inside _is_youth_nongay. (William 2026-06-15)
        if _is_youth_nongay(ev):
            dropped.append((ev, "youth/under-18 programming (not LGBTQ)"))
            continue
        if not _is_lgbtq_relevant(ev):
            if _is_spam_noise(ev):
                dropped.append((ev, "spam (career/investor/MLM noise)"))
                continue
            offtopic, reason = _is_offtopic_noise(ev)
            if offtopic:
                dropped.append((ev, f"off-topic: {reason}"))
                continue
        # Soft flags
        flags = _name_problems(name) + _time_problems(ev)
        if not (ev.get("venue") or "").strip():
            flags.append("missing venue")
        if flags:
            ev["sanity_flags"] = sorted(set((ev.get("sanity_flags") or []) + flags))
            n_flagged += 1
        else:
            ev.pop("sanity_flags", None)
        kept.append(ev)
    return kept, dropped, n_flagged


# ── LLM pass ─────────────────────────────────────────────────────────────────

_LLM_SYSTEM = (
    "You are the sanity checker for TulsaGays.com, a weekly LGBTQ+ and community "
    "events guide for Tulsa, Oklahoma. You receive this week's scraped event list "
    "and return verdicts. The guide intentionally lists ALL fun Tulsa community, "
    "arts, music, food, market, and cultural events (not only explicitly LGBTQ ones), "
    "so KEEP those. DROP only events that make no sense on a community events guide: "
    "government/city-council/school-board meetings, chamber-of-commerce and business "
    "networking, children-only programming, pro/minor-league sports games, paid "
    "professional training/certification courses, private trade conventions not open "
    "to casual attendees, and obvious non-events (bare 'presale'/'tickets' artifacts). "
    "IMPORTANT: an EMPTY time, venue, or date field is NOT evidence an event is fake — "
    "scrapers often miss fields. Never drop a real-sounding event for missing fields; "
    "FLAG it at most. Anything LGBTQ+ (drag, Pride, queer performance, gay icons like "
    "a David Sedaris reading) is always KEEP. FLAG (keep, but warn) events whose time "
    "of day is implausible for what they are, whose names look truncated or garbled, "
    "or that look like duplicates of another listed event."
)


# Verified sizing (2026-06-12): the nested `claude -p` CLI hangs on ~20KB
# sonnet prompts (the W23/W24 enrichment timeouts) but handles the same list on
# haiku in ~2 min, and sonnet is fine at <5KB. Use haiku over chunks of <=150.
_LLM_CHUNK = 150


def _llm_call(prompt: str) -> str:
    try:
        from content.generator import _call_claude_cli
    except Exception as e:
        print(f"[sanity] LLM unavailable (import: {e})")
        return ""
    try:
        out = _call_claude_cli(prompt, _LLM_SYSTEM, model="haiku", timeout=240)
    except TypeError:  # older generator signature without timeout param
        out = _call_claude_cli(prompt, _LLM_SYSTEM, model="haiku")
    if not out and getattr(config, "ANTHROPIC_API_KEY", ""):
        # CLI flaky/nested — same fallback chain the enrichment uses.
        try:
            from anthropic import Anthropic
            msg = Anthropic(api_key=config.ANTHROPIC_API_KEY).messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=4000,
                system=_LLM_SYSTEM,
                messages=[{"role": "user", "content": prompt}])
            out = msg.content[0].text.strip()
            print("[sanity] LLM verdicts via Anthropic API fallback")
        except Exception as e:
            print(f"[sanity] API fallback failed: {e}")
            out = ""
    return out


def llm_pass(events: list) -> dict:
    """Return {idx: ("drop"|"flag", reason)} or {} when the LLM is unavailable."""
    result = {}
    for chunk_start in range(0, len(events), _LLM_CHUNK):
        chunk = events[chunk_start:chunk_start + _LLM_CHUNK]
        lines = []
        for j, ev in enumerate(chunk):
            lines.append(
                f"{chunk_start + j} | {ev.get('name','')[:80]} | {ev.get('date','')} | "
                f"{ev.get('time','')} | {(ev.get('venue') or '')[:60]} | {ev.get('source','')}")
        prompt = (
            "Events (index | name | date | time | venue | source):\n"
            + "\n".join(lines)
            + "\n\nReturn ONLY a JSON array, no prose, no code fences. One object per "
              "event that needs action (omit keeps): "
              '[{"i": <index>, "v": "drop" or "flag", "why": "<short reason>"}]'
        )
        out = _llm_call(prompt)
        if not out:
            print(f"[sanity] LLM returned nothing for chunk @{chunk_start} — rules-only there")
            continue
        m = re.search(r"\[.*\]", out, re.S)
        if not m:
            print(f"[sanity] LLM chunk @{chunk_start} had no JSON array — skipped")
            continue
        try:
            verdicts = json.loads(m.group(0))
        except ValueError:
            print(f"[sanity] LLM chunk @{chunk_start} JSON unparseable — skipped")
            continue
        for v in verdicts:
            try:
                i = int(v.get("i"))
                verdict = (v.get("v") or "").strip().lower()
                if verdict in ("drop", "flag") and 0 <= i < len(events):
                    result[i] = (verdict, (v.get("why") or "no reason given")[:200])
            except (TypeError, ValueError):
                continue
    return result


def _llm_drop_protected(ev: dict) -> bool:
    """Events William curated by hand, from trusted LGBTQ sources, or annotated
    lgbtq_relevant must never be auto-dropped by an LLM verdict (in testing it
    voted to drop the manually-added Laura Bellis Pride celebration AND
    'PRIDE at Elote'/'Miss Gay Oklahoma America' over empty venue fields).
    Downgrade those to flags."""
    if ev.get("lgbtq_relevant"):
        return True
    src = (ev.get("source") or "").lower()
    if src in ("manual", "submission", "homo_hotel"):
        return True
    return src in getattr(config, "LGBTQ_SOURCES", set())


# ── Main ─────────────────────────────────────────────────────────────────────

def sanitize(events: list, week_key: str, use_llm=True, dry_run=False) -> tuple:
    """Run both passes over an in-memory event list. Returns (kept, report).
    Writes the quarantine + report files (unless dry_run) but does NOT touch
    the events JSON — the caller owns persistence. This lets the scraper
    sanitize BEFORE save_results() so the _all/_weekday/_weekend splits are
    all written clean."""
    n_before = len(events)

    kept, dropped, n_flagged = rules_pass(events)

    llm_dropped = 0
    llm_ran = False
    if use_llm and kept:
        verdicts = llm_pass(kept)
        llm_ran = bool(verdicts)
        if verdicts:
            new_kept = []
            for i, ev in enumerate(kept):
                verdict = verdicts.get(i)
                if verdict and verdict[0] == "drop":
                    if _llm_drop_protected(ev):
                        ev["sanity_flags"] = sorted(set(
                            (ev.get("sanity_flags") or [])
                            + [f"LLM wanted to drop (protected source): {verdict[1]}"]))
                        new_kept.append(ev)
                        continue
                    dropped.append((ev, f"LLM: {verdict[1]}"))
                    llm_dropped += 1
                    continue
                if verdict and verdict[0] == "flag":
                    ev["sanity_flags"] = sorted(set(
                        (ev.get("sanity_flags") or []) + [f"LLM: {verdict[1]}"]))
                new_kept.append(ev)
            kept = new_kept
            n_flagged = sum(1 for e in kept if e.get("sanity_flags"))

    report = {
        "week": week_key,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "events_before": n_before,
        "events_after": len(kept),
        "dropped": [
            {"name": e.get("name"), "date": e.get("date"), "venue": e.get("venue"),
             "source": e.get("source"), "reason": r} for e, r in dropped],
        "flagged": [
            {"name": e.get("name"), "date": e.get("date"),
             "flags": e.get("sanity_flags")} for e in kept if e.get("sanity_flags")],
        "llm_used": llm_ran,
        "llm_dropped": llm_dropped,
        "dry_run": dry_run,
    }

    print(f"[sanity] {week_key}: {n_before} -> {len(kept)} events "
          f"({len(dropped)} quarantined, {n_flagged} flagged"
          f"{', LLM on' if use_llm else ', rules only'})")
    for e, r in dropped:
        print(f"  DROP [{r}] {(e.get('name') or '')[:70]}")
    for e in kept:
        for f in e.get("sanity_flags") or []:
            print(f"  FLAG {(e.get('name') or '')[:50]}: {f}")

    if dry_run:
        print("[sanity] dry-run: nothing written")
        return kept, {**report, "ok": True}

    # Quarantine file (append-merge so reruns don't lose earlier drops)
    events_dir = Path(config.DATA_DIR) / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    qpath = events_dir / f"{week_key}_quarantine.json"
    quarantine = []
    if qpath.exists():
        try:
            quarantine = json.loads(qpath.read_text(encoding="utf-8"))
        except ValueError:
            quarantine = []
    seen = {(q.get("name"), q.get("date")) for q in quarantine if isinstance(q, dict)}
    for e, r in dropped:
        if (e.get("name"), e.get("date")) not in seen:
            quarantine.append({**e, "quarantine_reason": r,
                               "quarantined_at": report["checked_at"]})
    qpath.write_text(json.dumps(quarantine, ensure_ascii=False, indent=2),
                     encoding="utf-8")

    rpath = events_dir / f"{week_key}_sanity_report.json"
    rpath.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    print(f"[sanity] wrote {qpath.name}, {rpath.name}")
    return kept, {**report, "ok": True}


def run_for_week(week_key=None, use_llm=True, dry_run=False) -> dict:
    """File-based entry point: sanitize data/events/<week>_all.json in place.
    (The weekday/weekend split files are regenerated from _all by the scraper;
    when run standalone, this rewrites _all only — rerun the splits if needed.)"""
    week_key = week_key or config.current_week_key()
    path = Path(config.DATA_DIR) / "events" / f"{week_key}_all.json"
    if not path.exists():
        print(f"[sanity] no events file: {path}")
        return {"ok": False, "error": f"missing {path}"}
    data = json.loads(path.read_text(encoding="utf-8"))
    wrapper_is_dict = isinstance(data, dict)
    events = data.get("events", []) if wrapper_is_dict else data

    kept, report = sanitize(events, week_key, use_llm=use_llm, dry_run=dry_run)

    if not dry_run:
        if wrapper_is_dict:
            data["events"] = kept
            data["total_events"] = len(kept)
        else:
            data = kept
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        print(f"[sanity] rewrote {path.name}")
    return report


def main(argv):
    week = None
    use_llm, dry = True, False
    for a in argv:
        if a == "--no-llm":
            use_llm = False
        elif a == "--dry-run":
            dry = True
        elif not a.startswith("-"):
            week = a
    res = run_for_week(week, use_llm=use_llm, dry_run=dry)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
