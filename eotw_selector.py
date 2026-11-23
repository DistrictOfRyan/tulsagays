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
import re
import re as _re
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
    "support circle",      # W40 replay: "Community Care Providers Support Circle" (OKEQ)
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
    # LGBTQ ORGANISATIONS' OWN INSTAGRAM FEEDS (added 2026-09-07). These are the
    # accounts of queer venues and queer orgs, so anything they post is a gay
    # event by definition — the venue signature check below cannot see it when
    # the event is held somewhere else. That is not hypothetical: W37's
    # "HotMess Kickball Fall 2026 Free Open Play" is the Tulsa LGBTQ rec league,
    # but it is played at McClure Park Softball Field, so name and venue carry no
    # queer token and it scored strict_lgbtq=False. Wednesday then filled its
    # three slides with a comedy club, a Philbrook kids' garden class and a
    # gallery talk while a real gay event sat unfeatured — exactly what William
    # meant by "there's nothing really gay on them".
    # DELIBERATELY NOT trusted here, even though config.LGBTQ_SOURCES lists them:
    # facebook_events, manual, recurring, community_groups, circle_cinema,
    # philbrook_museum, aa_meetings. Those are venues-that-host or catch-all
    # feeds; trusting them would make almost every event "gay" and empty this
    # check of meaning.
    "hotmess_sports",     # HotMess Sports Tulsa — LGBTQ rec sports league
    "club_majestic_ig",   # Club Majestic — LGBTQ nightclub
    "dvl_ig",             # DVL Club & Lounge — woman-owned LGBTQ bar
    "tulsa_eagle_ig",     # Tulsa Eagle — levi/leather LGBTQ bar
    "ybr_ig",             # Yellow Brick Road — Tulsa's lesbian bar
    "pflag_ig",           # PFLAG Tulsa
    "pflag_tulsa",
    "homo_hotel",         # HHHH — William's own monthly LGBTQ mixer
    "council_oak",        # Council Oak Men's Chorale
    "circles_lgbtq",
    # From William's listing map (2026-11-11): queer accounts added to the IG scraper.
    "tulsa_house_of_drag",  # @tulsahouseofdrag, drag shows across venues
    "osq_and_a",            # @osq_and_a, queer student group
    # qlist (added 2026-09-12). scraper/qlist.py: "LGBTQ+ event aggregator for
    # Tulsa" — unlike facebook_events/manual/recurring above, qlist.app only
    # ever lists queer events, so it belongs with the trusted orgs, not the
    # catch-all feeds. config.LGBTQ_SOURCES already tags it "always-LGBTQ" and
    # weekend_carousel.py's _QUEER_SOURCES already trusts it for headline sort;
    # this file had simply never picked it up. Gap found on W37's "Sunday
    # Showcase" (qlist, no venue, description literally "Sunday drag and talent
    # showcase") scoring strict_lgbtq=False and rendering "Mostly Straight" on
    # the Saturday-preview carousel next to lower-novelty events correctly
    # tagged Super Gay / Very LGBTQIA+.
    "qlist",
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
    if any(kw in t for kw in _QUEER_PERF_KW):
        return True
    # A revue or burlesque at a gay venue / from a queer org is a queer
    # performance even when the title carries no queer keyword. W48's "RED
    # RIBBON REVUE UNDERWEAR AUCTION W/PORSCHE LYNN" at the Eagle matched no
    # tier at all, so the week's best one-off was never a candidate. The bare
    # word stays out of _QUEER_PERF_KW because "Holiday Revue" at a church is
    # not a queer night.
    name = (e.get("name") or "").lower()
    if re.search(r"\b(revue|burlesque)\b", name) and _is_lgbtq_strict(e):
        return True
    return False


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
    "dragnificent", "drags", "two-spirit", "two spirit", "pflag",
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


# WORD-BOUNDARY MATCHING (added 2026-09-07). This set was matched with a plain
# `kw in text` substring test, and the short acronyms in it silently fired inside
# ordinary words. The live example: "igra" (Oklahoma's IGRA gay rodeo) matched
# inside "imm-IGRA-tion", so "Immigration Updates – Town Hall Series" at the
# University of Tulsa scored strict_lgbtq=True and took a featured slide on
# W37 Tuesday. William: "the immigration updates town hall series is not an event
# that I would go to. It's not a fun thing. I'm not sure why that's on there."
# "eba" (Equality Business Alliance) would do the same inside "debate"/"rebate",
# and "trans" inside "transportation"/"transit"/"translation".
#
# This is a KNOWN, ALREADY-SOLVED bug class in this repo: scraper/relevance.py
# grew compile_lgbtq_keywords() with word boundaries on 2026-07-07 after "bi"
# matched inside "bingo". That fix was applied to the six scraper modules and
# never to this file. Same medicine here.
#
# Multi-word phrases keep plain substring semantics (they cannot false-fire);
# single tokens get \b boundaries. Hyphenated forms like "non-binary" are matched
# with the hyphen treated as part of the token.
_STRICT_SINGLE = {k for k in _STRICT_LGBTQ_KW if " " not in k}
_STRICT_PHRASE = {k for k in _STRICT_LGBTQ_KW if " " in k}
_STRICT_RE = _re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(_re.escape(k) for k in sorted(_STRICT_SINGLE, key=len, reverse=True))
    + r")(?![a-z0-9])"
)


# "Pride" that is not LGBTQ Pride. W40 (2026-09-28): "Tulsa Pagan Pride Day", a
# Pagan community festival, scored 5 flamingos / "Super Gay" on the Saturday
# slide and ranked as a gay event. Remove these phrases before keyword matching.
NON_LGBTQ_PRIDE_PHRASES = (
    "pagan pride", "pride and prejudice", "pride & prejudice",
)


