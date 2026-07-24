"""Orchestrator that runs all scrapers, applies quality filters, deduplicates, sorts, and saves events."""

import sys
import os
import json
import logging
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

from scraper import (
    recurring,
    okeq_calendar,
    twisted_arts,
    specific_orgs,
    eventbrite_meetup,
    community_calendars,
    extended_calendars,
    aa_meetings,
    homo_hotel,
    community_groups,
    qlist,
    churches,
    bars,
    manual_input,
    major_events,
    tulsa_arts_district,
    facebook_events,
    ticketing_sites,
    timetree_scraper,
    slack_browser_scraper,
    studio66,
    instagram_orgs,
    rendered_sites,
)
from scraper.relevance import compile_keywords

logger = logging.getLogger(__name__)

# Playwright scrapers are optional -- only available if playwright is installed
try:
    from scraper import playwright_scrapers as _playwright_scrapers
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _playwright_scrapers = None
    _PLAYWRIGHT_AVAILABLE = False
    logger.warning("playwright not installed -- playwright_scrapers will be skipped")

# ── Constants ────────────────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.75

# Explicit LGBTQ identity terms — matched with WORD BOUNDARIES. The old
# substring check marked dozens of generic events "LGBTQ-relevant" every week:
# 'bi' fired inside 'bingo'/'exhibit', 'trans' inside 'transform', and generic
# cultural words like 'workshop' made an Owasso small-business workshop count
# as an LGBTQ event (W24).
_LGBTQ_IDENTITY_TERMS = [
    "lgbtq", "lgbtqia", "lgbt", "queer", "gay", "gays", "lesbian", "bi",
    "bisexual", "trans", "transgender", "nonbinary", "non-binary", "drag",
    "pride", "rainbow", "dyke", "sapphic", "two-spirit", "twospirit", "homo",
    "equality", "affirming", "pflag", "gender",
]
_LGBTQ_IDENTITY_RX = re.compile(
    r"(?<![a-z0-9])(" + "|".join(re.escape(t) for t in _LGBTQ_IDENTITY_TERMS) + r")(?![a-z0-9])",
    re.IGNORECASE,
)

# Queer-coded event types: reliably draw queer crowds even without explicit
# LGBTQ branding. Substring match is fine for these multi-char phrases.
LGBTQ_KEYWORDS = [
    "oddities", "curiosities",          # Oddities & Curiosities touring market
    "burlesque", "cabaret",             # queer performance traditions
    "wiz",                              # The Wiz (Black/queer cultural touchstone)
    "boots riley",                      # radical filmmaker, queer community following
    "gender outreach",
]

# Generic community/cultural signals — these KEEP an event (the website lists
# all real Tulsa community events) but mark it community_event, NOT
# lgbtq_relevant. They used to live in LGBTQ_KEYWORDS, which inflated the
# LGBTQ counts feeding the content gate, the >=60% featured-LGBTQ target, and
# the EOTW pool.
COMMUNITY_CULTURE_KEYWORDS = [
    "feminist", "radical",
    "night market", "art market", "bazaar", "market",
    "greenwood", "black wall street",
    "screening", "film festival", "documentary",
    "exhibition", "opening reception", "art opening",
    "workshop", "panel discussion", "panel", "lecture",
    "fundraiser", "benefit show", "benefit concert",
    "cultural festival", "heritage",
    "open mic", "poetry",
]

# Generic non-LGBTQ blocklist — sports, oil/gas, mass non-LGBTQ religious events.
# Patterns most US cities will share. City-specific additions live in
# config.NON_LGBTQ_BLOCKLIST_CITY (e.g. local college sports team names).
_GENERIC_NON_LGBTQ_BLOCKLIST = [
    # College/pro sports (universal)
    "football game", "football season", "nfl ", " nfl", "nba ", " nba",
    "mlb ", " mlb", "nhl ", " nhl", "college football", "college basketball",
    "nascar", "ufc ", " ufc", "mma fight",
    # Motorsport "drag" + kids programming + hobby comps (William 2026-07-06:
    # google_events flooded Sesame Street / gymnastics / car-stereo comps in,
    # and automotive drag races masqueraded as drag shows).
    "drag racing", "drag races", "drag strip", "dragway", "raceway",
    "street outlaws", "motocross", "monster truck", "car stereo", "car audio",
    "sesame street", "paw patrol", "disney on ice", "bluey live",
    "gymnastics meet", "gymnastics championship", "cheer competition",
    "gun show", "rock mineral society",
    # "Trans-Miss" = Trans-Mississippi Golf Association, a straight amateur golf
    # tournament the word-boundary "trans" matcher misreads as LGBTQ (W28 made it
    # Tuesday's boxed hero). Mainstream golf championships are off-topic anyway.
    "trans-miss", "trans miss amateur", "amateur golf championship",
    # Petroleum/energy industry conferences
    "society of petroleum", "petroleum engineers",
    "spe ior", "spe improved", "improved oil recovery",
    "reservoir heterogeneity", "reservoir characterization",
    "oil and gas conference", "oil & gas conference",
    "drilling conference", "pipeline conference", "petroleum conference",
    # Non-LGBTQ religious mass events
    "revival meeting", "men's prayer breakfast", "prayer rally",
    "women's prayer breakfast",
]

# Generic junk names — scraper artifacts to discard regardless of city.
JUNK_NAMES = {
    "map", "google calendar", "get your tickets", "buy tickets",
    "learn more", "view all", "see more", "load more", "rsvp",
    "register", "sign up", "donate", "subscribe", "contact us",
    "home", "about", "menu", "calendar", "events", "back",
    # Google Events card artifacts (W24 shipped three "Information and Tickets" cards)
    "information and tickets", "information and tickets ...",
    "get directions", "tickets & info", "more information", "event details",
    # Org-site navigation text that scrapes as "events" (community_groups)
    "weekly events", "upcoming events", "stay connected", "our partners",
    "event application", "event calendar", "get your tickets",
}

# Compose city-specific values from config (with safe fallbacks for new-city scaffolds).
LGBTQ_SOURCES = getattr(config, "LGBTQ_SOURCES", set())
COMMUNITY_PARTNER_KEYWORDS = getattr(config, "COMMUNITY_PARTNER_KEYWORDS", [])
NON_LGBTQ_BLOCKLIST = _GENERIC_NON_LGBTQ_BLOCKLIST + getattr(config, "NON_LGBTQ_BLOCKLIST_CITY", [])

# Word-boundary matchers for the community-keeper lists. Substring matching
# used to keep an event as community_event on false hits ('market' inside
# 'supermarket'/'marketing', 'panel' inside a random word); word boundaries
# match runner's identity regex. Keeper lists only gate WEBSITE inclusion, so
# this is lower-stakes than the LGBTQ gate, but the same correctness applies.
_COMMUNITY_PARTNER_RX = compile_keywords(COMMUNITY_PARTNER_KEYWORDS)
_COMMUNITY_CULTURE_RX = compile_keywords(COMMUNITY_CULTURE_KEYWORDS)



# ── Normalization & dedup ─────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text


def _are_similar(name_a: str, name_b: str) -> bool:
    a = _normalize(name_a)
    b = _normalize(name_b)
    if not a or not b:
        return False
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= SIMILARITY_THRESHOLD


