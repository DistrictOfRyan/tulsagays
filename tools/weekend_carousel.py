#!/usr/bin/env python3
"""
weekend_carousel.py — build the "This Weekend" CAROUSEL (replaces the old
single-image + 3-bullet text post).

Why this exists (William, 2026-07-31): the weekend post was "kind of lame" —
one reused background image, three or four events, and most of them the same
weekly bar nights every single week. It read like a rerun, not a tip sheet.

Three fixes are baked in here:

1. CAROUSEL, not one static asset. Cover + a slide per day, rendered with the
   same content/image_maker engine as Monday's deck, so the weekend post looks
   like part of the brand instead of a leftover.

2. FRIDAY NIGHT IS IN THE WINDOW. The post goes out Friday 8am and used to skip
   Friday entirely — throwing away the single biggest night out of the week.
   Window is now Friday evening (>= FRIDAY_CUTOFF_HOUR) + Saturday + Sunday.

3. NOVELTY RANKING. Every candidate is scored against the last N weeks of
   scraped data. An event that ran the last four weekends is a WEEKLY, not
   news: it is demoted out of the headline slots and folded into a compact
   "always on" line. One-offs, first-appearances, drag/performance, ticketed
   and special-themed nights rise to the top. If a weekend genuinely has no
   one-offs, that is a SUPPLY problem (venue dig / flyer read), and this module
   says so out loud rather than dressing up reruns as a lineup.

CLI:
    python tools/weekend_carousel.py --dry-run     # print the selection, render nothing
    python tools/weekend_carousel.py               # render slides + caption
    python tools/weekend_carousel.py --selftest    # prove scoring + window + dedupe
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402

# --------------------------------------------------------------------------
# Tunables
# --------------------------------------------------------------------------

# Friday events starting at or after this hour count as "this weekend".
# A 10am Friday coffee meetup is not a weekend plan; a 7pm show is.
FRIDAY_CUTOFF_HOUR = 16

# How many prior weeks of scraped data to mine for the "is this a weekly?" test.
HISTORY_WEEKS = 6

# Appearing in this many of the last HISTORY_WEEKS weekends ⇒ treated as weekly.
WEEKLY_THRESHOLD = 3

# Max headline events rendered per day slide (image_maker caps day slides at 4).
MAX_PER_DAY = 4

# A weekend with fewer than this many genuinely-new events is flagged thin.
MIN_FRESH_TARGET = 4

_DAY_LABEL = {4: "FRIDAY", 5: "SATURDAY", 6: "SUNDAY"}

# Name fragments that mark a genuinely special/one-off occasion even when the
# host night is a regular fixture (a themed edition IS news).
_SPECIAL_SIGNALS = (
    "release party", "ep release", "album release", "premiere", "opening night",
    "opening reception", "anniversary", "birthday", "farewell", "finale",
    "debut", "one night", "one-night", "benefit", "fundraiser", "showcase",
    "festival", "pride", "pageant", "competition", "tournament", "market",
    "swap", "pop-up", "popup", "workshop", "screening", "book launch",
    "guest", "featuring", "live at", "tribute", "themed", "edition",
)

# High-draw queer formats. These earn a boost so a thin week still leads queer.
_QUEER_DRAW = (
    "drag", "queer", "lgbt", "gay", "lesbian", "trans", "nonbinary", "non-binary",
    "pride", "cabaret", "burlesque", "ball", "kiki", "bear", "dyke", "sapphic",
)

# Never headline these on a weekend hype post (services, support, admin).
_NEVER_HEADLINE = (
    "support group", "aa meeting", "al-anon", "narcotics anonymous",
    "therapy", "counseling", "clinic", "testing", "legal aid", "fair housing",
    "name change", "gender marker", "fafsa", "board meeting", "committee",
    "monthly meeting", "business meeting", "orientation", "rehearsal",
    "bowling league", "sunday service", "worship", "mass ",
)

# Venue strings the scrapers sometimes leave as junk (relative-date leakage).
_VENUE_JUNK_RE = re.compile(
    r"^(in \d+ days?|in a day|tomorrow|today|tbd|tba|mar|mié|obtener entradas|tickets)$",
    re.I,
)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _norm(text: str) -> str:
    """Normalize an event name for cross-week identity matching."""
    t = (text or "").lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    # Drop dates/ordinals/months that make the same weekly look different
    # week to week ("Drag Brunch : jul. 11th" vs "Drag Brunch : aug. 1st").
    t = re.sub(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b", " ", t)
    t = re.sub(r"\b\d{1,4}(st|nd|rd|th)?\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # Leading articles vary between sources for the SAME night
    # ("Sunday Showdown" vs "The Sunday Showdown!"). Strip them or the
    # cross-week match silently fails and a weekly reads as brand new.
    t = re.sub(r"^(the|a|an)\s+", "", t)
    return t


def _name_key(e: Dict) -> str:
    """Identity key for 'same event, different week'.

    NAME ONLY, deliberately. Venue strings are unstable across scrapes
    ("Club Majestic" vs "Club Majestic, 124 N Boston Ave"), and folding an
    unstable field into the key is what made a six-week-running open talent
    night score as a first appearance.
    """
    return _norm(e.get("name"))


def _clean_venue(raw: str) -> str:
    v = (raw or "").strip()
    if not v or _VENUE_JUNK_RE.match(v):
        return ""
    return v


# Time repair and copy scrubbing live in ONE place (content/textclean.py) so
# the carousel, the website generator and the slide renderer cannot drift.
from content import textclean as _tc  # noqa: E402
from content.textclean import clean_time, scrub_copy  # noqa: E402


# Marks of raw, un-voiced scraper text: run-on concatenation from stripped
# HTML ("withBemis Center"), press-release openings, links, org boilerplate.
_RAW_COPY_RE = re.compile(r"[a-z][A-Z]")


def clean_pitch(e: Dict) -> str:
    """Return a usable one-line pitch, or "" rather than shipping raw junk.

    The weekend post has no voice pass of its own, so anything that still
    looks like scraped press copy is dropped. A missing line reads fine; a
    truncated press release with mashed-together words does not.
    """
    text = (e.get("description") or "").strip()
    if not text:
        return ""
    text = text.split("\n")[0].strip()
    if len(text) < 25:
        return ""
    if "http" in text.lower():
        return ""
    if len(_RAW_COPY_RE.findall(text)) >= 2:
        return ""
    if re.match(r"^(join|register|tickets|presented by|meets the)\b", text, re.I):
        return ""
    # Sanitize BEFORE truncating. Truncation can chop the tail off a junk
    # fragment and hide it from the pattern: "... one. in 6 days ago" cut at
    # 150 chars became "... one. in 6..." which no longer matched "in N days".
    text = sanitize_pitch(text)
    if not text:
        return ""
    if len(text) > 150:
        text = text[:147].rsplit(" ", 1)[0] + "..."
    return text


def sanitize_pitch(text: str) -> str:
    """Final gate on ANY copy that reaches a slide or caption.

    Whatever produced it (scraper, rule bank, LLM), a pitch must never carry a
    URL, a tracking parameter, a relative-date fragment, or an unbreakable
    token long enough to overflow the slide. W31 shipped a raw ?fbclid= URL
    that ran off both edges of the Sunday slide. Returns "" on any violation,
    which renders as no pitch line, which is always better than debris.
    """
    raw = (text or "").strip()
    if not raw:
        return ""
    # DETECT on the original using the shared patterns, then DROP. The website
    # scrubs an artifact out and keeps the sentence, because a card has room to
    # carry a slightly shortened line. A slide does not: a sentence with its
    # verb phrase surgically removed reads worse than no sentence at all, and
    # there is no way to recover a mangled link mid-render. Same patterns, one
    # source of truth, deliberately different verdicts.
    low = raw.lower()
    if _tc.URL_RE.search(raw) or "fbclid" in low or ".com/" in low:
        return ""
    if _tc.REL_DATE_PHRASE_RE.search(raw) or _tc.REL_DATE_BARE_RE.search(raw):
        return ""
    # A single token this long cannot wrap and will overflow the slide.
    if any(len(tok) > 30 for tok in raw.split()):
        return ""
    # Clean copy: still run the shared tidy for dashes and whitespace.
    return scrub_copy(raw)


def _fallback_pitch(e: Dict) -> str:
    """Site-voice line for an event whose scraped copy was unusable.

    Reuses the repo's own rule-based voice bank so the weekend post never
    ships bare or press-release copy. Returns "" if even that fails, which
    renders as no pitch line rather than filler.
    """
    try:
        from content.generator import _rule_based_enrich
        text = (_rule_based_enrich(e) or "").strip()
    except Exception:
        return ""
    if not text:
        return ""
    return sanitize_pitch(text)


def _parse_hour(time_str: str) -> Optional[int]:
    """Best-effort start hour (0-23) from a messy time string. None if unknown."""
    s = (time_str or "").strip()
    if not s:
        return None
    s = s.replace(" ", " ").replace(" ", " ")
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?", s, re.I)
    if m:
        hour = int(m.group(1)) % 12
        if m.group(3).lower() == "p":
            hour += 12
        return hour
    m = re.match(r"^(\d{1,2}):(\d{2})", s)
    if m:
        h = int(m.group(1))
        return h if 0 <= h <= 23 else None
    return None


def _blocked_from_headline(e: Dict) -> bool:
    if e.get("never_feature"):
        return True
    blob = f"{e.get('name','')} {e.get('venue','')}".lower()
    return any(sig in blob for sig in _NEVER_HEADLINE)


# Sources that are queer BY DEFINITION (a curated subset of
# config.LGBTQ_SOURCES). The full list includes general-interest aggregators
# like tulsa_isnt_boring and venues like circle_cinema/philbrook, so it cannot
# be used wholesale as a "this is a queer event" signal.
_QUEER_SOURCES = {
    "black_queer_tulsa", "circles_lgbtq", "club_majestic_ig", "council_oak",
    "dvl_ig", "freedom_oklahoma", "goff_center", "homo_hotel", "hotmess_sports",
    "klassic", "okeq", "okeq_calendar", "pflag_ig", "pflag_tulsa", "qlist",
    "slack_unite_lgbtq_plus", "studio_66", "tulsa_eagle_ig", "twisted_arts",
    "ybr_ig",
}

# Tulsa's queer bars and community spaces. A talent night at Club Majestic is
# a queer event even when nothing in its title says so.
_QUEER_VENUES = (
    "club majestic", "majestic", "tulsa eagle", "yellow brick road", "ybr",
    "dvl", "studio 66", "equality center", "dennis r. neill", "dennis r neill",
    "the hunt club", "renegades",
)


def _is_queer_draw(e: Dict) -> bool:
    """True if this reads as a queer event: by name, by venue, or by source."""
    blob = f"{e.get('name','')} {e.get('venue','')} {e.get('source','')}".lower()
    if any(k in blob for k in _QUEER_DRAW):
        return True
    if (e.get("source") or "").lower() in _QUEER_SOURCES:
        return True
    venue = (e.get("venue") or "").lower()
    return any(v in venue for v in _QUEER_VENUES)


def _is_special_edition(e: Dict) -> bool:
    name = (e.get("name") or "").lower()
    return any(sig in name for sig in _SPECIAL_SIGNALS)


# --------------------------------------------------------------------------
# History: what has this weekend already seen, week after week?
# --------------------------------------------------------------------------

def load_history(current_week: str, weeks: int = HISTORY_WEEKS) -> Dict[str, int]:
    """Return {name_key: number_of_prior_weeks_it_appeared_on_a_weekend}.

    Only Fri/Sat/Sun rows count, so a Tuesday fixture is not mistaken for a
    weekend weekly. Backup files (.bak*) are ignored.
    """
    counts: Dict[str, set] = defaultdict(set)
    paths = sorted(glob.glob(os.path.join(config.EVENTS_DIR, "*_all.json")))
    paths = [p for p in paths if p.endswith("_all.json")]
    # Most recent `weeks` files strictly before the current week key.
    prior = [p for p in paths
             if os.path.basename(p).replace("_all.json", "") < current_week]
    for path in prior[-weeks:]:
        wk = os.path.basename(path).replace("_all.json", "")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        events = data if isinstance(data, list) else data.get("events", [])
        for e in events:
            try:
                d = datetime.strptime(e.get("date", ""), "%Y-%m-%d").date()
            except Exception:
                continue
            if d.weekday() not in (4, 5, 6):
                continue
            key = _name_key(e)
            if key:
                counts[key].add(wk)
    return {k: len(v) for k, v in counts.items()}


# --------------------------------------------------------------------------
# Window + scoring
# --------------------------------------------------------------------------

def weekend_window(today: Optional[datetime] = None) -> Tuple[str, str, str]:
    """(friday, saturday, sunday) ISO dates for the upcoming/current weekend."""
    d = (today or datetime.now()).date()
    # Mon(0)..Sun(6). On Sat/Sun we mean THIS weekend, not next.
    if d.weekday() in (5, 6):
        friday = d - timedelta(days=d.weekday() - 4)
    else:
        friday = d + timedelta(days=(4 - d.weekday()) % 7)
    return (friday.isoformat(),
            (friday + timedelta(days=1)).isoformat(),
            (friday + timedelta(days=2)).isoformat())


def in_window(e: Dict, friday: str, saturday: str, sunday: str) -> bool:
    date = e.get("date")
    if date == saturday or date == sunday:
        return True
    if date == friday:
        hour = _parse_hour(e.get("time"))
        # Unknown-time Friday events are kept only if they read as nightlife.
        if hour is None:
            return _is_queer_draw(e) or _is_special_edition(e)
        return hour >= FRIDAY_CUTOFF_HOUR
    return False


def novelty(e: Dict, history: Dict[str, int]) -> Tuple[int, str]:
    """Score an event's freshness. Higher = more newsworthy this weekend.

    Returns (score, label) where label is one of 'new', 'special', 'occasional',
    'weekly'. 'weekly' events are the ones that made the old post feel like a
    rerun — they still get a mention, never a headline.
    """
    key = _name_key(e)
    seen = history.get(key, 0)
    source = (e.get("source") or "").lower()

    if source == "recurring" or seen >= WEEKLY_THRESHOLD:
        label = "weekly"
        score = 0
    elif seen == 0:
        label = "new"
        score = 60
    else:
        label = "occasional"
        score = 35 - (seen * 5)

    # A themed/special edition of a regular night IS news — pull it back up,
    # but never above a genuine first-appearance.
    if label == "weekly" and _is_special_edition(e):
        label = "special"
        score = 45

    if _is_queer_draw(e):
        score += 25
    if e.get("lgbtq_relevant"):
        score += 10
    if _clean_venue(e.get("venue")):
        score += 5
    if e.get("url"):
        score += 3
    if _parse_hour(e.get("time")) is not None:
        score += 3
    # Priority 1 = primary LGBTQ source in this codebase.
    if e.get("priority") == 1:
        score += 5

    return score, label


# --------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------

def select(events: List[Dict],
           today: Optional[datetime] = None) -> Dict:
    """Pick the weekend lineup. Returns a structured selection dict."""
    friday, saturday, sunday = weekend_window(today)
    history = load_history(config.current_week_key())

    pool = [e for e in events if in_window(e, friday, saturday, sunday)]

    # Dedupe: same event scraped from two sources, or listed twice with a
    # renamed title. Keep the richest record (most non-empty fields).
    best: Dict[str, Dict] = {}
    for e in pool:
        key = f"{e.get('date')}|{_name_key(e)}"
        if not _name_key(e):
            continue
        prev = best.get(key)
        if prev is None or _richness(e) > _richness(prev):
            best[key] = e
    pool = list(best.values())

    scored = []
    for e in pool:
        score, label = novelty(e, history)
        # Normalize on the record itself, not just in the caption. make_day_slide
        # reads e["time"]/e["description"] straight from the dict, so repairing
        # only the caption left "6:00PM8:30PM18:0020:30" printed on the slide.
        clean = {**e, "_score": score, "_novelty": label}
        clean["time"] = clean_time(e.get("time"))
        clean["venue"] = _clean_venue(e.get("venue"))
        # Enrich from the CLEANED record, never the raw one, or the junk venue
        # ("in 6 days") gets written straight into the generated pitch.
        clean["description"] = clean_pitch(e) or _fallback_pitch(clean)
        # image_maker prefers slide_description over description. Monday's deck
        # leaves a templated slide_description on the record, so leaving it in
        # place silently overrode the cleaned/voice-passed copy on the slides
        # while the caption showed the good version. Drop it; description wins.
        clean.pop("slide_description", None)
        clean.pop("website_description", None)
        scored.append(clean)

    by_day: Dict[str, List[Dict]] = {friday: [], saturday: [], sunday: []}
    for e in scored:
        by_day.setdefault(e.get("date"), []).append(e)

    headlines: Dict[str, List[Dict]] = {}
    weeklies: List[Dict] = []
    # A multi-night run (a touring comic playing Fri + Sat + Sun) is ONE thing
    # to tell people about, not three. Track what has already been headlined
    # across the whole weekend so it cannot eat three slots.
    used_runs: set = set()

    for date in (friday, saturday, sunday):
        # Queer events sort ahead of everything else within a day. This is a
        # gay events account: a Sunday that leads with a general book club
        # while a queer night sits further down is an editorial failure, not a
        # scoring one. Freshness still orders within each group.
        day_events = sorted(
            by_day.get(date, []),
            key=lambda x: (not _is_queer_draw(x), -x["_score"], x.get("name", "")))
        eligible = [e for e in day_events if not _blocked_from_headline(e)]
        fresh = [e for e in eligible if e["_novelty"] != "weekly"]
        rerun = [e for e in eligible if e["_novelty"] == "weekly"]

        picks: List[Dict] = []
        for e in fresh:
            run = _run_key(e)
            if run in used_runs:
                continue
            used_runs.add(run)
            picks.append(e)
            if len(picks) >= MAX_PER_DAY:
                break

        # Guarantee a queer anchor every day. A day of comedy-club and
        # farmers-market listings is not what this account is for; if the day
        # has ANY queer-draw event, one of them holds a slot even when it is a
        # weekly fixture. Weeklies still never take the lead position.
        if not any(_is_queer_draw(e) for e in picks):
            anchor = next((e for e in eligible
                           if _is_queer_draw(e) and _run_key(e) not in used_runs), None)
            if anchor is not None:
                used_runs.add(_run_key(anchor))
                if len(picks) >= MAX_PER_DAY:
                    picks = picks[:MAX_PER_DAY - 1]
                picks.append(anchor)

        # Only pad with a weekly when the day would otherwise look empty.
        if len(picks) < 2:
            for e in rerun:
                if _run_key(e) in used_runs:
                    continue
                used_runs.add(_run_key(e))
                picks.append(e)
                if len(picks) >= 2:
                    break

        headlines[date] = picks
        weeklies.extend([e for e in rerun if e not in picks])

    fresh_count = sum(
        1 for d in headlines.values() for e in d if e["_novelty"] in ("new", "special"))

    return {
        "friday": friday,
        "saturday": saturday,
        "sunday": sunday,
        "headlines": headlines,
        "weeklies": _dedupe_weeklies(weeklies),
        "pool_size": len(pool),
        "fresh_count": fresh_count,
        "thin": fresh_count < MIN_FRESH_TARGET,
    }


def _run_key(e: Dict) -> str:
    """Collapse a multi-night run / re-titled same show into one identity.

    "Kam Patterson" and "Kam Patterson | Santa's Golden Ticket Pack" at the
    same venue are one booking with two ticket types. Keyed on the first few
    name tokens plus the venue so genuinely different shows stay separate.
    """
    tokens = _norm(e.get("name")).split()
    head = " ".join(tokens[:2])
    venue = _norm(e.get("venue"))[:20]
    return f"{head}|{venue}"


def _richness(e: Dict) -> int:
    return sum(1 for k in ("time", "venue", "url", "description",
                           "website_description") if e.get(k))


def _dedupe_weeklies(weeklies: List[Dict]) -> List[Dict]:
    """One entry per recurring night, best-scoring instance wins."""
    seen: Dict[str, Dict] = {}
    for e in weeklies:
        key = _name_key(e)
        if key and (key not in seen or e["_score"] > seen[key]["_score"]):
            seen[key] = e
    return sorted(seen.values(), key=lambda x: -x["_score"])


# --------------------------------------------------------------------------
# Caption
# --------------------------------------------------------------------------

def _fmt_when(e: Dict) -> str:
    date = e.get("date", "")
    try:
        day = _DAY_LABEL[datetime.strptime(date, "%Y-%m-%d").date().weekday()].title()
    except Exception:
        day = ""
    time = clean_time(e.get("time"))
    venue = _clean_venue(e.get("venue"))
    bits = [b for b in (day, time, venue) if b]
    return ", ".join(bits)


# Instagram hard-rejects a caption over 2200 characters ("The caption was too
# long"). Facebook has no practical limit. Build once, trim for IG.
IG_CAPTION_LIMIT = 2200


def build_caption(sel: Dict, hashtags: Optional[str] = None,
                  max_chars: Optional[int] = None,
                  with_pitches: bool = True) -> str:
    lines = ["THIS WEEKEND IN TULSA"]
    lines.append("")

    any_listed = False
    for date in (sel["friday"], sel["saturday"], sel["sunday"]):
        picks = sel["headlines"].get(date) or []
        if not picks:
            continue
        any_listed = True
        for e in picks:
            when = _fmt_when(e)
            lines.append(f"{e.get('name','').strip()}")
            if when:
                lines.append(when)
            pitch = clean_pitch(e) if with_pitches else ""
            if pitch:
                lines.append(pitch)
            lines.append("")

    if not any_listed:
        return ""

    weeklies = sel.get("weeklies") or []
    if weeklies:
        names = ", ".join(
            f"{w.get('name','').strip()} ({_clean_venue(w.get('venue')) or 'Tulsa'})"
            for w in weeklies[:4])
        lines.append(f"Running like always: {names}.")
        lines.append("")

    lines.append("Every event, every day, at tulsagays.com")
    lines.append("")
    lines.append(hashtags or
                 "#TulsaGays #TulsaLGBTQIA #LGBTQTulsa #TulsaEvents #GayTulsa #TulsaWeekend")

    caption = "\n".join(lines)
    # House rule: no em dashes, ever.
    caption = caption.replace("—", ",").replace("–", "-")

    if max_chars and len(caption) > max_chars:
        # Step 1: drop the per-event pitch lines. Names, days, times and venues
        # are the load-bearing content; the pitch is the luxury.
        if with_pitches:
            return build_caption(sel, hashtags=hashtags, max_chars=max_chars,
                                 with_pitches=False)
        # Step 2: still too long (a very full weekend). Trim whole events off
        # the end rather than truncating mid-word.
        trimmed = dict(sel)
        trimmed["headlines"] = {k: list(v) for k, v in sel["headlines"].items()}
        for date in reversed([sel["friday"], sel["saturday"], sel["sunday"]]):
            while len(caption) > max_chars and trimmed["headlines"].get(date):
                trimmed["headlines"][date].pop()
                caption = build_caption(trimmed, hashtags=hashtags,
                                        with_pitches=False)
            if len(caption) <= max_chars:
                break
    return caption


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------

def voice_pass(sel: Dict, budget_s: int = 180) -> Dict:
    """LLM-rewrite the copy for ONLY the headline events (~12).

    Same engine Monday's deck uses (content.generator.voice_enrich), scoped to
    the handful of events this post actually shows so it fits a wall-clock
    budget. On any failure the rule-based copy already on each record stands,
    so the post always ships.
    """
    shown = [e for d in sel["headlines"].values() for e in d]
    if not shown:
        return {"total": 0, "llm": 0, "rule": 0}
    try:
        from content.generator import voice_enrich
        stats = voice_enrich(shown, budget_s=budget_s, batch=6)
    except Exception as exc:
        print(f"[voice] LLM pass unavailable, keeping rule-based copy: {exc}")
        return {"total": len(shown), "llm": 0, "rule": len(shown)}
    # The LLM can reintroduce em dashes, and on a miss it sometimes echoes the
    # source description verbatim, URLs and all. Re-gate everything it wrote,
    # and clear any slide_description it may have set so `description` wins.
    for e in shown:
        for field in ("description", "website_description"):
            if e.get(field):
                e[field] = sanitize_pitch(e[field])
        e.pop("slide_description", None)
    return stats


def render(sel: Dict, out_dir: Optional[str] = None) -> List[str]:
    """Render cover + one slide per populated day. Returns saved paths."""
    from content.image_maker import (make_cover_slide, make_day_slide,
                                     save_carousel)

    out_dir = out_dir or os.path.join(
        config.DATA_DIR, "posts", config.current_week_key(), "weekend")

    fri = datetime.strptime(sel["friday"], "%Y-%m-%d").date()
    sun = datetime.strptime(sel["sunday"], "%Y-%m-%d").date()
    date_range = f"{fri.strftime('%b %-d') if os.name != 'nt' else fri.strftime('%b %#d')}" \
                 f" - {sun.strftime('%b %-d') if os.name != 'nt' else sun.strftime('%b %#d')}"

    # Lead with the highest-scoring fresh event across the whole weekend.
    all_picks = [e for d in sel["headlines"].values() for e in d]
    lead = max(all_picks, key=lambda x: x["_score"]) if all_picks else None

    images = [make_cover_slide(
        "THIS WEEKEND", date_range, featured_event=lead,
        headline="THIS WEEKEND IN TULSA",
        feature_label="PICK OF THE WEEKEND",
        footer_note="Every event, every day · visit for the full list",
        tagline="Friday night through Sunday. Pick one and go.")]

    for date in (sel["friday"], sel["saturday"], sel["sunday"]):
        picks = sel["headlines"].get(date) or []
        if not picks:
            continue
        try:
            label = _DAY_LABEL[datetime.strptime(date, "%Y-%m-%d").date().weekday()]
        except Exception:
            continue
        images.append(make_day_slide(label.title(), picks,
                                     total_day_events=len(picks)))

    return save_carousel(images, out_dir, prefix="weekend")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def load_events() -> List[Dict]:
    wk = config.current_week_key()
    path = os.path.join(config.EVENTS_DIR, f"{wk}_all.json")
    if not os.path.exists(path):
        raise SystemExit(
            f"[FAIL] {wk} event data missing at {path}. Monday scrape missing. STOP.")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("events", [])


def _print_selection(sel: Dict) -> None:
    print(f"Weekend window: {sel['friday']} (evening) .. {sel['sunday']}")
    print(f"Candidate pool: {sel['pool_size']}   fresh headline events: {sel['fresh_count']}")
    for date in (sel["friday"], sel["saturday"], sel["sunday"]):
        picks = sel["headlines"].get(date) or []
        label = _DAY_LABEL.get(
            datetime.strptime(date, "%Y-%m-%d").date().weekday(), date)
        print(f"\n{label} {date}  ({len(picks)})")
        for e in picks:
            print(f"   [{e['_novelty']:>10} {e['_score']:>3}] "
                  f"{(e.get('name') or '')[:52]:<52} @ {_clean_venue(e.get('venue'))[:28]}")
    if sel["weeklies"]:
        print(f"\nFolded into 'running like always' ({len(sel['weeklies'])}):")
        for e in sel["weeklies"][:8]:
            print(f"   {(e.get('name') or '')[:52]}")
    if sel["thin"]:
        print(f"\n[THIN WEEKEND] only {sel['fresh_count']} genuinely new events "
              f"(target {MIN_FRESH_TARGET}). This is a SUPPLY problem: run the "
              f"venue dig (data/venue_dig_playbook.md) and read the bar IG flyers.")


def _selftest() -> int:
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("  ok  " if cond else "  FAIL") + "  " + msg)
        ok = ok and bool(cond)

    print("weekend_carousel selftest")

    # Window: from a Friday, a Wednesday, and a Sunday.
    f, s, u = weekend_window(datetime(2026, 7, 31))   # Friday
    check((f, s, u) == ("2026-07-31", "2026-08-01", "2026-08-02"), "window from Friday")
    f2, _, _ = weekend_window(datetime(2026, 7, 29))  # Wednesday
    check(f2 == "2026-07-31", "window from midweek looks ahead")
    f3, _, u3 = weekend_window(datetime(2026, 8, 2))  # Sunday
    check((f3, u3) == ("2026-07-31", "2026-08-02"), "window on Sunday stays on this weekend")

    # Friday cutoff
    early = {"date": "2026-07-31", "time": "10:30 AM", "name": "Shut Up & Write"}
    late = {"date": "2026-07-31", "time": "9:00 PM", "name": "Drag Show"}
    check(not in_window(early, f, s, u), "Friday morning coffee excluded")
    check(in_window(late, f, s, u), "Friday night show included")

    # Hour parsing incl. unicode narrow space
    check(_parse_hour("9:30 PM") == 21, "parses narrow-space PM time")
    check(_parse_hour("") is None, "empty time is unknown")

    # Novelty: a four-week regular is weekly, a first-timer is new
    hist = {_name_key({"name": "2000s Night", "venue": "DVL"}): 5}
    weekly_score, weekly_label = novelty(
        {"name": "2000s Night", "venue": "DVL", "source": "dvl_ig"}, hist)
    new_score, new_label = novelty(
        {"name": "Snack n Shop Clothes Swap", "venue": "yogaQuest"}, hist)
    check(weekly_label == "weekly", "repeat night labeled weekly")
    check(new_label == "new", "first appearance labeled new")
    check(new_score > weekly_score, "new outranks weekly")

    # source=recurring is weekly regardless of history
    _, rec_label = novelty(
        {"name": "Babes & Bi-cons", "venue": "YBR", "source": "recurring"}, {})
    check(rec_label == "weekly", "source=recurring is weekly")

    # A themed edition of a weekly gets rescued
    _, sp_label = novelty(
        {"name": "2000s Night: Britney Tribute Edition", "venue": "DVL",
         "source": "recurring"}, hist)
    check(sp_label == "special", "themed edition of a weekly is rescued as special")

    # Name normalization ignores month/day noise
    check(_norm("Drag Brunch : jul. 11th - stars") ==
          _norm("Drag Brunch : aug. 1st - stars"), "date noise stripped from name key")
    # Leading-article variance across sources (the bug that made a six-week
    # running open talent night score as a first appearance)
    check(_name_key({"name": "The Sunday Showdown! Open Talent Night"}) ==
          _name_key({"name": "Sunday Showdown Open Talent Night"}),
          "leading article ignored in name key")
    # Venue instability must not break identity
    check(_name_key({"name": "2000s Night", "venue": "DVL"}) ==
          _name_key({"name": "2000s Night", "venue": "DVL, 116 S Elgin Ave"}),
          "venue variance ignored in name key")

    # Time repair (live W31 carried these exact mangled values)
    check(clean_time("6:00 PM8:30 PM18:0020:30") == "6:00 PM - 8:30 PM",
          "concatenated time range repaired")
    check(clean_time("2:00 PM4:00 PM14:0016:00") == "2:00 PM - 4:00 PM",
          "second concatenated range repaired")
    check(clean_time("9:45 PM") == "9:45 PM", "single time preserved")
    check(clean_time("") == "", "empty time stays empty")

    # Hard sanitizer: nothing with a URL, tracking param, relative-date
    # fragment, or unwrappable token may reach a slide. W31 shipped a raw
    # ?fbclid= URL that ran off both edges of the Sunday slide.
    check(sanitize_pitch("Head over to https://example.com/x?fbclid=IwZXh0bg") == "",
          "URL in copy rejected")
    check(sanitize_pitch("Go to www.tulsagays.com for more") == "",
          "bare www link rejected")
    check(sanitize_pitch("David Jolly at in 6 days is a good time") == "",
          "relative-date fragment rejected anywhere in the line")
    check(sanitize_pitch("Tickets " + "x" * 45) == "",
          "unwrappable long token rejected")
    check(sanitize_pitch("Claim your corner, sugar, and settle in.") ==
          "Claim your corner, sugar, and settle in.", "clean copy survives")
    check("—" not in sanitize_pitch("A line — with a dash"), "em dash converted")
    # Truncation used to hide junk from the pattern: "... one. in 6 days ago"
    # cut at 150 chars became "... one. in 6..." which no longer matched.
    check(clean_pitch({"description": "Going solo to David Jolly is a power move, "
                       "sugar. Claim a corner, settle in, and you will be in a "
                       "conversation before you decide to start one. in 6 days ago"}) == "",
          "junk surviving truncation is caught (sanitize before truncate)")
    check(sanitize_pitch("a decent line that trails off in 6...") == "",
          "truncated relative-date tail rejected")

    # Raw scraper copy is dropped rather than shipped
    check(clean_pitch({"description":
                       "Tulsa Artist Fellowship is proud to partner withBemis "
                       "CenterandThe Church Arthouseto present"}) == "",
          "run-on scraped copy rejected")
    check(clean_pitch({"description":
                       "Join us for an evening of readings and conversation "
                       "with local authors."}) == "",
          "press-release opener rejected")
    check(clean_pitch({"description":
                       "Frosted tips, low-rise jeans, and a crowd that will "
                       "scream every word with you, honey."}),
          "real voice copy kept")

    # Headline blocks
    check(_blocked_from_headline({"name": "PFLAG Tulsa Monthly Meeting"}),
          "monthly meeting blocked from headline")
    check(_blocked_from_headline({"name": "X", "never_feature": True}),
          "never_feature respected")
    check(not _blocked_from_headline({"name": "Drag Bingo"}), "drag bingo headline-eligible")

    # Junk venue scrub (the 'in 5 days' leakage seen in W31 data)
    check(_clean_venue("in 5 days") == "", "relative-date venue junk scrubbed")
    check(_clean_venue("Club Majestic") == "Club Majestic", "real venue preserved")

    # Queer detection by venue and source, not just by name keyword
    check(_is_queer_draw({"name": "Sunday Showdown Open Talent Night",
                          "venue": "Club Majestic, 124 N Boston Ave"}),
          "queer venue recognized without a keyword in the name")
    check(_is_queer_draw({"name": "2000s Night", "venue": "DVL",
                          "source": "dvl_ig"}), "queer source recognized")
    check(not _is_queer_draw({"name": "Kam Patterson",
                              "venue": "Bricktown Comedy Club Tulsa"}),
          "comedy club not treated as queer")

    # Multi-night run / re-titled same booking collapses to one identity
    check(_run_key({"name": "Kam Patterson", "venue": "Bricktown Comedy Club"}) ==
          _run_key({"name": "Kam Patterson | Santa's Golden Ticket Pack",
                    "venue": "Bricktown Comedy Club"}),
          "re-titled same booking collapses to one run")
    check(_run_key({"name": "Drag Bingo", "venue": "YBR"}) !=
          _run_key({"name": "Drag Brunch", "venue": "YBR"}),
          "different shows at one venue stay separate")

    # Selection end-to-end on a synthetic week
    fake = [
        {"name": "2000s Night", "venue": "DVL", "date": s, "time": "9:00 PM",
         "source": "dvl_ig", "lgbtq_relevant": True},
        {"name": "Clothes Swap", "venue": "yogaQuest", "date": s, "time": "1:00 PM",
         "lgbtq_relevant": True},
        {"name": "Sunday Showdown", "venue": "Club Majestic", "date": u,
         "time": "8:00 PM", "source": "recurring", "lgbtq_relevant": True},
        {"name": "Coffee", "venue": "Foolish Things", "date": f, "time": "8:00 AM"},
    ]
    sel = select(fake, today=datetime(2026, 7, 31))
    check(all(e.get("name") != "Coffee"
              for d in sel["headlines"].values() for e in d),
          "Friday morning coffee not selected")
    cap = build_caption(sel)
    check("—" not in cap, "caption has no em dashes")
    check("tulsagays.com" in cap, "caption carries the URL")

    # IG length cap: a full 12-event caption with pitches blows past 2200 and
    # Instagram hard-rejects it ("The caption was too long").
    big = {
        "friday": f, "saturday": s, "sunday": u, "weeklies": [], "thin": False,
        "fresh_count": 12, "pool_size": 12,
        "headlines": {d: [{"name": f"Event {d} {i}", "date": d,
                           "time": "9:00 PM", "venue": "Some Venue In Tulsa",
                           "description": "A nicely written pitch line that "
                                          "runs on for a good while, sugar."}
                          for i in range(4)] for d in (f, s, u)},
    }
    long_cap = build_caption(big)
    short_cap = build_caption(big, max_chars=IG_CAPTION_LIMIT)
    check(len(short_cap) <= IG_CAPTION_LIMIT, "IG caption respects the 2200 cap")
    check("tulsagays.com" in short_cap, "trimmed caption still carries the URL")
    check("#TulsaGays" in short_cap, "trimmed caption still carries hashtags")
    check(len(short_cap) <= len(long_cap), "trimming shortens, never grows")

    print("\nSELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the selection and caption, render nothing")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", default=None, help="output dir for slides")
    ap.add_argument("--json", action="store_true",
                    help="emit the selection as JSON (for the task handler)")
    ap.add_argument("--no-voice", action="store_true",
                    help="skip the LLM voice pass, ship rule-based copy")
    ap.add_argument("--voice-budget", type=int, default=180,
                    help="wall-clock seconds for the LLM voice pass")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    events = load_events()
    sel = select(events)

    if not args.no_voice and not args.json:
        stats = voice_pass(sel, budget_s=args.voice_budget)
        print(f"[voice] {stats.get('llm', 0)} LLM / {stats.get('rule', 0)} rule "
              f"of {stats.get('total', 0)} shown events")

    caption = build_caption(sel)

    if args.json:
        print(json.dumps({
            "friday": sel["friday"], "saturday": sel["saturday"],
            "sunday": sel["sunday"], "thin": sel["thin"],
            "fresh_count": sel["fresh_count"], "caption": caption,
            "headlines": {k: [{"name": e.get("name"), "venue": e.get("venue"),
                               "time": e.get("time"), "novelty": e["_novelty"]}
                              for e in v]
                          for k, v in sel["headlines"].items()},
        }, indent=2, ensure_ascii=False))
        return 0

    _print_selection(sel)
    print("\n--- CAPTION ---\n")
    print(caption)

    if args.dry_run:
        return 0

    paths = render(sel, args.out)
    print(f"\nRendered {len(paths)} slides:")
    for p in paths:
        print("  " + p)
    cap_path = os.path.join(os.path.dirname(paths[0]), "caption.txt")
    with open(cap_path, "w", encoding="utf-8") as f:
        f.write(caption)
    print("  " + cap_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
