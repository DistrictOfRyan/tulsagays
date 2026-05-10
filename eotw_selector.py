"""
Event of the Week (EOTW) selection — shared logic for post_weekly.py and main.py.

Priority tiers (hard order, non-negotiable):
  0  Homo Hotel Happy Hour        — only if in this Mon-Sun week
  1  Council Oak Men's Chorale    — any week they perform
  2  Drag shows                   — explicit drag performances (highest crowd-draw)
  3  Queer performances           — cabaret, pride events, queer nights, pride parties
  4  Ticketed trusted-source LGBTQ events — must have a URL
  5  Non-recurring LGBTQ-relevant events  — catch-all for the rare strong week

Within each tier, secondary sort: Fri-Sun > Mon-Thu, has URL, richer description.

NEVER EOTW — excluded unconditionally:
  Bar events, bowling leagues, AA meetings, recurring weekly events (support groups,
  health clinics, classes, sound baths), Club Majestic, and any non-LGBTQ event.
"""

from datetime import datetime
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Exclusion rules
# ---------------------------------------------------------------------------

_SKIP_SOURCES = {"recurring", "aa_meetings", "bars"}

_SKIP_NAME_FRAGMENTS = {
    "bowling league", "bowling night",
    "aa meeting", "aa meetings",
    "support group",
    "sound bath",
    "health clinic", "okeq health", "okeq senior",
    "hope testing",
    "drop-in therapy", "therapy session", "free drop-in",
    "health outreach",
    "girl scout",
    "mix and mingle",
    "shut up & write",
    "raise your spiritual iq",
    "book club - tulsa",
    "scrabble",
    "tabletop",
    "ttrpg",
    "touchtunes",          # weekly Eagle bar promo, never special
    "happy hour!",         # generic bar open-door entries (not HHHH)
    "leather night",
    "shenanigans",
    "eagle bingo",
    "derby watch",
    "derby hat",
}

_SKIP_VENUES = {
    "majestic",            # Club Majestic — per organizer policy, never feature
    "124 n boston",        # Club Majestic address fallback
}


def _is_skip(e: Dict) -> bool:
    """Return True if this event must never appear as EOTW."""
    src   = (e.get("source")  or "").lower()
    name  = (e.get("name")    or "").lower()
    venue = (e.get("venue")   or "").lower()
    return (
        src in _SKIP_SOURCES
        or any(frag in name  for frag in _SKIP_NAME_FRAGMENTS)
        or any(v    in venue for v    in _SKIP_VENUES)
    )


# ---------------------------------------------------------------------------
# Tier detectors
# ---------------------------------------------------------------------------

def _is_hh(e: Dict) -> bool:
    """Homo Hotel Happy Hour."""
    return "homo hotel" in (
        (e.get("name") or "") + " " + (e.get("source") or "")
    ).lower()


def _is_council(e: Dict) -> bool:
    """Council Oak Men's Chorale or COMC."""
    combined = (
        (e.get("name") or "") + " " + (e.get("source") or "")
    ).lower()
    return "council oak" in combined or "comc" in combined


# Drag shows — explicit drag performances get their own tier because they
# reliably draw the largest crowds and are the most explicitly queer content.
_DRAG_KW = {
    "drag show", "drag bingo", "drag brunch",
    "drag queen", "drag king",
    "drag performance", "drag night", "drag performer",
    "dragnificent", "inner circle drag",
    "drag extravaganza", "drag pageant", "drag ball",
    "drag revue",
}

# Queer performances that aren't "drag shows" per se but are high-value
# explicitly LGBTQ events worth headlining.
_QUEER_PERF_KW = {
    "cabaret",
    "pride show", "pride event", "pride night",
    "pride dance", "pride party",
    "queer night", "gay night", "lgbtq+ night",
    "queer prom", "queer disco", "rainbow night",
    "queer film", "queer cinema",
    "pride fundraiser", "queer fundraiser",
}

# Trusted primary LGBTQ sources (not just LGBTQ-keyword-matching).
# Events from these orgs can reach Tier 4 even without LGBTQ keywords in name.
_TRUSTED_LGBTQ_SRCS = {
    "twisted_arts",
    "freedom_oklahoma",
    "black_queer_tulsa",
    "all_souls_special",
    "slack_unite_lgbtq_plus",
}