def strip_non_lgbtq_pride(text: str) -> str:
    for p in NON_LGBTQ_PRIDE_PHRASES:
        text = text.replace(p, " ")
    return text


def _strict_kw_hit(text: str) -> bool:
    """True if text carries a strict LGBTQ keyword as a WORD, not a substring."""
    text = strip_non_lgbtq_pride(text)
    if any(p in text for p in _STRICT_PHRASE):
        return True
    return bool(_STRICT_RE.search(text))


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
    return _strict_kw_hit(text)


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
    # Philbrook's "Little Garden Explorers" is drop-in play for children under 5;
    # W40 put it on the Wednesday slide.
    "garden explorers", "little explorers",
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
# Freshness (William 2026-11-23)
# ---------------------------------------------------------------------------
# William: "the event of the week, unless it's Homo Hotel Happy Hour, should
# rarely be like [DRAGNIFICENT], which is every [week] ... no one's going to look
# at the site if you're just saying the same things over and over. You're
# supposed to be introducing new things."
#
# What shipped before this: 15 of 17 weeks (W31-W47) put an Equality Center
# event in the hero slot (the OKEQ partner auto-highlight matched the venue, so
# any OKEQ programme led), Rainbow Harvest won 3 times, Queer Crafters Club
# twice, and the second slot went to DRAGNIFICENT 6 times, the Elote Drag Brunch
# 4 times and Drag Bingo 3 times. The tier ladder never asked "have we said this
# before?", and its only recurring guard was source == "recurring", which weekly
# shows from community_groups / qlist / rendered_sites never carry.
#
# So every candidate below Homo Hotel Happy Hour and Council Oak gets a
# freshness BUCKET, and the bucket ranks BEFORE the tier:
#   0  brand new: its series is in none of the last 4 weeks' listings
#   1  fresh: seen before, but not weekly and not a recent hero
#   2  its VENUE held the hero slot in the last 3 weeks
#   3  its SERIES held the hero slot in the last 12 weeks
#   4  STANDING: weekly programming (in 2+ of the last 4 weeks' listings, a
#      recurring.py row, or a weekly name like "Friday Drag Shows")
# Buckets 0 and 1 rank together (tier decides between them, brand-new breaks
# ties), so a fresh drag show still beats a fresh keyword match. A venue used
# 2-3 weeks ago is only a tie-breaker; LAST week's venue demotes (_fresh_rank
# has the exact order). Annual landmarks (Pride festivals, Trans Day of
# Remembrance, World AIDS Day) are exempt and rank first. Nothing is ever
# removed: when the week has nothing fresh, the stalest candidate still wins, so
# the cover is never empty where it was not before. Manual pins
# (data/manual_eotw.json) still always win. HHHH and Council Oak are exempt.
#
# Replay proof: python tools/eotw_replay.py --check --from 2026-W33 --to 2026-W48

SERIES_COOLDOWN_WEEKS = 12
VENUE_COOLDOWN_WEEKS = 3
STANDING_LOOKBACK_WEEKS = 4
STANDING_MIN_WEEKS = 2
# A partner event auto-leads only when it is a true one-off: its series is in
# none of the last 8 weeks' listings. Monthly programming (Rainbow Harvest,
# Queer Crafters Club, the TLC and Prime Timers meetings) is not a "special".
PARTNER_ONEOFF_LOOKBACK_WEEKS = 8

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

_MONTH_WORDS = {
    "jan", "january", "feb", "february", "mar", "march", "apr", "april", "may",
    "jun", "june", "jul", "july", "aug", "august", "sep", "sept", "september",
    "oct", "october", "nov", "november", "dec", "december",
}
_WEEKDAY_WORDS = {
    "mon", "monday", "mondays", "tue", "tues", "tuesday", "tuesdays", "wed",
    "wednesday", "wednesdays", "thu", "thur", "thurs", "thursday", "thursdays",
    "fri", "friday", "fridays", "sat", "saturday", "saturdays", "sun", "sunday",
    "sundays",
}
# Words that never identify WHICH event something is. A name made only of these
# ("Drag Brunch", "Karaoke Night") is keyed on its venue instead.
_SERIES_GENERIC = {
    "the", "a", "an", "and", "or", "of", "for", "in", "on", "to", "by", "at",
    "with", "w", "ft", "feat", "featuring", "presents", "presented", "present",
    "hosted", "host", "hosts", "tulsa", "ok", "okla", "oklahoma", "show", "shows",
    "night", "nights", "party", "parties", "event", "events", "live", "music",
    "free", "annual", "edition", "special", "specials", "tour", "drag", "brunch",
    "bingo", "karaoke", "happy", "hour", "hours", "dinner", "club", "bar", "pub",
    "lounge", "queer", "gay", "lgbtq", "lgbtqia", "lgbt", "pride", "vol", "part",
    "dj", "open", "mic", "celebration", "community", "meeting", "monthly",
    "weekly", "series", "new", "our", "your", "you", "all", "its", "it",
}
_SERIES_SPLIT_RE = re.compile(
    r"\s+[:|@–—-]\s+|:\s|\(|\s+at\s+|\s+w/|\s+with\s+"
    r"|\s+ft\.?\s+|\s+feat\.?\s+|\s+featuring\s+|\s+presented\s+by\s+|\s+hosted\s+by\s+",
    re.I,
)
_ORDINAL_RE = re.compile(r"^\d+(st|nd|rd|th)?$")