def _same_date(date_a: str, date_b: str) -> bool:
    if not date_a or not date_b:
        return True
    return date_a.strip() == date_b.strip()


def _venues_match(venue_a: str, venue_b: str) -> bool:
    """One normalized venue contains the other (long enough to be meaningful).
    Catches 'Elote Cafe & Catering' vs 'Elote Cafe & Catering, 514 S Boston Ave'."""
    a, b = _normalize(venue_a or ""), _normalize(venue_b or "")
    if len(a) < 8 or len(b) < 8:
        return False
    return a in b or b in a


# Words too generic to prove two same-venue titles are one event ("Non-binary
# Support Group" vs "Gender Outreach Support Group" are DIFFERENT groups).
_VENUE_DEDUP_GENERIC = {
    "support", "group", "night", "meeting", "weekly", "monthly", "annual",
    "tulsa", "event", "events", "with", "presents", "featuring",
}


def _same_event_by_venue(ev_a: Dict, ev_b: Dict) -> bool:
    """Same date + same venue + names sharing >=2 significant words = one real
    event scraped under two different titles. Name similarity alone missed
    W28's 'Elote Drag Brunch' (recurring) vs 'Drag Brunch : jul. 11th - stars,
    stripes & sequins' (community_groups) — both at Elote on the same Saturday,
    which put the same brunch in two of Saturday's three featured slots.

    Only DISTINCTIVE shared words count: generic event-type words are ignored,
    and so are words of the venue itself leaking into a title ('Happy Hour at
    Saturn Room' vs 'Record Night at Saturn Room' are different events)."""
    if not _same_date(ev_a.get("date", ""), ev_b.get("date", "")):
        return False
    if not _venues_match(ev_a.get("venue"), ev_b.get("venue")):
        return False
    venue_words = {w for w in _normalize((ev_a.get("venue") or "") + " " + (ev_b.get("venue") or "")).split()
                   if len(w) >= 4}

    def _tokens(name):
        out = set()
        for w in _normalize(name or "").split():
            if len(w) < 4 or w in _VENUE_DEDUP_GENERIC:
                continue
            # venue word (or an address-glued variant like 'room209') in a title
            if any(v.startswith(w) or w.startswith(v) for v in venue_words):
                continue
            out.add(w)
        return out

    return len(_tokens(ev_a.get("name")) & _tokens(ev_b.get("name"))) >= 2


def deduplicate(events: List[Dict]) -> List[Dict]:
    """Remove duplicate events based on name + date similarity, or same
    venue + date + overlapping name words (the cross-source rename case)."""
    if not events:
        return []

    unique = []
    for event in events:
        is_dup = False
        for i, existing in enumerate(unique):
            if (_are_similar(event["name"], existing["name"]) and _same_date(event["date"], existing["date"])) \
                    or _same_event_by_venue(event, existing):
                is_dup = True
                # Collect all unique URLs from both events before deciding winner
                merged_urls = list(dict.fromkeys(
                    (existing.get("source_urls") or []) + (event.get("source_urls") or [])
                ))
                # A live-scraped record BEATS the hardcoded recurring one: the
                # scrape proves a SPECIAL instance ('Drag Brunch : ... stars,
                # stripes & sequins' vs the recurring 'Elote Drag Brunch'),
                # and source=recurring is barred from EOTW — letting recurring
                # win the merge silently demoted the week's top event.
                rec_event = (event.get("source") == "recurring")
                rec_existing = (existing.get("source") == "recurring")
                if rec_event != rec_existing:
                    if rec_existing:
                        unique[i] = event
                elif event["priority"] < existing["priority"]:
                    unique[i] = event
                elif event["priority"] == existing["priority"]:
                    event_info = sum(1 for v in event.values() if v)
                    existing_info = sum(1 for v in existing.values() if v)
                    if event_info > existing_info:
                        unique[i] = event
                # Backfill the winner from the loser so a merge never LOSES
                # information (address venue, richer description/time, URL).
                winner = unique[i]
                loser = existing if winner is event else event

                def _has_addr(v):
                    return "," in (v or "") or any(c.isdigit() for c in (v or ""))
                if _has_addr(loser.get("venue")) and not _has_addr(winner.get("venue")):
                    winner["venue"] = loser["venue"]
                if len(loser.get("description") or "") > len(winner.get("description") or ""):
                    winner["description"] = loser["description"]
                if loser.get("url") and not winner.get("url"):
                    winner["url"] = loser["url"]
                if loser.get("time") and not winner.get("time"):
                    winner["time"] = loser["time"]
                if loser.get("lgbtq_relevant"):
                    winner["lgbtq_relevant"] = True
                winner["source_urls"] = merged_urls
                break
        if not is_dup:
            unique.append(event)

    return unique


# ── Quality filters ───────────────────────────────────────────────────────────

def _get_week_range():
    """Return (monday, sunday) datetime objects for the current week."""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday.replace(hour=0, minute=0, second=0, microsecond=0), sunday.replace(hour=23, minute=59, second=59, microsecond=999999)


def _is_junk_name(name: str) -> bool:
    """Return True if the name is clearly navigation/UI text, not an event."""
    if not name or len(name) < 5:
        return True
    low = name.lower().strip()
    if low in JUNK_NAMES:
        return True
    # Punctuation variants: "(map)", "Get Your Tickets!", "WEEKLY EVENTS:"
    stripped = re.sub(r"[^a-z0-9& ]", "", low).strip()
    if stripped in JUNK_NAMES:
        return True
    if len(name) > 200:
        return True
    return False


def _is_in_current_week(date_str: str) -> bool:
    """Return True if date_str (YYYY-MM-DD) falls within the current Mon-Sun week."""
    if not date_str:
        return False
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        monday, sunday = _get_week_range()
        return monday <= dt <= sunday
    except ValueError:
        return False


def _is_clearly_not_lgbtq(event: Dict) -> bool:
    """Return True if this event matches the non-LGBTQ blocklist — exclude regardless of source."""
    combined = " ".join([
        (event.get("name") or ""),
        (event.get("description") or ""),
        (event.get("venue") or ""),
    ]).lower()
    return any(kw in combined for kw in NON_LGBTQ_BLOCKLIST)


def _is_lgbtq_relevant(event: Dict) -> bool:
    """Return True if this event is genuinely LGBTQ-relevant (trusted source,
    identity term with word boundaries, or queer-coded event type). Generic
    cultural events and partner-venue events are handled separately — they are
    KEPT but classified community_event, not LGBTQ."""
    source = event.get("source", "")
    if source in LGBTQ_SOURCES:
        return True
    combined = " ".join([
        event.get("name", ""),
        event.get("description", ""),
        event.get("url", ""),
    ]).lower()
    if _LGBTQ_IDENTITY_RX.search(combined):
        return True
    if any(kw in combined for kw in LGBTQ_KEYWORDS):
        return True
    return False


def _is_community_keeper(event: Dict) -> bool:
    """Genuine Tulsa community/cultural event or queer-welcoming partner venue —
    keep on the website even without LGBTQ relevance."""
    combined = " ".join([
        event.get("name", ""),
        event.get("description", ""),
        event.get("venue", ""),
        event.get("url", ""),
    ]).lower()
    if _COMMUNITY_PARTNER_RX.search(combined):
        return True
    return bool(_COMMUNITY_CULTURE_RX.search(combined))