# Keywords that make an event explicitly LGBTQ-relevant for Tier 5.
_LGBTQ_KW = {
    "lgbtq", "queer", "gay", "lesbian", "trans",
    "bisexual", "nonbinary", "non-binary",
    "pride", "rainbow", "equality",
    "homo", "sapphic", "affirming",
    "gender outreach",
}


def _text(e: Dict) -> str:
    """Combined lowercase text for keyword matching."""
    return " ".join([
        e.get("name",        ""),
        e.get("description", ""),
        e.get("venue",       ""),
        e.get("source",      ""),
    ]).lower()


def _is_drag(e: Dict) -> bool:
    t = _text(e)
    return any(kw in t for kw in _DRAG_KW)


def _is_queer_perf(e: Dict) -> bool:
    t = _text(e)
    return any(kw in t for kw in _QUEER_PERF_KW)


def _is_lgbtq(e: Dict) -> bool:
    if (e.get("source") or "").lower() in _TRUSTED_LGBTQ_SRCS:
        return True
    t = _text(e)
    return any(kw in t for kw in _LGBTQ_KW)


# ---------------------------------------------------------------------------
# Within-tier sort key
# ---------------------------------------------------------------------------

def _sort_key(e: Dict) -> tuple:
    """
    Secondary sort within a tier (ascending = better):
      1. Weekend (Fri-Sun) before weekday
      2. Has a URL (ticketed/specific) before no URL
      3. Richer description (longer = more substance)
    """
    date_str = e.get("date") or ""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        day_score = 0 if dt.weekday() >= 4 else 1   # Fri=4, Sat=5, Sun=6
    except Exception:
        day_score = 2                                 # unknown date — deprioritize

    url_score  = 0 if e.get("url") else 1
    desc_score = -(len(e.get("description") or ""))  # negate — longer is better

    return (day_score, url_score, desc_score)


# ---------------------------------------------------------------------------
# Main selector
# ---------------------------------------------------------------------------

def select_eotw(events_this_week: List[Dict]) -> Optional[Dict]:
    """
    Return the single best Event of the Week from events already filtered
    to the current Mon-Sun window.  Returns None when no suitable LGBTQ
    event is found (the caller should handle that gracefully, not fall back
    to a random community event).
    """
    if not events_this_week:
        return None

    eligible = [e for e in events_this_week if not _is_skip(e)]

    # Tier 0 — Homo Hotel Happy Hour
    pool = sorted([e for e in eligible if _is_hh(e)], key=_sort_key)
    if pool:
        return pool[0]

    # Tier 1 — Council Oak Men's Chorale / COMC
    pool = sorted([e for e in eligible if _is_council(e)], key=_sort_key)
    if pool:
        return pool[0]

    # Tier 2 — Drag shows (most explicitly queer, highest attendance draw)
    pool = sorted([e for e in eligible if _is_drag(e)], key=_sort_key)
    if pool:
        return pool[0]

    # Tier 3 — Queer performances, pride events, queer nights
    pool = sorted(
        [e for e in eligible if _is_queer_perf(e) and not _is_drag(e)],
        key=_sort_key,
    )
    if pool:
        return pool[0]

    # Tier 4 — Ticketed events from trusted primary LGBTQ sources
    pool = sorted(
        [
            e for e in eligible
            if (e.get("source") or "").lower() in _TRUSTED_LGBTQ_SRCS
            and e.get("url")
            and not _is_drag(e)
            and not _is_queer_perf(e)
        ],
        key=_sort_key,
    )
    if pool:
        return pool[0]

    # Tier 5 — Non-recurring LGBTQ-relevant events with explicit keywords
    pool = sorted(
        [
            e for e in eligible
            if _is_lgbtq(e)
            and not _is_drag(e)
            and not _is_queer_perf(e)
            and (e.get("source") or "").lower() not in _TRUSTED_LGBTQ_SRCS
        ],
        key=_sort_key,
    )
    if pool:
        return pool[0]

    # Nothing qualifies — return None so the cover can show a graceful fallback.
    # DO NOT fall back to a random community event.
    return None
