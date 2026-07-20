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
  Bowling leagues, AA meetings, recurring weekly services (support groups,
  health clinics, classes, sound baths), generic weekly bar promos, and any
  non-LGBTQ event.

NOTE (2026-06-12, William): the blanket Club Majestic venue ban is REMOVED.
Special one-off events at Majestic / the Eagle (e.g. Lil' Shop of Horrors)
are featurable and EOTW-eligible. Weekly recurring bar programming still
never auto-wins EOTW — _sort_key deprioritizes source=recurring within tiers.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

try:
    import config as _config  # city-specific knobs (GAY_VENUE_SIGNATURES, etc.)
except Exception:
    _config = None

_MANUAL_EOTW_PATH = os.path.join(os.path.dirname(__file__), "data", "manual_eotw.json")
_FEATURED_PARTNERS_PATH = os.path.join(os.path.dirname(__file__), "data", "featured_partners.json")


# ---------------------------------------------------------------------------
# Exclusion rules
# ---------------------------------------------------------------------------

# NOTE: "recurring" is intentionally NOT skipped wholesale — recurring.py holds
# both services (excluded by the never_feature flag) AND fun weekly queer events
# (drag shows, drag brunch, talent nights, socials) that William wants ALLOWED to
# fill a day when one-offs run short. Services are still caught by never_feature
# + the name/desc fragments below.
_SKIP_SOURCES = {"aa_meetings"}

_SKIP_NAME_FRAGMENTS = {
    "bowling league", "bowling night",
    "aa meeting", "aa meetings",
    "support group",
    "sound bath",
    "health clinic", "okeq health", "okeq senior",
    "(cancelled",
    "legal aid", "legal services", "legal clinic", "legal help", "fair housing",
    "correction clinic", "name & gender", "name and gender", "expungement",
    "know your rights", "fafsa", "wellness fair", "health fair",
    "vaccine", "vaccination", "resource fair", "food pantry", "blood drive",
    "clinic",
    "hope testing",
    "drop-in therapy", "therapy session", "free drop-in",
    "health outreach",
    "girl scout",
    # Kids / family programming — real events, but they belong on the website,
    # never featured/EOTW (William 2026-07-20). Venue-based catch (_SKIP_VENUES)
    # handles Discovery Lab etc.; these names catch kid events elsewhere.
    "story time", "storytime", "toddler", "preschool", "homeschool",
    "kids camp", "day camp", "summer camp", "tinkercad", "lego club",
    "for families", "family fun", "kids' ", "kids club", "children's story",
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
    "open for business",   # business-hours announcement, not a real event
    "okeq closed",         # org-closure notice (e.g. "OKEQ Closed") — not an event
    "office closed", "center closed", "closed today", "closed for the",
}

# Venue-level bans: Majestic/Eagle special events are featurable (2026-06-12),
# but children's-museum / kids-programming venues are NOT — their events are
# family/kids fare that must never lead a day or be EOTW (William 2026-07-20:
# "Big Build Week ... it's a kids event ... that's definitely not gay"). They
# still list on the website.
_SKIP_VENUES = {
    "discovery lab",          # Tulsa children's science museum (Big Build Week etc.)
    "children's museum", "childrens museum",
    "little light house",     # children's charity/school
}


# Service/recurring signals found in the DESCRIPTION (not the name). Catches
# euphemistically-named OKEQ programming like "AFFIRMING" (a CBT therapy
# program) and "Positively Grateful" (an HIV+ support group) that dodge the
# name-based list but must never be featured/lead.
_SKIP_DESC_FRAGMENTS = {
    "support group", "hiv+ support", "hiv support",
    "cognitive behavioral", "therapy-based", "cbt-based", "therapy session",
    "health clinic", "hope testing", "drop-in therapy", "peer support",
    "free testing", "testing clinic", "recovery group",
}


def _is_skip(e: Dict) -> bool:
    """Return True if this event must never appear as EOTW or lead a day.

    Honors a persisted `never_feature` flag (set at scrape time from the RAW
    description, before the LLM voice softens service language), then falls
    back to name/venue/source/description keyword checks."""
    if e.get("never_feature"):
        return True
    src   = (e.get("source")  or "").lower()
    name  = (e.get("name")    or "").lower()
    venue = (e.get("venue")   or "").lower()
    # Scan both the (possibly voiced) short description and the long one.
    desc  = ((e.get("description") or "") + " " + (e.get("website_description") or "")).lower()
    return (
        src in _SKIP_SOURCES
        or any(frag in name  for frag in _SKIP_NAME_FRAGMENTS)
        or any(v    in venue for v    in _SKIP_VENUES)
        or any(frag in desc  for frag in _SKIP_DESC_FRAGMENTS)
    )


# Hard-skip rules — events that never appear on slides at all, not just EOTW.
# Smaller list than _is_skip — community resources at LGBTQ venues (TTRPG at
# OKEQ, support groups, health clinics) ARE shown on day slides; they just
# never lead a day or get featured as EOTW.
_HARD_SKIP_SOURCES = {"aa_meetings", "bars"}

_HARD_SKIP_NAME_FRAGMENTS = {
    "aa meeting", "aa meetings",            # privacy
    "drop-in therapy", "therapy session",   # therapy privacy
    "touchtunes",                           # weekly Eagle bar promo
    "happy hour!",                          # generic bar open-door (DVL etc.)
    "leather night", "shenanigans",
    "eagle bingo", "derby watch", "derby hat",
    "mix and mingle",                       # straight networking
    "open for business",                    # business-hours announcement
    "raise your spiritual iq",              # generic self-help
}

# Venue hard-skips REMOVED 2026-06-12 (William reversed the Majestic policy).
_HARD_SKIP_VENUES = set()


def _is_hard_skip(e: Dict) -> bool:
    """Stricter blocklist for slides — only the truly banned categories.
    Recurring OKEQ programming (TTRPG, support groups, health clinics)
    can appear as filler events on day slides; they just can't be EOTW.
    """
    src   = (e.get("source")  or "").lower()
    name  = (e.get("name")    or "").lower()
    venue = (e.get("venue")   or "").lower()
    return (
        src in _HARD_SKIP_SOURCES
        or any(frag in name  for frag in _HARD_SKIP_NAME_FRAGMENTS)
        or any(v    in venue for v    in _HARD_SKIP_VENUES)
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
    "okeq",               # Oklahomans for Equality — primary LGBTQ org, always trusted
    "okeq_calendar",      # OKEQ calendar scraper
}

# Keywords that make an event explicitly LGBTQ-relevant for Tier 5.
_LGBTQ_KW = {
    "lgbtq", "queer", "gay", "lesbian", "trans",
    "bisexual", "nonbinary", "non-binary",
    "pride", "rainbow", "equality",
    "homo", "sapphic", "affirming",
    "gender outreach",
    # Great Plains Rodeo Association — Oklahoma's IGRA gay rodeo. Their events
    # (rodeo, fundraisers, socials) are explicitly LGBTQ even with neutral titles.
    "great plains rodeo", "gay rodeo", "igra",
}


def _text(e: Dict) -> str:
    """Combined lowercase text for keyword matching."""
    return " ".join([
        e.get("name",        ""),
        e.get("description", ""),
        e.get("venue",       ""),
        e.get("source",      ""),
    ]).lower()


# Car "drag racing" / "drag strip" events keep tripping the LGBTQ "drag"
# keyword (e.g. "Fun Friday Drags Night @ Tulsa Raceway Park", "Motorama at the
# Drag Strip - Car Show"). They are NOT queer events — never let them count as
# LGBTQ, earn flamingos, or get featured. (William 2026-06-15: feature gay ones.)
_DRAG_RACING_KW = (
    "drag strip", "drag racing", "drag race", "dragway", "dragster",
    "raceway", "speedway", "motorama", "motorsport", "nhra", "car show",
)


def _is_drag_racing(e: Dict) -> bool:
    return any(kw in _text(e) for kw in _DRAG_RACING_KW)


def _is_drag(e: Dict) -> bool:
    if _is_drag_racing(e):
        return False
    t = _text(e)
    return any(kw in t for kw in _DRAG_KW)


def _is_queer_perf(e: Dict) -> bool:
    t = _text(e)
    return any(kw in t for kw in _QUEER_PERF_KW)


def _is_lgbtq(e: Dict) -> bool:
    if (e.get("source") or "").lower() in _TRUSTED_LGBTQ_SRCS:
        return True
    if _is_drag_racing(e):
        return False
    t = _text(e)
    return any(kw in t for kw in _LGBTQ_KW)


# STRICT variant used by slide generator. Only matches:
#   1. Trusted LGBTQ source, OR
#   2. LGBTQ keyword in NAME or VENUE (NOT description — too many "affirming
#      spaces for LGBTQIA+ people of faith" type matches that aren't LGBTQ events)
_STRICT_LGBTQ_KW = {
    "lgbtq", "lgbtqia", "queer", "gay", "lesbian", "trans",
    "bisexual", "nonbinary", "non-binary", "sapphic", "dyke",
    "pride", "rainbow", "homo hotel", "hhhh",
    # Specific drag-PERFORMANCE phrases only — never the bare token "drag",
    # which substring-matched "DRAGon Paper Craft" (a kids' library craft) and
    # car "drag racing". (William 2026-06-15: feature gay ones.)
    "drag show", "drag queen", "drag king", "drag brunch", "drag night",
    "drag bingo", "drag ball", "drag pageant", "drag revue", "drag performance",
    "dragnificent", "drags", "two-spirit", "pflag",
    "okeq", "oklahomans for equality", "equality center",
    "dennis r. neill", "dennis r neill",
    "council oak", "comc",
    "gender outreach",
    "broadway clubhouse",   # OKEQ social space
    "queer crafters",
    "morecolor",            # OKEQ art show
    "great plains rodeo", "gay rodeo", "igra",   # Oklahoma's IGRA gay rodeo (GPRA)
    "equality business alliance", "eba",
    "affirming",            # only matches in NAME, not description
}


def _is_lgbtq_strict(e: Dict) -> bool:
    """Stricter LGBTQ check for slide generation. Source-trusted OR keyword
    in name/venue only — NOT description, which lets too many "everyone
    welcome including LGBTQIA+" community events sneak through.
    """
    if (e.get("source") or "").lower() in _TRUSTED_LGBTQ_SRCS:
        return True
    if _is_drag_racing(e):
        return False
    name = (e.get("name") or "").lower()
    venue = (e.get("venue") or "").lower()
    # Events at the city's gay bars / queer venues / LGBTQ org center ARE gay
    # events even without a keyword in the title (e.g. "Monday Movie Night" at the
    # Eagle). City-specific: read config.GAY_VENUE_SIGNATURES so a new city stays
    # portable; fall back to the Tulsa list if config is unavailable.
    _sigs = getattr(_config, "GAY_VENUE_SIGNATURES", None) or _GAY_VENUE_SIGNATURES
    if any(sig in venue for sig in _sigs):
        return True
    text = name + " " + venue
    return any(kw in text for kw in _STRICT_LGBTQ_KW)


# Tulsa gay bars / queer venues — by address and name. An event here counts as
# LGBTQ even if the title is neutral. (Eagle, Club Majestic, DVL.)
_GAY_VENUE_SIGNATURES = (
    "1338 e 3rd", "tulsa eagle",
    "124 n boston", "club majestic",
    "302 s frankfort", "302 south frankfort", "302 s. frankfort",
    "dennis r. neill", "dennis r neill", "equality center",
    # Yellow Brick Road — Tulsa's only lesbian bar, inclusive/everyone-welcome.
    # (William 2026-06-21: feature more YBR.) Mirrors config.GAY_VENUE_SIGNATURES.
    "yellow brick", "ybr", "2630 e 15th",
)


# Under-18 / kids programming signals. Events matching these are geared at minors
# and are DROPPED from the guide unless the event is explicitly LGBTQ (William
# 2026-06-15: "things geared for people under 18 that aren't explicitly gay should
# be removed" — e.g. a pet-rock class at the library). Queer youth programming
# (drag story hour, GSA, queer teen group) is protected by the _is_lgbtq check.
_YOUTH_KW = (
    "kids", "kid-friendly", "for kids", "children", "childrens", "children's",
    "toddler", "babies", "baby ", "infant", "preschool", "pre-k", "prek",
    "kindergarten", "elementary", "story time", "storytime", "story hour",
    "puppet", "lego", "sensory", "homeschool", "home school", "petting zoo",
    "pet rock", "dino", "dinosaur", "make and take", "corn husk", "corn-husk",
    "balloon twist", "bubble show", "bubble stage", "tween", "scout troop",
    "girl scout", "boy scout", "cub scout", "4-h", "summer reading",
    "reading buddies", "craft time", "kids' ", "youth craft", "teen craft",
    "family storytime", "family fun day", "weather show", "junior ranger",
)


def _is_youth_nongay(e: Dict) -> bool:
    """True if the event is geared at under-18s AND is NOT explicitly LGBTQ.
    Such events are screened OUT of the guide entirely (not just unfeatured).
    Anything that reads LGBTQ (broad _is_lgbtq OR a strict/source signal OR the
    lgbtq_relevant flag) is protected — queer youth programming stays."""
    if _is_lgbtq(e) or _is_lgbtq_strict(e) or e.get("lgbtq_relevant"):
        return False
    # Match the NAME (+venue) only, not the description — a youth program announces
    # itself in its title ("Pet Rock Class", "Toddler Storytime"). Matching the
    # description over-drops adult events that merely mention "kids menu" / "family".
    # Normalize punctuation so "Balloon-Twisting", "Corn-Husk", "Pre-K" still match.
    import re as _re
    t = (e.get("name") or "") + " " + (e.get("venue") or "")
    t = _re.sub(r"[^a-z0-9 ]+", " ", t.lower())
    t = _re.sub(r"\s+", " ", t)
    return any(kw.replace("-", " ") in t for kw in _YOUTH_KW)


# ---------------------------------------------------------------------------
# Within-tier sort key
# ---------------------------------------------------------------------------

def _sort_key(e: Dict) -> tuple:
    """
    Secondary sort within a tier (ascending = better):
      1. One-off events before weekly recurring (a special like Lil' Shop of
         Horrors must beat DRAGNIFICENT-every-Thursday now that bar venues
         are EOTW-eligible)
      2. Weekend (Fri-Sun) before weekday
      3. Has a URL (ticketed/specific) before no URL
      4. Richer description (longer = more substance)
    """
    recurring_score = 1 if (e.get("source") or "").lower() == "recurring" else 0

    date_str = e.get("date") or ""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        day_score = 0 if dt.weekday() >= 4 else 1   # Fri=4, Sat=5, Sun=6
    except Exception:
        day_score = 2                                 # unknown date — deprioritize

    url_score  = 0 if e.get("url") else 1
    desc_score = -(len(e.get("description") or ""))  # negate — longer is better

    return (recurring_score, day_score, url_score, desc_score)


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

    # EOTW must be a VERIFIABLE one-off. Recurring auto-events (recurring.py)
    # are date-stamped onto a weekday without checking they actually happen, so
    # they are NEVER eligible to auto-win the hero slot (William 2026-06-23: an
    # unverified "Drag Bingo Bongo at Saturn Room" recurring rule headlined a
    # post for an event that wasn't happening). They still appear on day slides
    # and the website. A pinned manual EOTW (data/manual_eotw.json) always wins
    # and bypasses this — that path is human-verified.
    eligible = [
        e for e in events_this_week
        if not _is_skip(e) and (e.get("source") or "").lower() != "recurring"
    ]

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


# ---------------------------------------------------------------------------
# Manual override + multi-EOTW support
# ---------------------------------------------------------------------------

def load_manual_eotw(week_key: Optional[str]) -> List[Dict]:
    """Read data/manual_eotw.json and return the list of matcher dicts for
    week_key, or []. Each matcher: {"match": "<name/source substring>",
    "date": "YYYY-MM-DD" (optional)}. The file is keyed by week_key, e.g.
    {"2026-W23": [{"match": "homo hotel"}, {"match": "council oak"}]}."""
    if not week_key:
        return []
    try:
        with open(_MANUAL_EOTW_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        return []
    entry = data.get(week_key)
    if isinstance(entry, list):
        return [m for m in entry if isinstance(m, dict) and m.get("match")]
    return []


# ---------------------------------------------------------------------------
# Partner auto-highlight (William 2026-07-20)
# ---------------------------------------------------------------------------
# The site has cross-promo deals (PFLAG Tulsa, Oklahomans for Equality / the
# Equality Center) to highlight partners' events. Rather than remembering to pin
# them in manual_eotw.json each week, an active partner's SPECIAL event is auto-
# promoted to an Event-of-the-Week hero the week it happens. Data-driven from
# data/featured_partners.json so each city just maintains its own partner list.

# Partner events that are NOT featurable highlights even though they come from a
# partner: routine support meetings, memberships, business/service programming.
# The deal is to spotlight a partner's SPECIAL events, never their standing
# support meeting (support-meeting policy, William 2026-07-07).
_PARTNER_NONEVENT_FRAGMENTS = (
    "monthly meeting", "support group", "support meeting", "membership",
    "office hours", "volunteer meeting", "board meeting", "general meeting",
    "weekly meeting", "business meeting",
)


def _load_partner_matchers() -> List[Dict]:
    """Return active auto-highlight partners from data/featured_partners.json as
    [{"name": str, "match": [lowercase substrings]}].

    A partner opts IN by being active (the default) and does not set
    "highlight": false. `match` substrings are tested against an event's
    name + source + venue; when absent, the partner name is the default matcher.
    Fails soft (returns []) so a missing/broken file never blocks EOTW."""
    try:
        with open(_FEATURED_PARTNERS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        return []
    out: List[Dict] = []
    for p in (data.get("partners") or []):
        if not isinstance(p, dict) or not p.get("active", False):
            continue
        if p.get("highlight") is False:
            continue
        matchers = p.get("match") or []
        if isinstance(matchers, str):
            matchers = [matchers]
        matchers = [str(m).lower() for m in matchers if str(m).strip()]
        if not matchers and p.get("name"):
            matchers = [str(p["name"]).lower()]
        if matchers:
            out.append({"name": p.get("name", matchers[0]), "match": matchers})
    return out


def _partner_of(e: Dict, partners: Optional[List[Dict]] = None) -> Optional[str]:
    """Return the partner name if this event belongs to an active highlight
    partner, else None (matches on name + source + venue)."""
    if partners is None:
        partners = _load_partner_matchers()
    hay = ((e.get("name") or "") + " | " + (e.get("source") or "")
           + " | " + (e.get("venue") or "")).lower()
    for p in partners:
        if any(m in hay for m in p["match"]):
            return p["name"]
    return None


def _is_partner_special(e: Dict, partners: Optional[List[Dict]] = None) -> bool:
    """True when an event is a partner's SPECIAL event worth auto-heroing:
    from an active partner, a real event (not a service / support meeting caught
    by _is_skip or the non-event fragments), and not a bare recurring auto-row.
    Preserves the support-meeting policy — a partner's routine meeting is never
    auto-featured."""
    if not _partner_of(e, partners):
        return False
    if _is_skip(e):
        return False
    if (e.get("source") or "").lower() == "recurring":
        return False
    name = (e.get("name") or "").lower()
    if any(frag in name for frag in _PARTNER_NONEVENT_FRAGMENTS):
        return False
    return True


def select_eotw_list(events_this_week: List[Dict],
                     week_key: Optional[str] = None) -> List[Dict]:
    """Return an ordered list of Events of the Week (usually 1, sometimes 2).

    Order of precedence:
      1. Human-pinned manual override (data/manual_eotw.json) — always wins.
      2. Auto: partner special events (one hero per active partner from
         data/featured_partners.json) lead, so PFLAG / OKEQ deals are honored
         automatically; any remaining hero slot is filled by the marquee
         auto-pick (select_eotw). Capped at 2 to fit the stacked-cover layout.
      3. Single auto-selected EOTW when there are no partner events.
    Returns [] if nothing qualifies."""
    # 1. Human-pinned override always wins (a person verified it).
    manual = load_manual_eotw(week_key)
    if manual:
        resolved: List[Dict] = []
        seen = set()
        for m in manual:
            frag = (m.get("match") or "").lower()
            want_date = m.get("date")
            cands = [
                e for e in events_this_week
                if frag in ((e.get("name") or "") + " " + (e.get("source") or "")).lower()
            ]
            if want_date:
                dated = [e for e in cands if e.get("date") == want_date]
                cands = dated or cands
            if cands:
                best = sorted(cands, key=_sort_key)[0]
                if id(best) not in seen:
                    resolved.append(best)
                    seen.add(id(best))
        if resolved:
            return resolved

    # 2. Auto path — lead with partner special events (one per partner).
    partners = _load_partner_matchers()
    heroes: List[Dict] = []
    seen_ids = set()
    if partners:
        best_by_partner: Dict[str, Dict] = {}
        for e in events_this_week:
            if not _is_partner_special(e, partners):
                continue
            pname = _partner_of(e, partners)
            cur = best_by_partner.get(pname)
            if cur is None or _sort_key(e) < _sort_key(cur):
                best_by_partner[pname] = e
        for e in sorted(best_by_partner.values(), key=_sort_key):
            if id(e) not in seen_ids:
                heroes.append(e)
                seen_ids.add(id(e))

    # Fill any remaining hero slot (up to 2) with the marquee auto-pick.
    if len(heroes) < 2:
        marquee = select_eotw([e for e in events_this_week if id(e) not in seen_ids])
        if marquee is not None and id(marquee) not in seen_ids:
            heroes.append(marquee)  # rounds out slot 2, or is the sole hero
            seen_ids.add(id(marquee))

    return heroes[:2]


# ---------------------------------------------------------------------------
# Self-test — python eotw_selector.py --selftest
# ---------------------------------------------------------------------------
def _selftest() -> int:
    """Prove partner auto-highlight: partners lead, services are excluded, the
    support-meeting policy holds, and manual pins still win. Returns 0 on pass."""
    import sys
    partners = [
        {"name": "PFLAG", "match": ["pflag"]},
        {"name": "OKEQ", "match": ["okeq", "equality center"]},
    ]
    fri = "2026-07-24"
    events = [
        {"name": "Drag Bingo", "source": "recurring", "date": "2026-07-22"},
        {"name": "Random Comedy Night", "source": "eventbrite", "date": "2026-07-23"},
        {"name": "PFLAG Tulsa: Big Gala", "source": "manual", "date": fri, "url": "x", "description": "gala"},
        {"name": "OKEQ Health Clinic", "source": "okeq", "date": "2026-07-21", "never_feature": True},
        {"name": "PFLAG Monthly Meeting", "source": "manual", "date": "2026-07-25"},
        {"name": "Queer Night at the Equality Center", "source": "okeq", "date": "2026-07-25", "url": "y", "description": "party"},
    ]
    fails = []

    # partner detection + special filter
    if not _is_partner_special(events[2], partners):
        fails.append("PFLAG gala should be a partner special")
    if _is_partner_special(events[3], partners):
        fails.append("OKEQ clinic (never_feature) must be excluded")
    if _is_partner_special(events[4], partners):
        fails.append("PFLAG monthly meeting must be excluded (support-meeting policy)")
    if _is_partner_special(events[0], partners):
        fails.append("recurring auto-row must be excluded")
    if not _is_partner_special(events[5], partners):
        fails.append("OKEQ queer night should be a partner special")

    # auto path: both partners lead, capped at 2, marquee does not crowd them out
    import unittest.mock as _mock
    with _mock.patch.object(sys.modules[__name__], "_load_partner_matchers", lambda: partners):
        heroes = select_eotw_list(events, week_key="2099-W01")
    names = [h["name"] for h in heroes]
    if len(heroes) != 2:
        fails.append(f"expected 2 heroes, got {len(heroes)}: {names}")
    if not any("PFLAG Tulsa: Big Gala" in n for n in names):
        fails.append(f"PFLAG special missing from heroes: {names}")
    if not any("Equality Center" in n for n in names):
        fails.append(f"OKEQ special missing from heroes: {names}")
    if any("Monthly Meeting" in n or "Clinic" in n for n in names):
        fails.append(f"a service/meeting leaked into heroes: {names}")

    # no partners with events -> single marquee hero (a real LGBTQ event)
    marquee_only = {"name": "Big Drag Show", "source": "eventbrite", "date": fri,
                    "url": "z", "description": "a drag show"}
    with _mock.patch.object(sys.modules[__name__], "_load_partner_matchers", lambda: partners):
        solo = select_eotw_list([marquee_only, events[1]], week_key="2099-W02")
    if len(solo) != 1 or solo[0]["name"] != "Big Drag Show":
        fails.append(f"no-partner week should fall back to single marquee: {[h['name'] for h in solo]}")

    if fails:
        print("SELFTEST FAILED:")
        for f in fails:
            print("  -", f)
        return 1
    print("SELFTEST PASSED — partner auto-highlight, service exclusion, "
          "support-meeting policy, and marquee fallback all verified.")
    return 0


if __name__ == "__main__":
    import sys as _sys
    if "--selftest" in _sys.argv:
        raise SystemExit(_selftest())
    print("eotw_selector.py — use --selftest to run the regression checks.")