# ── Geographic filter ──────────────────────────────────────────────────────
# Tulsa metro / Oklahoma markers. If any appear in an event's location fields,
# the event is in-region and kept regardless of other-state matches.
_OK_MARKERS = (
    "tulsa", "oklahoma", ", ok", " ok ", " ok,",
    "broken arrow", "owasso", "jenks", "bixby", "sand springs", "sapulpa",
    "claremore", "catoosa", "glenpool", "skiatook", "collinsville",
    "okmulgee", "muskogee", "wagoner", "coweta", "okc", "stillwater", "norman",
)

# Full names of all other 49 states + DC (no "oklahoma").
_OTHER_STATE_NAMES = (
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oregon", "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming",
)

# ", ST ZIP" pattern for every state abbreviation except OK. Requires a comma
# and a following ZIP/space so prose like ", in person" never matches.
_OTHER_STATE_ABBR_RE = re.compile(
    r",\s*(al|ak|az|ar|ca|co|ct|de|fl|ga|hi|id|il|in|ia|ks|ky|la|me|md|ma|mi|"
    r"mn|ms|mo|mt|ne|nv|nh|nj|nm|ny|nc|nd|oh|or|pa|ri|sc|sd|tn|tx|ut|vt|va|wa|"
    r"wv|wi|wy|dc)\b(\s+\d|\s*$)",
    re.IGNORECASE,
)


# Services / recurring programming that must NEVER be featured or lead a day
# (they still appear on the website). Detected from RAW name + description at
# scrape time, before the LLM voice softens the language, and persisted as a
# `never_feature` flag the selection logic reads.
_NEVER_FEATURE_SIGNALS = (
    "support group", "aa meeting", "lgbtq+ aa", "bowling league",
    "health clinic", "hope testing", "drop-in therapy", "therapy session",
    "cognitive behavioral", "therapy-based", "dialectical behavioral", "dbt",
    "behavioral therapy", "group therapy", "hiv+ support", "hiv support",
    "peer support", "smart recovery", "recovery meeting", "monthly meeting",
    "girl scout", "shut up & write", "raise your spiritual iq", "mix and mingle",
    "ttrpg", "free testing", "guiding right", "okeq senior", "okeq health",
    "sunday service", "sunday services", "open meditation", "drop-in",
    # Services are not events (William 2026-07-06: W28 boxed "Fair Housing:
    # Legal Aid Services" + "Name & Gender Correction Clinic" as day heroes).
    "(cancelled", "cancelled)",  # cancelled events stay listed, never featured
    "legal aid", "legal services", "legal clinic", "legal help", "fair housing",
    "correction clinic", "name & gender", "name and gender", "expungement",
    "know your rights", "fafsa", "wellness fair", "health fair",
    "health and wellness fair", "vaccine", "vaccination", "resource fair",
    "food pantry", "blood drive", "coat drive", "clinic",
)


# A cancelled/postponed event must NEVER be a highlighted pick (W28 featured
# "(Cancelled) Clothing Swap!" as a Saturday hero). Names get word-boundary
# matching in any spelling/format; descriptions only match explicit
# "this event is off" phrasing so ticket boilerplate like "free cancellation"
# or a "cancellation policy" paragraph never fires.
_CANCELLED_NAME_RE = re.compile(r"\b(cancell?ed|postponed|rescheduled)\b", re.IGNORECASE)
_CANCELLED_DESC_RE = re.compile(
    r"\b(has been|have been|is|are|was|were|event)\s+(cancell?ed|postponed)\b"
    r"|\bcancell?ed due to\b|\bno longer happening\b",
    re.IGNORECASE)


def _is_cancelled(event: Dict) -> bool:
    if _CANCELLED_NAME_RE.search(event.get("name") or ""):
        return True
    return bool(_CANCELLED_DESC_RE.search(event.get("description") or ""))


def _is_never_feature(event: Dict) -> bool:
    if _is_cancelled(event):
        return True
    text = ((event.get("name") or "") + " " + (event.get("description") or "")).lower()
    return any(sig in text for sig in _NEVER_FEATURE_SIGNALS)


# Clear non-community SPAM — dropped even though we otherwise keep Tulsa-area
# community/cultural events. (Career/investor/MLM/webinar/job-fair noise.)
_SPAM_NOISE_KW = (
    "career blueprint", "project manager", "investor", "founders |",
    "real estate", "make money", "webinar", "mlm", "side hustle", "crypto",
    "franchise", "sales training", "networking for", "passive income",
    "business opportunity", "hiring event", "job fair", "biggest community",
    "investors founders",
)

# Civic / government / business-networking noise — W24 shipped an Owasso city
# small-business workshop and a Chamber of Commerce legislative breakfast.
# These never belong on an LGBTQ+ community events guide. Applied only to
# events that are NOT lgbtq_relevant, so a "Pride Night at City Hall" or an
# LGBTQ chamber mixer still passes.
_CIVIC_NOISE_KW = (
    "city council", "council meeting", "town hall meeting", "school board",
    "planning commission", "board of adjustment", "county commission",
    "city commission", "chamber of commerce", "legislative wrap-up",
    "legislative breakfast", "legislative update", "small business workshop",
    "business workshop", "lunch and learn", "lunch & learn", "ribbon cutting",
    "rotary club", "kiwanis", "toastmasters", "economic development",
    "homeowners association", "hoa meeting", "brotherhood breakfast",
)
_CIVIC_VENUE_KW = (
    "chamber of commerce", "city hall", "city of owasso", "city of broken arrow",
    "city of bixby", "city of jenks", "city of sand springs", "city of sapulpa",
)

# Children's / library-kids programming — real events, wrong audience for the
# site (W24 listed baby storytimes, Teen Time: Gaming, kids' day camps).
_KIDS_NOISE_KW = (
    "storytime", "story time", "toddlers", "babies", "teen time",
    "kids camp", "day camp", "summer camp", "vacation bible school",
    "pint-size", "build a reader", "kids club", "children's program",
)

# Mainstream pro/minor-league sports game listings. Only applied to
# non-LGBTQ events, so "Pride Night at the Drillers" still passes.
_MAINSTREAM_SPORTS_KW = (
    "tulsa drillers", "wind surge", "fc tulsa", "tulsa oilers",
    "tulsa roughnecks", "at tulsa drillers", "vs. tulsa",
)


def _is_spam_noise(event: Dict) -> bool:
    text = ((event.get("name") or "") + " " + (event.get("description") or "")).lower()
    return any(sig in text for sig in _SPAM_NOISE_KW)


def _is_offtopic_noise(event: Dict) -> tuple:
    """(True, reason) when a non-LGBTQ event is civic/government, kids-library,
    or mainstream-sports noise that makes no sense on the site."""
    text = ((event.get("name") or "") + " " + (event.get("description") or "")).lower()
    venue = (event.get("venue") or "").lower()
    if any(kw in text for kw in _CIVIC_NOISE_KW) or any(kw in venue for kw in _CIVIC_VENUE_KW):
        return True, "civic/government/business-networking"
    if any(kw in text for kw in _KIDS_NOISE_KW):
        return True, "children's programming"
    if any(kw in text or kw in venue for kw in _MAINSTREAM_SPORTS_KW):
        return True, "mainstream sports game"
    return False, ""