# Weekly programming that names itself as such.
_STANDING_NAME_RE = re.compile(
    r"\b(every|weekly|nightly|each\s+week)\b"
    r"|\b(mondays|tuesdays|wednesdays|thursdays|fridays|saturdays|sundays)\b"
    r"|\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+nights\b"
    r"|\b(taco\s+tuesday|thirsty\s+thursday|wine\s+wednesday)\b"
    r"|\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+"
    r"(night\s+)?(karaoke|movie\s+night|drag\s+shows?|trivia|bingo|open\s+mic"
    r"|bar\s+specials?|specials?|happy\s+hour|showcase|tea\s+party|lunch|brunch)\b",
    re.I,
)

# Same building under its different spellings. Anything not listed keys on the
# first comma part of the venue line.
_VENUE_ALIASES = (
    ("equality-center", ("equality center", "dennis r. neill", "dennis r neill",
                         "621 e 4th", "621 e. 4th", "lynn riggs theatre")),
    ("tulsa-eagle", ("tulsa eagle", "1338 e 3rd", "1338 e. 3rd")),
    ("club-majestic", ("club majestic", "majestic tulsa", "124 n boston", "124 n. boston")),
    ("ybr", ("yellow brick", "2630 e 15th")),
    ("elote", ("elote", "514 s boston", "514 s. boston")),
    ("dvl", ("dvl", "302 s frankfort", "302 south frankfort", "302 s. frankfort")),
)
_YBR_RE = re.compile(r"(?<![a-z0-9])ybr(?![a-z0-9])")
# Words of the known buildings' names. They say WHERE, never WHICH event, so
# they never make a series distinctive: "Elote Drag Brunch" and "Drag Brunch :
# oct. 10th - scream queens" at Elote are one series.
_ALIAS_TOKENS = {t for _k, _al in _VENUE_ALIASES for a in _al if not a[:1].isdigit()
                 for t in re.findall(r"[a-z]+", a) if len(t) > 2} | {"ybr"}

# Annual landmarks: once-a-year community moments that must headline their
# week no matter what held the slot before. The replay caught it: with a plain
# venue cooldown, W42's "Tulsa Pride 2026" (at the Equality Center, three weeks
# after Broadway Clubhouse there) lost the hero slot to a drag bingo. Deliberately
# narrow; runner._FLAGSHIP_KEYWORDS ("drag brunch", "festival", "ball") is a
# scrape-retention list and far too broad to exempt anything here.
_LANDMARK_RE = re.compile(
    r"\bpride\s*(\d{4}|fest\w*|parade|picnic|march|rally|weekend|kickoff)\b"
    r"|\b\w+\s+pride\s*$|^\s*pride\b"
    r"|\btrans\s+day\s+of\s+(remembrance|visibility)\b|\btdor\b"
    r"|\bworld\s+aids\s+day\b|\baids\s+walk\b|\bcoming\s+out\s+day\b",
    re.I,
)


def _is_landmark(e: Dict) -> bool:
    name = strip_non_lgbtq_pride(_ascii_lower(e.get("name") or ""))
    base = re.split(r"\s+at\s+|:\s|\s+[-|]\s+", name, maxsplit=1)[0]
    return bool(_LANDMARK_RE.search(name) or _LANDMARK_RE.search(base))