def _location_text(event: Dict) -> str:
    return " ".join([
        event.get("venue", "") or "",
        event.get("address", "") or "",
        event.get("city", "") or "",
        event.get("location", "") or "",
    ]).lower()


def _is_out_of_region(event: Dict) -> bool:
    """True if the event is clearly outside the Tulsa metro / Oklahoma."""
    loc = _location_text(event).strip()
    if not loc:
        return False  # no location info — cannot judge, keep it
    if any(m in loc for m in _OK_MARKERS):
        return False  # explicitly Oklahoma/Tulsa metro
    if any(s in loc for s in _OTHER_STATE_NAMES):
        return True
    if _OTHER_STATE_ABBR_RE.search(loc):
        return True
    return False


def apply_quality_filters(events: List[Dict]) -> List[Dict]:
    """Apply all quality filters and annotate each event with lgbtq_relevant."""
    monday, sunday = _get_week_range()
    filtered = []
    removed_counts = {
        "no_name": 0, "junk_name": 0, "out_of_week": 0,
        "non_lgbtq_blocklist": 0, "not_lgbtq_relevant": 0, "out_of_region": 0,
    }

    for event in events:
        name = event.get("name", "")
        date_str = event.get("date", "")
        source = event.get("source", "")

        # Filter 1: no name
        if not name:
            removed_counts["no_name"] += 1
            continue

        # Filter 2: junk name
        if _is_junk_name(name):
            removed_counts["junk_name"] += 1
            logger.debug(f"[filter] Junk name removed: '{name}'")
            continue

        # Filter 3: dated events outside current week
        if date_str:
            if not _is_in_current_week(date_str):
                removed_counts["out_of_week"] += 1
                logger.debug(f"[filter] Out-of-week removed: '{name}' on {date_str}")
                continue

        # Filter 3b: out-of-region (not Tulsa metro / Oklahoma)
        if _is_out_of_region(event):
            removed_counts["out_of_region"] += 1
            logger.info(f"[filter] Out-of-region removed: '{name}' (loc={_location_text(event)[:60]})")
            continue

        # Filter 4: non-LGBTQ blocklist — blocks matching events from ANY source
        if _is_clearly_not_lgbtq(event):
            removed_counts["non_lgbtq_blocklist"] += 1
            logger.info(f"[filter] Non-LGBTQ blocklist removed: '{name}' (source={source})")
            continue

        # Annotate LGBTQ relevance + never-feature (computed from RAW text now,
        # before enrichment softens service language).
        event["lgbtq_relevant"] = _is_lgbtq_relevant(event)
        if _is_never_feature(event):
            event["never_feature"] = True

        # Filter 5: keep genuine Tulsa community/cultural events even without
        # LGBTQ keywords — they populate the WEBSITE (William: all events you
        # find go on the website) and the featured-candidate pool. Drop clear
        # non-community SPAM (career/investor/MLM/job-fair) AND off-topic noise
        # (civic/government meetings, kids' library programming, mainstream
        # sports games — the W24 "Owasso city council" class of nonsense).
        if source not in LGBTQ_SOURCES and not event["lgbtq_relevant"]:
            if _is_spam_noise(event):
                removed_counts["not_lgbtq_relevant"] += 1
                logger.info(f"[filter] Spam/non-community removed: '{name}' (source={source})")
                continue
            offtopic, reason = _is_offtopic_noise(event)
            if offtopic:
                removed_counts["not_lgbtq_relevant"] += 1
                logger.info(f"[filter] Off-topic removed ({reason}): '{name}' (source={source})")
                continue
            event["community_event"] = True   # kept, not LGBTQ-specific

        filtered.append(event)

    logger.info(
        f"[filter] Removed: {removed_counts['no_name']} no-name, "
        f"{removed_counts['junk_name']} junk-name, "
        f"{removed_counts['out_of_week']} out-of-week, "
        f"{removed_counts['out_of_region']} out-of-region, "
        f"{removed_counts['non_lgbtq_blocklist']} non-LGBTQ blocklist, "
        f"{removed_counts['not_lgbtq_relevant']} not LGBTQ-relevant"
    )
    return filtered


# ── Sorting & grouping ────────────────────────────────────────────────────────

def sort_events(events: List[Dict]) -> List[Dict]:
    """Sort by priority (asc) then by date (asc). Undated events go last in their group."""
    def sort_key(e):
        is_homo_hotel = 0 if e.get("source") == "homo_hotel" else 1
        priority = e.get("priority", 99)
        date_sort = e.get("date", "") or "9999-99-99"
        return (is_homo_hotel, priority, date_sort)

    return sorted(events, key=sort_key)


def split_weekday_weekend(events: List[Dict]) -> Dict[str, List[Dict]]:
    """Split events into weekday (Mon-Thu) and weekend (Fri-Sun) groups."""
    weekday = []
    weekend = []
    undated = []

    for event in events:
        date_str = event.get("date", "")
        if not date_str:
            undated.append(event)
            continue
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            if dt.weekday() >= 4:  # Fri=4, Sat=5, Sun=6
                weekend.append(event)
            else:
                weekday.append(event)
        except ValueError:
            undated.append(event)

    weekday.extend(undated)
    weekend.extend(undated)

    # Signature event always in both groups (configured via config.SIGNATURE_EVENT)
    _sig_event = getattr(config, "SIGNATURE_EVENT", None) or {}
    _sig_source_key = _sig_event.get("source_key", "")
    _sig_keywords = _sig_event.get("name_keywords", [])

    def _is_signature(ev: dict) -> bool:
        if _sig_source_key and ev.get("source") == _sig_source_key:
            return True
        name = ev.get("name", "").lower()
        return any(kw in name for kw in _sig_keywords)

    sig_events = [e for e in events if _is_signature(e)]
    for h in sig_events:
        if h not in weekday:
            weekday.insert(0, h)
        if h not in weekend:
            weekend.insert(0, h)

    return {"weekday": weekday, "weekend": weekend}


# ── Signature event guarantee ─────────────────────────────────────────────────

def ensure_signature_event(events: List[Dict]) -> List[Dict]:
    """Always ensure the city's signature event is present and at the top.
    Configured via config.SIGNATURE_EVENT. If a city has no signature event,
    this is a no-op."""
    sig_event = getattr(config, "SIGNATURE_EVENT", None) or {}
    sig_source_key = sig_event.get("source_key", "")

    if not sig_source_key:
        return events

    has_sig = any(e.get("source") == sig_source_key for e in events)

    if not has_sig:
        # Try to import the signature event scraper if it exists
        try:
            from scraper import homo_hotel as _signature_scraper
        except ImportError:
            try:
                _signature_scraper = __import__(f"scraper.{sig_source_key}", fromlist=[""])
            except ImportError:
                logger.warning(f"Signature event source '{sig_source_key}' has no scraper module; skipping inject")
                return events
        sig_events = _signature_scraper.scrape()
        for e in sig_events:
            e["lgbtq_relevant"] = True
        events = sig_events + events
        logger.info(f"Injected {sig_event.get('name', 'signature')} events (were missing)")
    else:
        sig_evs = [e for e in events if e.get("source") == sig_source_key]
        others = [e for e in events if e.get("source") != sig_source_key]
        events = sig_evs + others

    return events


# Backward-compat alias so existing call sites keep working
ensure_homo_hotel = ensure_signature_event


_UNICODE_DASHES = "‐‑‒–—―−"  # ‐‑‒–—―−
_TIME_TOKEN_RX = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?$", re.IGNORECASE)


def _clean_time_text(t: str) -> str:
    """Normalize unicode whitespace (thin/narrow no-break spaces from Google
    Events) to ASCII space and unicode dashes to '-'. Google emits times like
    '6 - 10 PM' which the old ASCII-only parsing missed entirely."""
    import unicodedata
    t = "".join(" " if unicodedata.category(c) == "Zs" else c for c in t)
    for d in _UNICODE_DASHES:
        t = t.replace(d, "-")
    return re.sub(r"\s+", " ", t).strip()


def _parse_time_token(tok: str, meridiem_hint: str = None):
    """Parse '6', '6:30', '6 PM', '18:30' -> (hour24, minute) or None.
    A bare number is only accepted when a meridiem hint is supplied (i.e. it
    came from a range like '6 - 10 PM' whose other side carries the AM/PM)."""
    m = _TIME_TOKEN_RX.match(tok.strip())
    if not m:
        return None
    h, mins = int(m.group(1)), int(m.group(2) or 0)
    mer = (m.group(3) or meridiem_hint or "").upper()
    if mins > 59:
        return None
    if mer:
        if not 1 <= h <= 12:
            return None
        if mer == "PM" and h != 12:
            h += 12
        elif mer == "AM" and h == 12:
            h = 0
    else:
        # No meridiem anywhere: only accept unambiguous 24h with minutes ("19:00")
        if m.group(2) is None or not 0 <= h <= 23:
            return None
    return h, mins


def _fmt_12h(hm) -> str:
    return datetime(2000, 1, 1, hm[0], hm[1]).strftime("%I:%M %p").lstrip("0")