def _ascii_lower(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _venue_alias(text: str) -> Optional[str]:
    """The known building named anywhere in `text`, or None."""
    v = _ascii_lower(text)
    for key, aliases in _VENUE_ALIASES:
        if any(a in v for a in aliases):
            return key
    if _YBR_RE.search(v):
        return "ybr"
    return None


def _venue_key(venue: str) -> Optional[str]:
    """Canonical building key for a venue line, or None when it says nothing."""
    v = _ascii_lower(venue)
    if not v.strip():
        return None
    alias = _venue_alias(v)
    if alias:
        return alias
    first = v.split(",")[0]
    toks = [t for t in re.findall(r"[a-z0-9]+", first) if t not in {"the", "tulsa", "ok"}]
    if not toks or _VENUE_NOT_A_PLACE_RE.match(first.strip()):
        return None
    return " ".join(toks)


def _series_key(e: Dict) -> tuple:
    """(distinctive tokens, base words, venue key) for an event's SERIES.

    "Drag Brunch : nov. 11th - gone cuntry" and "Drag Brunch : jul. 11th -
    stars, stripes & sequins" at Elote are one series; "Hocus Pocus Drag Brunch"
    is another; "DRAGNIFICENT! Drag Show" and "DRAGNIFICENT! at Club Majestic"
    are one."""
    name = _ascii_lower(e.get("name") or "")
    base = _SERIES_SPLIT_RE.split(name, maxsplit=1)[0]
    words = [t for t in re.findall(r"[a-z0-9]+", base)
             if not _ORDINAL_RE.match(t) and t not in _MONTH_WORDS
             and t not in _WEEKDAY_WORDS]
    words = [t for t in words if t not in _ALIAS_TOKENS]
    if words and words[0] == "the":
        words = words[1:]
    distinct = frozenset(t for t in words if t not in _SERIES_GENERIC and len(t) > 1)
    # A known building named in the title counts as the venue: "Drag Brunch
    # Presented by Elote" arrived with venue "Bryson Day Travieso" (the Facebook
    # host's name) and escaped the Elote Drag Brunch series in the replay.
    venue = (_venue_alias(e.get("venue") or "") or _venue_alias(name)
             or _venue_key(e.get("venue") or ""))
    return (distinct, " ".join(words), venue)


def _same_series(ka: tuple, kb: tuple) -> bool:
    ta, ba, va = ka
    tb, bb, vb = kb
    if ta and tb:
        inter = ta & tb
        if not inter:
            return False
        if len(inter) / len(ta | tb) >= 0.5:
            return True
        small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
        return small <= big and len(big) <= 3
    if not ta and not tb:
        # Generic-only names ("Drag Brunch") are one series per building.
        return bool(ba) and ba == bb and va is not None and va == vb
    return False


def _week_monday(week_key: str):
    from datetime import date as _d
    y, w = week_key.split("-W")
    return _d.fromisocalendar(int(y), int(w), 1)


def _week_key_of(d) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _shift_week(week_key: str, weeks: int) -> str:
    from datetime import timedelta as _td
    return _week_key_of(_week_monday(week_key) + _td(weeks=weeks))


def _infer_week_key(events: List[Dict]) -> Optional[str]:
    """The ISO week most of these events fall in (callers like post_weekly.py
    and auto_fix_deck.py hand select_eotw a week of events but no week key)."""
    from collections import Counter
    c = Counter()
    for e in events or []:
        try:
            c[_week_key_of(datetime.strptime(e.get("date") or "", "%Y-%m-%d").date())] += 1
        except Exception:
            continue
    return c.most_common(1)[0][0] if c else None


def _has_date(e: Dict) -> bool:
    try:
        datetime.strptime(e.get("date") or "", "%Y-%m-%d")
        return True
    except Exception:
        return False


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _in_week(e: Dict, week_key: str) -> bool:
    try:
        d = datetime.strptime(e.get("date") or "", "%Y-%m-%d").date()
    except Exception:
        return False
    return _week_key_of(d) == week_key


class Freshness:
    """How new each candidate is relative to what the site already said.

    eotw_history: [(weeks_ago, event)], what held the hero slot before.
    prior_events: [(weeks_ago, event)], the listings of the previous weeks."""

    def __init__(self, week_key: Optional[str] = None, eotw_history=None, prior_events=None):
        self.week_key = week_key
        hist = [(int(wa), e) for wa, e in (eotw_history or []) if isinstance(e, dict)]
        # Third field: does NOT count toward the venue cooldown. HHHH rotates
        # hotels and a landmark (Tulsa Pride) is about the day, not the building.
        self._hist = [(wa, _series_key(e), _is_hh(e) or _is_landmark(e)) for wa, e in hist]
        self._prior = [(int(wa), _series_key(e)) for wa, e in (prior_events or [])
                       if isinstance(e, dict)]

    @classmethod
    def for_week(cls, week_key: Optional[str], data_dir: str = _DATA_DIR,
                 history_override: Optional[Dict[str, List[Dict]]] = None) -> "Freshness":
        """Load the last SERIES_COOLDOWN_WEEKS heroes (data/posts/<wk>/
        slide_manifest.json "eotw") and the last STANDING_LOOKBACK_WEEKS weeks
        of listings (data/events/<wk>_all.json, rows dated inside that week).
        history_override {week_key: [events]} replaces a week's shipped heroes
        (tools/eotw_replay.py chains its own picks through it). Fails soft."""
        if not week_key:
            return cls(None)
        try:
            _week_monday(week_key)
        except Exception:
            return cls(None)
        history, prior = [], []
        for k in range(1, SERIES_COOLDOWN_WEEKS + 1):
            wk = _shift_week(week_key, -k)
            if history_override is not None and wk in history_override:
                heroes = history_override[wk] or []
            else:
                m = _load_json(os.path.join(data_dir, "posts", wk, "slide_manifest.json")) or {}
                heroes = m.get("eotw") or []
            history += [(k, e) for e in heroes if isinstance(e, dict)]
        for k in range(1, max(STANDING_LOOKBACK_WEEKS, PARTNER_ONEOFF_LOOKBACK_WEEKS) + 1):
            wk = _shift_week(week_key, -k)
            rows = _load_json(os.path.join(data_dir, "events", f"{wk}_all.json"))
            if isinstance(rows, dict):
                rows = rows.get("events") or []
            prior += [(k, e) for e in (rows or []) if isinstance(e, dict) and _in_week(e, wk)]
        return cls(week_key, history, prior)

    def info(self, e: Dict) -> Dict:
        key = _series_key(e)
        landmark = _is_landmark(e)
        exempt = _is_hh(e) or _is_council(e) or landmark
        weeks_seen_long = {wa for wa, k in self._prior if _same_series(key, k)}
        weeks_seen = {wa for wa in weeks_seen_long if wa <= STANDING_LOOKBACK_WEEKS}
        named_weekly = bool(_STANDING_NAME_RE.search(e.get("name") or ""))
        standing = ((e.get("source") or "").lower() == "recurring" or named_weekly
                    or len(weeks_seen) >= STANDING_MIN_WEEKS)
        series_hits = [wa for wa, k, hh in self._hist
                       if wa <= SERIES_COOLDOWN_WEEKS and _same_series(key, k)]
        vk = key[2]
        venue_hits = [wa for wa, k, hh in self._hist
                      if not hh and wa <= VENUE_COOLDOWN_WEEKS and vk and k[2] == vk]
        if exempt:
            bucket = 0
            why = "annual landmark" if landmark else "exempt (HHHH / Council Oak)"
        elif standing:
            bucket = 4
            why = ("weekly by name" if named_weekly else
                   "recurring.py row" if (e.get("source") or "").lower() == "recurring" else
                   f"listed in {len(weeks_seen)} of the last {STANDING_LOOKBACK_WEEKS} weeks")
        elif series_hits:
            bucket, why = 3, f"same series was the hero {min(series_hits)} week(s) ago"
        elif venue_hits:
            bucket, why = 2, f"{vk} held the hero slot {min(venue_hits)} week(s) ago"
        elif weeks_seen:
            bucket, why = 1, "fresh (listed before, not weekly, not a recent hero)"
        else:
            bucket, why = 0, f"fresh (not listed in the last {STANDING_LOOKBACK_WEEKS} weeks)"
        # stale: 0 fresh, 1 the building was LAST week's hero, 2 the series was
        # a hero in the last 12 weeks, 3 standing weekly programming. A building
        # used 2-3 weeks ago stays "fresh" and is only a tie-breaker inside a
        # band (see _fresh_rank): the Equality Center loses to a fresh event of
        # the same kind elsewhere, but a themed drag night at a venue used two
        # weeks ago still beats a Monday student mixer. Back-to-back weeks at one
        # building is the repetition readers notice first, so that one demotes.
        last_week = bucket == 2 and min(venue_hits) == 1
        stale = {0: 0, 1: 0, 2: 1 if last_week else 0, 3: 2, 4: 3}[bucket]
        return {"bucket": bucket, "group": {0: 0, 1: 0, 2: 1, 3: 2, 4: 3}[bucket],
                "stale": stale,
                "venue_cool": bucket == 2, "landmark": landmark,
                "oneoff": not weeks_seen_long,
                "seen_before": bool(weeks_seen), "reason": why}


# Word-bounded LGBTQ test for the hero picker's tier 5 (2026-11-23). The broad
# _is_lgbtq() above substring-matches _LGBTQ_KW, so "igra" fires inside
# "immIGRAtion": the freshness replay put "THE ALABAMA SOLUTION: SCREENING &
# COMMUNITY CONVERSATION" (a prison documentary) in W45's hero slot for exactly
# that reason. _is_lgbtq() keeps its behaviour for its other callers
# (content/generator.py, tools/final_deck_review.py); only EOTW uses this one.
_LGBTQ_WORD_RE = re.compile(
    r"(?<![a-z0-9])(lgbt\w*|queer\w*|gays?|lesbians?|trans(gender\w*|sexual\w*|fem\w*|masc\w*)?"
    r"|bisexual\w*|nonbinary|non-binary|pride|rainbow|homo|sapphic|two[- ]spirit"
    r"|drag\s+(queens?|kings?)|great\s+plains\s+rodeo|gay\s+rodeo|igra|gender\s+outreach|pflag)"
    r"(?![a-z0-9])"
)


def _is_lgbtq_word(e: Dict) -> bool:
    if (e.get("source") or "").lower() in _TRUSTED_LGBTQ_SRCS:
        return True
    if _is_drag_racing(e):
        return False
    return bool(_LGBTQ_WORD_RE.search(strip_non_lgbtq_pride(_text(e))))


def _eotw_tier(e: Dict) -> Optional[int]:
    """The tier ladder in one place (docstring at the top of this file)."""
    if _is_hh(e):
        return 0
    if _is_council(e):
        return 1
    if _is_drag(e):
        return 2
    if _is_queer_perf(e):
        return 3
    src = (e.get("source") or "").lower()
    if src in _TRUSTED_LGBTQ_SRCS:
        return 4 if e.get("url") else None
    # Tier 5 also counts events at the city's gay venues (2026-11-23): W48's
    # one-offs at the Eagle ("LEFTOVERS & LEGENDS RETRO PARTY") carried no
    # keyword, so the hero picker could not see them while the day slides did.
    if _is_lgbtq_word(e) or _is_lgbtq_strict(e):
        return 5
    return None


def _fresh_rank(e: Dict, tier: int, fresh) -> tuple:
    """Rank for tiers 2-5 (lower wins):
      stale    0 fresh, 1 building was last week's hero, 2 series was a hero
               in the last 12 weeks, 3 weekly
      band     -1 annual landmark, 0 a performance (drag / queer perf, tiers
               2-3), 1 everything else (trusted-source ticketed, keyword, venue)
      venue    1 when the building held the hero slot in the last 3 weeks
      tier     the old ladder
      seen     0 when not listed in the last 4 weeks (newest first)
      _sort_key the old within-tier order (one-off, weekend, URL, description)
    With fresh=False this is exactly the old tier ladder."""
    if not fresh:
        return (0, 0, 0, tier, 0, _sort_key(e))
    i = fresh.info(e)
    band = -1 if i["landmark"] else (0 if tier in (2, 3) else 1)
    return (i["stale"], band, 1 if i["venue_cool"] else 0, tier,
            1 if i["seen_before"] else 0, _sort_key(e))


_TODAY_OVERRIDE = None   # tests set a date here


def _already_over(e: Dict) -> int:
    """1 when the event is earlier in THIS week than today. The website banner
    is regenerated mid-week (the Wednesday last-minute refresh) with this same
    picker, and a hero that already happened is a dead banner. Only applies
    inside the current week, so Monday's deck and the replay of past weeks are
    unaffected."""
    today = _TODAY_OVERRIDE or datetime.now().date()
    try:
        d = datetime.strptime(e.get("date") or "", "%Y-%m-%d").date()
    except Exception:
        return 0
    return 1 if (d < today and _week_key_of(d) == _week_key_of(today)) else 0


def explain(e: Dict, fresh: Optional["Freshness"]) -> Dict:
    """Tier + freshness verdict for one event (tools/eotw_replay.py prints it)."""
    out = {"tier": _eotw_tier(e)}
    if fresh:
        out.update(fresh.info(e))
    return out


# ---------------------------------------------------------------------------
# Main selector
# ---------------------------------------------------------------------------

def _has_venue(e: dict) -> bool:
    """True when the event knows where it is.

    Venue guard (2026-09-08). LexingtonGays shipped an Event of the Week whose
    scraped record carried venue "" (the sanity report had already flagged it
    "missing venue"), so docs/index.html rendered <div class="featured-where">
    </div> on the single most prominent block of the site while the description
    told the reader to "find your people by the light rig". A hero event that
    cannot say which building it is in reproduces the exact "I don't know where
    to go" problem the site exists to remove.

    Relative-date junk ("in 3 days", "Tomorrow") leaks into the venue field from
    Eventbrite and Google Events, so those count as no venue too.
    """
    v = (e.get("venue") or "").split(",")[0].strip()
    if len(v) < 3:
        return False
    if _VENUE_NOT_A_PLACE_RE.match(v):
        return False
    return True


_VENUE_NOT_A_PLACE_RE = re.compile(
    r'^(in\s+(a|an|\d+)\s+(day|days|hour|hours|week|weeks|month|months)'
    r'|today|tonight|tomorrow|yesterday|tba|tbd|online|virtual'
    r'|this\s+\w+|next\s+\w+'
    # Facebook card chrome that lands in the venue field (2026-11-23): the
    # freshness replay surfaced "Kowboy Hugs and Drag Queen Kisses Benefit Show
    # @ Shared by Stacy Gorley" and "Halloween Monster Ball @ Shared by JOMO
    # Pride Inc" as heroes. Fresh one-offs now win more often, and many come
    # from facebook_events, so a hero must still name a building.
    r'|shared\s+by\b.*|happening\s+now)$', re.I)


def select_eotw(events_this_week: List[Dict],
                _venue_pass: bool = False, fresh=None) -> Optional[Dict]:
    """
    Return the single best Event of the Week from events already filtered
    to the current Mon-Sun window.  Returns None when no suitable LGBTQ
    event is found (the caller should handle that gracefully, not fall back
    to a random community event).

    `fresh` is a Freshness for this week. None loads it from disk for the week
    the events fall in; False turns the freshness ranking off (pure tiers).
    """
    if not events_this_week:
        return None
    if fresh is None:
        fresh = Freshness.for_week(_infer_week_key(events_this_week))

    # EOTW must be a VERIFIABLE one-off. Recurring auto-events (recurring.py)
    # are date-stamped onto a weekday without checking they actually happen, so
    # they are NEVER eligible to auto-win the hero slot (William 2026-06-23: an
    # unverified "Drag Bingo Bongo at Saturn Room" recurring rule headlined a
    # post for an event that wasn't happening). They still appear on day slides
    # and the website. A pinned manual EOTW (data/manual_eotw.json) always wins
    # and bypasses this — that path is human-verified.
    # A hero needs a real date (2026-11-23): qlist rows like "First Thursday Art
    # Show" arrive dateless, and the freshness ranking would otherwise let a
    # brand-new dateless row outrank a dated show.
    eligible = [
        e for e in events_this_week
        if not _is_skip(e) and (e.get("source") or "").lower() != "recurring"
        and _has_date(e)
    ]

    # Venue guard (2026-09-08) — see _has_venue. Run the whole tier ladder first
    # over candidates that have a venue; only if NOTHING with a venue qualifies
    # do we fall through to the full pool (and then the page template renders an
    # honest fallback instead of an empty div). Implemented as a pre-pass so
    # every tier below is untouched and the ranking rules stay in one place.
    if not _venue_pass:
        _with_venue = [e for e in events_this_week if _has_venue(e)]
        if len(_with_venue) != len(events_this_week):
            _best = select_eotw(_with_venue, _venue_pass=True, fresh=fresh)
            if _best is not None:
                return _best

    # Tier 0 — Homo Hotel Happy Hour (William's own night: always wins, may repeat)
    pool = sorted([e for e in eligible if _is_hh(e)], key=_sort_key)
    if pool:
        return pool[0]

    # Tier 1 — Council Oak Men's Chorale / COMC
    pool = sorted([e for e in eligible if _is_council(e)], key=_sort_key)
    if pool:
        return pool[0]

    # Tiers 2-5 (drag, queer performance, trusted-source ticketed, LGBTQ
    # keyword or gay venue), ranked FRESHNESS FIRST, then tier, then brand-new
    # before seen-before, then the old within-tier sort. See the Freshness
    # block above for why. A stale candidate still wins a week with nothing
    # fresh, so this never empties a cover the tier ladder would have filled.
    cands = [(e, t) for e in eligible if (t := _eotw_tier(e)) in (2, 3, 4, 5)]
    if cands:
        return min(cands, key=lambda et: (_already_over(et[0]),)
                   + _fresh_rank(et[0], et[1], fresh))[0]

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
                     week_key: Optional[str] = None,
                     confirmed=None, strict: bool = False,
                     fresh=None) -> List[Dict]:
    """Return an ordered list of Events of the Week (usually 1, sometimes 2).

    Order of precedence:
      1. Human-pinned manual override (data/manual_eotw.json) — always wins.
      2. Auto: partner special events (one hero per active partner from
         data/featured_partners.json) lead, so PFLAG / OKEQ deals are honored
         automatically; any remaining hero slot is filled by the marquee
         auto-pick (select_eotw). Capped at 2 to fit the stacked-cover layout.
      3. Single auto-selected EOTW when there are no partner events.
    Returns [] if nothing qualifies.

    `confirmed` (2026-10-27) is tools/truth_status.TruthStatus.featurable or
    None. preflight hard-blocks an EOTW its source never confirmed, so: each
    partner's hero is its best CONFIRMED special when it has one, and the
    marquee pick runs over confirmed rows (plus Homo Hotel Happy Hour, William's
    own night) before it may fall back to the whole week. `strict` is the prep
    degrade ladder's confirmed-only rebuild: unconfirmed partner specials are
    dropped and the HHHH exemption goes too. Manual pins are never filtered.

    `fresh` (2026-11-23) is a Freshness; None loads it for week_key (or the
    week the events fall in), False disables it. A partner special leads only
    while it is FRESH (bucket 0/1): not weekly, its series not a hero in the
    last 12 weeks, and its building not a hero in the last 3. Before this the
    OKEQ partner match on "equality center" put that one building in the hero
    slot 15 of 17 weeks. A stale partner event can still win the marquee slot
    on merit when nothing fresher exists."""
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

    if fresh is None:
        fresh = Freshness.for_week(week_key or _infer_week_key(events_this_week))

    # 2. Auto path — lead with partner special events (one per partner).
    partners = _load_partner_matchers()
    heroes: List[Dict] = []
    seen_ids = set()
    if partners:
        def _conf_rank(e):
            return 0 if (confirmed is None or confirmed(e)) else 1

        best_by_partner: Dict[str, Dict] = {}
        for e in events_this_week:
            if not _is_partner_special(e, partners):
                continue
            if not _has_date(e):
                continue
            if fresh:
                _i = fresh.info(e)
                if _i["group"] != 0 or not (_i["oneoff"] or _i["landmark"]):
                    continue
            if strict and confirmed is not None and not confirmed(e):
                continue
            pname = _partner_of(e, partners)
            cur = best_by_partner.get(pname)
            if cur is None or (_conf_rank(e), _sort_key(e)) < (_conf_rank(cur), _sort_key(cur)):
                best_by_partner[pname] = e
        for e in sorted(best_by_partner.values(), key=_sort_key):
            if id(e) not in seen_ids:
                heroes.append(e)
                seen_ids.add(id(e))

    # Fill any remaining hero slot (up to 2) with the marquee auto-pick.
    if len(heroes) < 2:
        # Never two heroes of one series (two Homo Hotel Happy Hour rows from
        # different feeds, or a partner pick and its own duplicate).
        hero_keys = [_series_key(h) for h in heroes]
        rest = [e for e in events_this_week if id(e) not in seen_ids
                and not any(_same_series(_series_key(e), hk) for hk in hero_keys)]
        marquee = None
        if confirmed is not None:
            marquee = select_eotw([e for e in rest if confirmed(e) or (_is_hh(e) and not strict)],
                                  fresh=fresh)
        if marquee is None:
            marquee = select_eotw(rest, fresh=fresh)
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

    # ── Freshness (William 2026-11-23: stop repeating the same heroes) ────────
    wk = "2026-W48"
    mon, thu, fri, sat = "2026-11-23", "2026-11-26", "2026-11-27", "2026-11-28"
    eqc = "Dennis R. Neill Equality Center, 621 E 4th St"
    dragn = {"name": "DRAGNIFICENT! Drag Show", "source": "community_groups", "date": thu,
             "venue": "Club Majestic, 124 N Boston Ave", "url": "u", "description": "drag show"}
    revue = {"name": "RED RIBBON REVUE UNDERWEAR AUCTION W/PORSCHE LYNN", "source": "facebook_events",
             "date": sat, "venue": "1338 E 3rd St, Tulsa, OK", "url": "u", "description": "fundraiser"}
    harvest = {"name": "Rainbow Harvest: Free Farmer's Market", "source": "okeq", "date": sat,
               "venue": eqc, "url": "u", "description": "groceries"}
    prior = [(1, {"name": "DRAGNIFICENT! at Club Majestic", "venue": "Club Majestic"}),
             (2, {"name": "DRAGNIFICENT! Drag Show", "venue": "124 N Boston Ave"}),
             (6, {"name": "Queer Crafters Club", "venue": eqc})]
    hist = [(1, {"name": "Queer Crafters Club", "venue": eqc}),
            (5, {"name": "Rainbow Harvest", "venue": eqc}),
            (1, {"name": "Homo Hotel Happy Hour", "venue": "Mayo Hotel"})]
    fr = Freshness(wk, eotw_history=hist, prior_events=prior)

    if fr.info(dragn)["bucket"] != 4:
        fails.append(f"weekly DRAGNIFICENT should be STANDING: {fr.info(dragn)}")
    if fr.info(harvest)["bucket"] != 3:
        fails.append(f"Rainbow Harvest (hero 5 wk ago) should be series-cooled: {fr.info(harvest)}")
    pick = select_eotw([dragn, revue, harvest], fresh=fr)
    if not pick or pick["name"] != revue["name"]:
        fails.append(f"fresh one-off revue at the Eagle must beat weekly drag + repeat: {pick and pick['name']}")
    if (select_eotw([dragn, revue, harvest], fresh=False) or {}).get("name") != dragn["name"]:
        fails.append("fresh=False must reproduce the old pure tier ladder (drag tier first)")
    if (select_eotw([dragn], fresh=fr) or {}).get("name") != dragn["name"]:
        fails.append("a week with only stale candidates must still get a hero (never empty)")
    friday_shows = {"name": "Friday Drag Shows at Tulsa Eagle", "date": fri, "source": "qlist",
                    "venue": "Tulsa Eagle, 1338 E 3rd St", "url": "u"}
    if fr.info(friday_shows)["bucket"] != 4:
        fails.append("'Friday Drag Shows' is weekly by name")

    # venue cooldown: Equality Center was the hero last week
    eqc_new = {"name": "No Hate Photoshoot", "source": "okeq", "date": sat, "venue": eqc, "url": "u"}
    ybr_new = {"name": "Queer Women's Collective Tulsa", "source": "manual", "date": fri,
               "venue": "Yellow Brick Road Pub, 2630 E 15th St", "description": "queer women social"}
    if fr.info(eqc_new)["bucket"] != 2:
        fails.append(f"Equality Center hero last week -> venue cooldown: {fr.info(eqc_new)}")
    if (select_eotw([eqc_new, ybr_new], fresh=fr) or {}).get("name") != ybr_new["name"]:
        fails.append("a fresh event elsewhere must beat a fresh one at last week's hero venue")
    with _mock.patch.object(sys.modules[__name__], "_load_partner_matchers", lambda: partners):
        heroes = select_eotw_list([eqc_new, ybr_new], week_key=wk, fresh=fr)
    if any(h["name"] == eqc_new["name"] for h in heroes):
        fails.append("partner auto-lead must not fire for a venue in cooldown")
    fr_clear = Freshness(wk, eotw_history=[(5, {"name": "Rainbow Harvest", "venue": eqc})], prior_events=prior)
    crafters = {"name": "Queer Crafters Club", "source": "okeq", "date": thu, "venue": eqc, "url": "u"}
    with _mock.patch.object(sys.modules[__name__], "_load_partner_matchers", lambda: partners):
        h1 = select_eotw_list([eqc_new, ybr_new], week_key=wk, fresh=fr_clear)
        h2 = select_eotw_list([crafters, revue], week_key=wk, fresh=fr_clear)
    if not h1 or h1[0]["name"] != eqc_new["name"]:
        fails.append(f"a never-listed partner one-off should auto-lead: {[h['name'] for h in h1]}")
    # Auto-leading would put Crafters first with the revue second; without it
    # the marquee alone picks the revue (a performance outranks a craft club).
    if [h["name"] for h in h2] != [revue["name"]]:
        fails.append(f"monthly partner programming (listed 6 wk ago) must not auto-lead: {[h['name'] for h in h2]}")
    if fr_clear.info(crafters)["oneoff"]:
        fails.append("Queer Crafters Club listed 6 weeks ago is not a one-off")

    # exemptions: HHHH may repeat; landmarks ignore the venue cooldown
    hhhh = {"name": "Homo Hotel Happy Hour", "source": "homo_hotel", "date": fri,
            "venue": "Courtyard Downtown", "url": "u"}
    if (select_eotw([hhhh, revue], fresh=fr) or {}).get("name") != hhhh["name"]:
        fails.append("HHHH must still win even though it was the hero last week")
    pride = {"name": "Tulsa Pride 2026", "source": "okeq", "date": sat, "venue": eqc, "url": "u"}
    drag_new = {"name": "Hocus Pocus Drag Brunch", "source": "rendered_sites", "date": sat,
                "venue": "Bricktown Comedy Club Tulsa", "url": "u", "description": "drag brunch"}
    if (select_eotw([pride, drag_new], fresh=fr) or {}).get("name") != pride["name"]:
        fails.append("Tulsa Pride (annual landmark) must headline despite the venue cooldown")
    if _is_landmark({"name": "Tulsa Pagan Pride Day"}):
        fails.append("Pagan Pride Day is not an LGBTQ landmark")

    # series keys
    a = _series_key({"name": "Drag Brunch : jul. 11th - stars, stripes & sequins", "venue": "Elote Cafe & Catering"})
    b = _series_key({"name": "Elote Drag Brunch", "venue": "Elote Cafe, 514 S Boston Ave"})
    c = _series_key({"name": "Drag Brunch Presented by Elote", "venue": "Bryson Day Travieso"})
    d = _series_key({"name": "Hocus Pocus Drag Brunch", "venue": "Bricktown Comedy Club Tulsa"})
    if not (_same_series(a, b) and _same_series(a, c)):
        fails.append(f"Elote drag brunch spellings must be one series: {a} {b} {c}")
    if _same_series(a, d):
        fails.append("Hocus Pocus Drag Brunch is its own series")

    # guards
    if select_eotw([{"name": "First Thursday Art Show", "source": "qlist", "url": "u",
                     "venue": "Allie Jensen Gallery"}], fresh=fr) is not None:
        fails.append("a dateless row must never be the hero")
    if _eotw_tier({"name": "THE ALABAMA SOLUTION: SCREENING", "source": "tulsa_artist_fellowship",
                   "venue": "Flagship", "description": "incarceration, immigration detention"}) is not None:
        fails.append("'igra' inside 'immigration' must not make an event LGBTQ")
    if _eotw_tier({"name": "Transgender Day of Visibility Picnic", "source": "x", "venue": "Park"}) != 5:
        fails.append("'transgender' must still count as LGBTQ")
    if _has_venue({"venue": "Shared by Stacy Gorley"}):
        fails.append("'Shared by <name>' is Facebook chrome, not a venue")
    global _TODAY_OVERRIDE
    _saved = _TODAY_OVERRIDE
    try:
        from datetime import date as _d
        _TODAY_OVERRIDE = _d(2026, 11, 25)
        monday_new = dict(ybr_new, date=mon)
        if (select_eotw([monday_new, dragn], fresh=fr) or {}).get("name") != dragn["name"]:
            fails.append("mid-week refresh must not keep a hero that already happened")
    finally:
        _TODAY_OVERRIDE = _saved

    if fails:
        print("SELFTEST FAILED:")
        for f in fails:
            print("  -", f)
        return 1
    print("SELFTEST PASSED — partner auto-highlight, service exclusion, "
          "support-meeting policy, marquee fallback, and freshness (standing, "
          "series + venue cooldown, landmarks, HHHH exemption) all verified.")
    return 0


if __name__ == "__main__":
    import sys as _sys
    if "--selftest" in _sys.argv:
        raise SystemExit(_selftest())
    print("eotw_selector.py — use --selftest to run the regression checks.")