def _normalize_time_str(t: str) -> str:
    """Convert any scraped time string to canonical 12-hour AM/PM format.

    Handles the formats that previously broke downstream display:
      '6 - 10 PM'  -> '6:00 PM - 10:00 PM'  (unicode spaces, shared meridiem)
      '9:00 - 10:30 AM'           -> '9:00 AM - 10:30 AM'
      '19:00'                     -> '7:00 PM'
    The old code split only on ASCII ' - ', so unicode-dash ranges fell through
    unparsed and the website's display regex then grabbed the only AM/PM-tagged
    token: the END time (soda-bottle convention at '6 - 10 PM' rendered as 10 PM).
    Unparseable strings (e.g. 'Doors 9 PM, Show 10 PM') are returned unchanged."""
    raw = t.strip()
    cleaned = _clean_time_text(raw)
    parts = re.split(r"\s*(?:-|\bto\b)\s*", cleaned, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        start_s, end_s = parts[0].strip(), parts[1].strip()
        sm = _TIME_TOKEN_RX.match(start_s)
        em = _TIME_TOKEN_RX.match(end_s)
        # In shorthand ranges the side missing AM/PM inherits the other side's
        # ('6 - 10 PM' means 6 PM; '9:00 AM - 1' means 1 AM is wrong but unseen)
        end_hint = em.group(3).upper() if (em and em.group(3)) else None
        start_hint = sm.group(3).upper() if (sm and sm.group(3)) else None
        start = _parse_time_token(start_s, meridiem_hint=end_hint)
        end = _parse_time_token(end_s, meridiem_hint=start_hint)
        if start and end:
            return f"{_fmt_12h(start)} - {_fmt_12h(end)}"
        if start:
            return f"{_fmt_12h(start)} - {end_s}" if end_s else _fmt_12h(start)
        return raw
    single = _parse_time_token(parts[0])
    return _fmt_12h(single) if single else raw


# ── Save ─────────────────────────────────────────────────────────────────────

def get_week_key(date: datetime = None) -> str:
    if date is None:
        date = datetime.now()
    return f"{date.year}-W{date.isocalendar()[1]:02d}"


def save_results(events: List[Dict], week_key: str = None):
    config.ensure_dirs()
    if week_key is None:
        week_key = get_week_key()

    # G204 GEO GUARD: drop events belonging to a DIFFERENT city before any file
    # is written. Found on LexingtonGays 2026-07-23, where 14 of 84 events were
    # published at TULSA venues (Philbrook, Circle Cinema, Dennis R. Neill
    # Equality Center, qlist.app/events/Tulsa/...) relabelled as Lexington -
    # addresses that do not exist in that metro. The offending scrapers live in
    # THIS shared file tree, which sync_from_tulsa.py overlays onto every city
    # site, so the guard belongs here in the master and propagates outward.
    # Guarding at the single write choke point covers _all/_weekday/_weekend.
    # Fail-OPEN by design: a guard bug must never take a site down. If no city
    # is configured it REFUSES TO GUESS and passes everything through.
    try:
        from tools.geo_guard import filter_events as _geo_filter, resolve_city as _resolve_city
        _city = _resolve_city(config)
        if not _city:
            raise RuntimeError(
                "no CITY_NAME/CITY/SITE_CITY in config - refusing to guess a city")
        _kept, _dropped = _geo_filter(events, _city)
        if _dropped:
            print(f"[geo_guard] dropped {len(_dropped)} event(s) not in {_city}:")
            for _e in _dropped[:10]:
                print(f"    - {str(_e.get('name'))[:50]} | {_e.get('_dropped_reason')}")
            events = _kept
    except Exception as _e:  # noqa: BLE001 - never block a publish on the guard
        print(f"[geo_guard] SKIPPED (non-fatal): {_e}")

    split = split_weekday_weekend(events)

    combined_path = os.path.join(config.EVENTS_DIR, f"{week_key}_all.json")
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump({
            "week": week_key,
            "generated_at": datetime.now().isoformat(),
            "total_events": len(events),
            "events": events,
        }, f, indent=2, ensure_ascii=False)

    weekday_path = os.path.join(config.EVENTS_DIR, f"{week_key}_weekday.json")
    with open(weekday_path, "w", encoding="utf-8") as f:
        json.dump({
            "week": week_key,
            "type": "weekday",
            "days": "Monday - Thursday",
            "generated_at": datetime.now().isoformat(),
            "total_events": len(split["weekday"]),
            "events": split["weekday"],
        }, f, indent=2, ensure_ascii=False)

    weekend_path = os.path.join(config.EVENTS_DIR, f"{week_key}_weekend.json")
    with open(weekend_path, "w", encoding="utf-8") as f:
        json.dump({
            "week": week_key,
            "type": "weekend",
            "days": "Friday - Sunday",
            "generated_at": datetime.now().isoformat(),
            "total_events": len(split["weekend"]),
            "events": split["weekend"],
        }, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(events)} events to {combined_path}")
    return combined_path, weekday_path, weekend_path


# ── Main runner ───────────────────────────────────────────────────────────────

def run_all_scrapers() -> List[Dict]:
    """Run all scrapers in priority order and return combined raw results."""
    all_events = []

    # Ordered by importance/reliability
    scrapers = [
        ("manual_input", manual_input.scrape),  # Always first — manually curated, priority honored (default 1)
        ("major_events", major_events.scrape),  # Marquee Tulsa civic events (Tulsa Tough, Route 66 centennial, State Fair, Oktoberfest...) — website coverage, priority 3
        ("recurring", recurring.scrape),
        ("okeq_calendar", okeq_calendar.scrape),
        ("twisted_arts", twisted_arts.scrape),
        ("specific_orgs", specific_orgs.scrape),
        ("eventbrite_meetup", eventbrite_meetup.scrape),
        ("meetup", None),  # Already included in eventbrite_meetup.scrape
        ("homo_hotel", homo_hotel.scrape),
        ("community_calendars", community_calendars.scrape),
        ("extended_calendars", extended_calendars.scrape),
        ("rendered_sites", rendered_sites.scrape),  # JS-rendered venue calendars (Playwright + per-site specs) - revives Philbrook/Cain's/BOK/Hard Rock/etc. that extended_calendars saw as empty shells
        ("aa_meetings", aa_meetings.scrape),
        ("qlist", qlist.scrape),
        ("community_groups", community_groups.scrape),
        ("studio_66", studio66.scrape),  # @studio.66_ IG via authenticated instagrapi session
        ("instagram_orgs", instagram_orgs.scrape),  # IG-only orgs: KLASSIC (@upflykai), Goff Center (@goff_fest)
        ("churches", churches.scrape),
        ("bars", bars.scrape),
        ("tulsa_arts_district", tulsa_arts_district.scrape),
        ("facebook_events", facebook_events.scrape),
        ("ticketing_sites", ticketing_sites.scrape),
        ("timetree_scraper", timetree_scraper.scrape),  # Tulsa Isn't Boring -- iCal/Playwright/browser-flag
        ("slack_browser_scraper", slack_browser_scraper.scrape),  # TulsaRemote Slack -- browser-extracted JSON or flag
    ]

    # Playwright scrapers run after all static scrapers
    # They supplement (not replace) the existing pipeline
    if _PLAYWRIGHT_AVAILABLE:
        scrapers.append(("playwright_scrapers", _playwright_scrapers.scrape_all))
    else:
        logger.info("Skipping playwright_scrapers -- playwright not installed")

    for name, scrape_fn in scrapers:
        if scrape_fn is None:
            continue  # Skip placeholder entries
        logger.info(f"Running scraper: {name}")
        try:
            events = scrape_fn()
            logger.info(f"  {name}: {len(events)} events")
            all_events.extend(events)
        except Exception as e:
            logger.error(f"  {name}: FAILED - {e}", exc_info=True)

    return all_events


def _append_growth_log(events: List[Dict], week_key: str, start_time: datetime):
    """Append a stats record for this scrape run to the growth log JSON array."""
    try:
        # Build events_per_source (only sources with count > 0)
        source_counts: Dict[str, int] = {}
        for e in events:
            src = e.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1
        events_per_source = dict(
            sorted(source_counts.items(), key=lambda x: -x[1])
        )

        # blank_days: Mon-Sun day names with 0 events this week
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_counts: Dict[str, int] = {d: 0 for d in day_names}
        for e in events:
            date_str = e.get("date", "")
            if date_str:
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    day_name = day_names[dt.weekday()]
                    day_counts[day_name] += 1
                except ValueError:
                    pass
        blank_days = [d for d in day_names if day_counts[d] == 0]

        record = {
            "week": week_key,
            "timestamp": datetime.now().isoformat(),
            "total_events": len(events),
            "events_with_dates": sum(1 for e in events if e.get("date", "") != ""),
            "blank_days": blank_days,
            "events_per_source": events_per_source,
            "top_sources": list(events_per_source.keys())[:5],
            "scrape_duration_seconds": round(
                (datetime.now() - start_time).total_seconds(), 1
            ),
        }

        # Load existing log or start fresh
        log_data: List[Dict] = []
        if os.path.exists(config.GROWTH_LOG):
            try:
                with open(config.GROWTH_LOG, "r", encoding="utf-8") as f:
                    log_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                log_data = []

        # Update in place if same week_key already exists, otherwise append
        updated = False
        for i, existing in enumerate(log_data):
            if existing.get("week") == week_key:
                log_data[i] = record
                updated = True
                break
        if not updated:
            log_data.append(record)

        config.ensure_dirs()
        with open(config.GROWTH_LOG, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Growth log updated: {week_key} - {len(events)} events")

    except Exception as exc:
        logger.error(f"Growth log write failed: {exc}", exc_info=True)


PENDING_ACTIONS_PATH = os.path.join(
    os.path.expanduser("~"), ".claude", "pending-william-actions.md"
)
LGBTQ_DATED_MINIMUM = 8
PRIMARY_SOURCE_MINIMUM = 3

# Venues that must be covered every week. If one of these trusted sources
# returns 0 events, that is almost always a silent scrape failure (rate-limited
# IG endpoint, renamed handle, dead site), not a genuinely empty week. The
# content gate only halts when the WHOLE pool is thin, so the main gay bars can
# quietly drop out while other sources fill the quota — this catches exactly
# that. Override per-city via config.KEY_VENUE_SOURCES.
KEY_VENUE_SOURCES = getattr(config, "KEY_VENUE_SOURCES", {
    "tulsa_eagle_ig": "Tulsa Eagle (@tulsaeagle)",
    "club_majestic_ig": "Club Majestic (@clubmajestictulsa)",
    "ybr_ig": "Yellow Brick Road (@tulsaybr)",
    "studio_66": "Studio 66 (@studio.66_)",
})

# ── Flagship upcoming-event hold ──────────────────────────────────────────────
# The weekly site only shows the current Mon–Sun window, so a flagship event
# announced weeks early (Pride, an anniversary, a festival, a big touring drag
# show) would otherwise be dropped by the current-week filter and forgotten by
# the time its week arrives. We persist such FUTURE events to a small ledger and
# resurface them when their week comes around — even if the source stopped
# posting by then. Conservative by design: only genuinely juicy events qualify,
# so the current-week roundup is never polluted with far-off listings.
UPCOMING_LEDGER = os.path.join(getattr(config, "DATA_DIR", "data"), "upcoming_events.json")
FLAGSHIP_LOOKAHEAD_WEEKS = 8
_FLAGSHIP_KEYWORDS = (
    "pride", "anniversary", "festival", "pageant", "ball ", "block party",
    "grand opening", "headliner", "world tour", "drag brunch", "homo hotel",
)


def _write_pending_action(message: str, week_key: str) -> None:
    """Append a timestamped entry to pending-william-actions.md."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n## [{timestamp}] TulsaGays scraper HALTED — {week_key}\n- {message}\n"
        with open(PENDING_ACTIONS_PATH, "a", encoding="utf-8") as f:
            f.write(entry)
        logger.warning(f"[content-gate] Written to pending-william-actions.md")
    except Exception as exc:
        logger.error(f"[content-gate] Could not write pending action: {exc}")


def _warn_missing_key_venues(events: List[Dict], week_key: str) -> None:
    """Loud, NON-halting alert when a must-cover venue returns 0 events.

    Distinct from the content gate (which only fires when the whole pool is
    thin). This is the 'don't silently skip the gay bar' safety net: if the
    Eagle/Majestic/YBR/Studio 66 contributed nothing, flag it so a juicy event
    behind a rate-limited IG endpoint or a renamed handle gets caught and can be
    added by hand, rather than vanishing."""
    present = {(e.get("source") or "") for e in events}
    missing = {src: label for src, label in KEY_VENUE_SOURCES.items() if src not in present}
    if not missing:
        return
    labels = ", ".join(sorted(missing.values()))
    msg = (
        f"{len(missing)} key venue(s) returned 0 events this week: {labels}. "
        "Likely a silent scrape failure (rate-limited IG endpoint, renamed "
        "handle, or dead site), not a genuinely empty week. Check the venue's "
        "Instagram directly and add anything live to data/manual_events.json, "
        "then re-run the scraper."
    )
    logger.warning("[key-venue] %s", msg)
    print(f"\n*** KEY VENUE ALERT ***\n{msg}\n")
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = (f"\n## [{timestamp}] TulsaGays key venue(s) silent — {week_key}\n"
                 f"- {msg}\n")
        with open(PENDING_ACTIONS_PATH, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as exc:
        logger.error(f"[key-venue] Could not write pending action: {exc}")


# ── Flagship upcoming-event hold helpers ──────────────────────────────────────

def _ledger_key(event: Dict) -> tuple:
    return (_normalize(event.get("name", "")), (event.get("date") or "").strip())


def _load_upcoming() -> List[Dict]:
    try:
        with open(UPCOMING_LEDGER, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_upcoming(ledger: List[Dict]) -> None:
    try:
        config.ensure_dirs()
        with open(UPCOMING_LEDGER, "w", encoding="utf-8") as f:
            json.dump(ledger, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        logger.error("[upcoming] could not save ledger: %s", exc)


def _prune_past(ledger: List[Dict]) -> List[Dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    return [e for e in ledger if (e.get("date") or "") >= today]


def _is_flagship_future(event: Dict, sunday: datetime, horizon: datetime) -> bool:
    """A juicy event dated AFTER this week but within the lookahead horizon:
    priority-1, a key-venue event, or a flagship-keyword match."""
    date_str = event.get("date", "")
    if not date_str:
        return False
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
    except ValueError:
        return False
    if not (sunday < dt <= horizon):
        return False
    if int(event.get("priority", 99)) <= 1:
        return True
    if (event.get("source") or "") in KEY_VENUE_SOURCES:
        return True
    text = ((event.get("name") or "") + " " + (event.get("description") or "")).lower()
    return any(kw in text for kw in _FLAGSHIP_KEYWORDS)


def manage_upcoming(raw_events: List[Dict]) -> List[Dict]:
    """Harvest flagship FUTURE events into the ledger and resurface any that have
    now entered the current week. Returns the resurfaced events to merge into the
    pool (they then flow through the normal filter/dedup path). Never raises into
    the caller — the run continues even if the ledger is unreadable."""
    monday, sunday = _get_week_range()
    horizon = sunday + timedelta(weeks=FLAGSHIP_LOOKAHEAD_WEEKS)
    ledger = _prune_past(_load_upcoming())
    seen = {_ledger_key(e) for e in ledger}

    harvested = 0
    for ev in raw_events:
        if _is_flagship_future(ev, sunday, horizon):
            key = _ledger_key(ev)
            if key not in seen:
                stored = dict(ev)
                stored["from_upcoming_ledger"] = True
                ledger.append(stored)
                seen.add(key)
                harvested += 1

    resurfaced = []
    for e in ledger:
        try:
            dt = datetime.strptime((e.get("date") or "")[:10], "%Y-%m-%d")
        except ValueError:
            continue
        if monday <= dt <= sunday:
            ev = dict(e)
            ev["resurfaced_from_upcoming"] = True
            resurfaced.append(ev)

    _save_upcoming(ledger)
    if harvested or resurfaced:
        logger.info("[upcoming] harvested %d future flagship event(s); resurfaced %d "
                    "due this week (ledger now %d)", harvested, len(resurfaced), len(ledger))
    return resurfaced


def main():
    """Main entry point: run all scrapers, filter, deduplicate, sort, save."""
    start_time = datetime.now()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 60)
    logger.info("Tulsa Gays Event Scraper - Starting")
    logger.info(f"Week: {get_week_key()}")
    monday, sunday = _get_week_range()
    logger.info(f"Date range: {monday.date()} to {sunday.date()}")
    logger.info("=" * 60)

    # 1. Run all scrapers
    raw_events = run_all_scrapers()
    logger.info(f"\nTotal raw events: {len(raw_events)}")

    # 1a. Recurring reality-check: drop paused/dead recurring events (a closed
    # bar or cancelled night stops posting a ghost), auto-confirm any that a real
    # live scrape corroborates this week -- adopting the live venue so a moved
    # night self-corrects -- and track verification freshness for the preflight
    # gate. Runs before the upcoming-hold so dropped events are never harvested.
    try:
        from scraper.recurring_verify import verify_recurring, load_ledger, save_ledger
        _vledger = load_ledger()
        _vtoday = datetime.now().strftime("%Y-%m-%d")
        _recurring_evs = [e for e in raw_events if (e.get("source") or "") == "recurring"]
        _live_evs = [e for e in raw_events if (e.get("source") or "") != "recurring"]
        _kept_rec, _vreport = verify_recurring(_recurring_evs, _live_evs, _vtoday, _vledger)
        save_ledger(_vledger)
        raw_events = _live_evs + _kept_rec
        logger.info(
            "[recurring-verify] %d live-confirmed, %d on seed clock, %d venue-adopted, "
            "%d venue-conflict(s), %d dropped (paused/dead)",
            len(_vreport["live_confirmed"]), len(_vreport["seeded"]),
            len(_vreport["venue_adopted"]), len(_vreport["venue_conflicts"]),
            len(_vreport["dropped"]))
        for _vline in _vreport["venue_adopted"]:
            logger.info("[recurring-verify] venue adopted -> %s", _vline)
        for _cline in _vreport["venue_conflicts"]:
            logger.warning("[recurring-verify] possible move -> %s", _cline)
        for _dline in _vreport["dropped"]:
            logger.info("[recurring-verify] dropped -> %s", _dline)
    except Exception as exc:
        logger.error(f"[recurring-verify] step failed (non-fatal): {exc}", exc_info=True)

    # 1b. Flagship upcoming-event hold: remember juicy FUTURE events (Pride,
    # anniversaries, festivals, key-venue/priority-1) so a thing announced weeks
    # early is never dropped, and resurface any whose week has now arrived.
    try:
        resurfaced = manage_upcoming(raw_events)
        if resurfaced:
            raw_events.extend(resurfaced)
            logger.info(f"Re-injected {len(resurfaced)} flagship event(s) due this week")
    except Exception as exc:
        logger.error(f"[upcoming] hold step failed (non-fatal): {exc}", exc_info=True)

    # 2. Apply quality filters (junk names, out-of-week dates, lgbtq_relevant annotation)
    filtered_events = apply_quality_filters(raw_events)
    logger.info(f"After quality filters: {len(filtered_events)}")

    # 3. Deduplicate
    unique_events = deduplicate(filtered_events)
    logger.info(f"After deduplication: {len(unique_events)}")

    # 4. Ensure Homo Hotel is present and at top
    unique_events = ensure_homo_hotel(unique_events)

    # 4.5. Slack zero-event warning — must appear before the content gate
    slack_events = [e for e in unique_events if "slack" in (e.get("source") or "").lower()]
    if not slack_events:
        import glob as _glob
        flag_file = os.path.join(config.DATA_DIR, "slack_browser_needed.flag")
        if os.path.exists(flag_file):
            logger.warning(
                "[SLACK] ZERO Slack events found and slack_browser_needed.flag exists. "
                "TulsaRemote Slack (#events-local, #unite-lgbtq-plus) is a REQUIRED source. "
                "Run the browser extraction step before generating slides."
            )
        else:
            logger.warning(
                "[SLACK] ZERO Slack events found. slack_browser_needed.flag not present — "
                "slack_browser_scraper may have failed silently. Check data/slack_events_browser.json."
            )

    # 4.5b. Key-venue zero-event alert — surfaces a silent gay-bar scrape miss
    # (the "don't skip the juicy events" guard) even when the content gate passes.
    _warn_missing_key_venues(unique_events, get_week_key())

    # 4.6. LGBTQ content quality gate — halt if event pool is too thin to produce a good post
    lgbtq_dated = [
        e for e in unique_events
        if e.get("lgbtq_relevant") and e.get("date")
    ]
    lgbtq_from_primary = [
        e for e in unique_events
        if (e.get("source") or "") in LGBTQ_SOURCES and e.get("date")
    ]

    week_key = get_week_key()

    if len(lgbtq_dated) < LGBTQ_DATED_MINIMUM or len(lgbtq_from_primary) < PRIMARY_SOURCE_MINIMUM:
        missing_primary = [
            src for src in sorted(LGBTQ_SOURCES)
            if not any((e.get("source") or "") == src for e in unique_events)
        ]
        gate_msg = (
            f"CONTENT GATE FAILED for {week_key}: "
            f"{len(lgbtq_dated)} LGBTQ-relevant dated events "
            f"(minimum {LGBTQ_DATED_MINIMUM}), "
            f"{len(lgbtq_from_primary)} from primary LGBTQ sources "
            f"(minimum {PRIMARY_SOURCE_MINIMUM}). "
            f"Primary sources returning 0 events: {missing_primary}. "
            f"Scrape output is too thin or off-audience to post. "
            f"Fix scrapers, re-run the browser Slack step, then re-run the scraper."
        )
        logger.error(f"[content-gate] {gate_msg}")
        print(f"\n*** CONTENT GATE HALT ***\n{gate_msg}\n")
        _write_pending_action(gate_msg, week_key)
        import sys
        sys.exit(1)

    # 5. Sort by priority then date
    sorted_events = sort_events(unique_events)

    # 5b. Normalize all time strings to 12-hour AM/PM format
    for ev in sorted_events:
        raw_t = (ev.get("time") or "").strip()
        if raw_t:
            ev["time"] = _normalize_time_str(raw_t)

    # 5c. Sanity checker — quarantines off-topic/junk/implausible events the
    # keyword filters missed (2026-W24 shipped Owasso civic meetings, kids
    # storytimes, and end-time-as-start-time renders). Runs BEFORE save so the
    # _all/_weekday/_weekend splits are all written clean. Uses an LLM verdict
    # pass when available; NEVER allowed to break the scrape itself.
    week_key = get_week_key()
    try:
        from tools.sanity_check_events import sanitize as _sanitize
        sorted_events, _sanity_report = _sanitize(sorted_events, week_key, use_llm=True)
    except Exception as exc:
        logger.error(f"[sanity] checker failed (saving unsanitized output): {exc}",
                     exc_info=True)

    # 5d. Apply operator venue overrides -- month-scoped corrections that WIN over
    # any stale scraped/hardcoded/ledger venue (e.g. Queer Women's Collective,
    # whose location rotates monthly). The final word on venue before save.
    try:
        from scraper.venue_overrides import apply_venue_overrides
        sorted_events = apply_venue_overrides(sorted_events)
    except Exception as exc:
        logger.error(f"[venue-override] step failed (non-fatal): {exc}", exc_info=True)

    # 6. Save results
    paths = save_results(sorted_events, week_key)

    logger.info(f"\nResults saved for week {week_key}:")
    for p in paths:
        logger.info(f"  {p}")

    # 6c. Append growth log entry
    _append_growth_log(sorted_events, week_key, start_time)

    # 6b. Date-parse health check
    _events_with_dates = [e for e in sorted_events if e.get("date")]
    _events_without_dates = [e for e in sorted_events if not e.get("date")]
    _total = len(sorted_events)
    print(f"\n[DATE SUMMARY] Events WITH dates: {len(_events_with_dates)} | WITHOUT dates: {len(_events_without_dates)} | Total: {_total}")
    if _total > 0:
        _undated_ratio = len(_events_without_dates) / _total
        if _undated_ratio > 0.70:
            logger.warning(
                "WARNING: Date parsing may be broken — review scrapers before generating slides. "
                "%.0f%% of events (%d/%d) have no date.",
                _undated_ratio * 100,
                len(_events_without_dates),
                _total,
            )
            print(
                f"\n*** WARNING: Date parsing may be broken — review scrapers before generating slides. "
                f"{_undated_ratio:.0%} of events ({len(_events_without_dates)}/{_total}) have no date. ***\n"
            )

    # 7. Summary report
    split = split_weekday_weekend(sorted_events)
    dated = [e for e in sorted_events if e.get("date")]
    undated = [e for e in sorted_events if not e.get("date")]
    lgbtq_relevant = [e for e in sorted_events if e.get("lgbtq_relevant")]

    logger.info(f"\n{'='*60}")
    logger.info("SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"  Total unique events:    {len(sorted_events)}")
    logger.info(f"  Events with dates:      {len(dated)}")
    logger.info(f"  Events without dates:   {len(undated)}")
    logger.info(f"  LGBTQ-relevant events:  {len(lgbtq_relevant)}")
    logger.info(f"  Weekday events (Mo-Th): {len(split['weekday'])}")
    logger.info(f"  Weekend events (Fr-Su): {len(split['weekend'])}")

    sources = {}
    for e in sorted_events:
        src = e.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1
    logger.info(f"\n  Events by source:")
    for src, count in sorted(sources.items(), key=lambda x: -x[1]):
        logger.info(f"    {src}: {count}")

    if undated:
        logger.info(f"\n  Sources with undated events (need manual attention):")
        undated_sources = {}
        for e in undated:
            src = e.get("source", "unknown")
            undated_sources[src] = undated_sources.get(src, 0) + 1
        for src, count in sorted(undated_sources.items(), key=lambda x: -x[1]):
            logger.info(f"    {src}: {count} undated")

    logger.info(f"{'='*60}")
    logger.info("Done!")
    logger.info(f"{'='*60}")

    return sorted_events


if __name__ == "__main__":
    main()
