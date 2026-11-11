"""Would the average gay person be welcome at this event?

William, 2026-11-11, looking at the W46 deck: "My Tulsa gays posts are showing a
lot of things that aren't even gay in the events and that the average gay person
probably would not be welcome at." The W46 list he was looking at (291 events)
carried, among others:

  - "Baptist Collegiate Ministries Free Lunch Monday", "Asbury Campus Fellowship
    Bible Study", "Kappa Phi Christian Sisterhood", "WOW - Worship on Wednesday"
  - "Homecoming Weekend Brunch for Parents, Families & Alumni" (University of
    Tulsa) as SUNDAY'S TOP PICK, ranked over the Black Queer Tulsa brunch
  - "Pizza & Patriotism", "Intelligent Singles Mixer in Tulsa OK",
    "A Singles Friendsgiving Social Event"
  - "Alistair Wedding Reception" (a private booking on the Equality Center
    calendar) chosen as Event of the Week in a replay of the week
  - ~110 student-life rows from the University of Tulsa, TCC and OSU-Tulsa
    calendars: tutoring, residence-hall dinners, HIIT classes, skills groups

Nothing upstream asked the question this module asks. runner.apply_quality_filters
keeps every non-LGBTQ row as a "community_event" unless it is spam, civic, kids or
pro sports, so whole campus and ministry calendars flowed onto tulsagays.com and,
on thin days, into the carousel.

`unwelcoming_reason(event)` returns a short reason when the event should not be on
the guide at all, else "". It is called from tools/sanity_check_events.rules_pass,
which runs at scrape time (scraper/runner.py, before save), at slide generation
(main.cmd_generate) and in preflight (a featured/EOTW hit is a hard block), so the
website, the carousel, the "N more events" count and the gate all agree.

Rules, each narrow on purpose:
  private_occasion   a private booking listed on a venue calendar (wedding
                     reception, baby shower, private party). Applies to EVERY
                     row, gay venue or not: strangers are not invited.
  non_affirming_faith  ministry / worship / Bible-study programming, unless it is
                     hosted by one of the affirming congregations registered in
                     config.SOURCES (type "church") or says it is affirming.
  campus_closed      student-life programming from a campus calendar (TU, TCC,
                     OSU-Tulsa, ORU ...). Public performances and anything
                     marked "open to the public" stay, except at ORU, whose
                     student code bans same-sex relationships.
  straight_dating    singles mixers and speed dating with no queer signal.
  partisan_hostile   organisations that campaign against LGBTQ people
                     (Turning Point USA, Moms for Liberty, crisis-pregnancy
                     centres) and "patriotism" programming.
  closed_audience    alumni / faculty / students-only / members-only events.

Every rule except private_occasion skips an event that is queer in itself
(eotw_selector._is_lgbtq_strict, or an identity word in its own name), so a
"Queer Bible Study", a "Gay Singles Mixer" or "TU Pride Alumni Night" stays.

Self-test: python scraper/welcome.py
"""

from __future__ import annotations

import os
import re
import sys
from typing import Dict

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

try:
    import config as _config
except Exception:  # pragma: no cover - config is always importable in this repo
    _config = None


def _rx(*alternatives: str) -> re.Pattern:
    """Word-boundary alternation; punctuation counts as a boundary."""
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(alternatives) + r")(?![a-z0-9])",
                      re.IGNORECASE)


# ── Queer in itself ──────────────────────────────────────────────────────────
# An identity word in the event's OWN name. Mirrors the 5-flamingo identity list
# in content/image_maker._flamingo_score.
_OWN_QUEER_RX = _rx(
    r"queer(?:ing|ed|ness|s)?", r"lgbtq?\+?", r"lgbtqia\+?", r"gays?", r"lesbians?",
    r"sapphic", r"dykes?", r"bi(?:sexual)?", r"trans(?:gender)?", r"non-?binary",
    r"two-spirit", r"drag", r"pride", r"pflag", r"homo hotel", r"hhhh", r"rainbow",
    r"affirming",
)
# A description that is explicitly about queer people or names a queer org. The
# campus / singles / members-only rules stand down for it: TU's "Sex in the Dark"
# is co-presented by the Equality Center, OSU-Tulsa's "Queering Body Image Group"
# is an LGBTQ+ group. Deliberately narrow: "pride" ("show your Golden Hurricane
# pride") and "affirming" ("an affirming space for neurodivergent students") do
# not count here.
_DESC_QUEER_RX = _rx(
    r"lgbtq?(?:ia)?\+?", r"queer(?:ing|ness)?", r"gays?", r"lesbians?", r"bisexual",
    r"transgender", r"trans (?:people|folks|community|students|youth|adults)",
    r"non-?binary", r"two-spirit", r"equality center", r"oklahomans for equality",
    r"okeq", r"pflag",
)


def is_queer_in_itself(ev: Dict) -> bool:
    name = (ev.get("name") or "").lower()
    try:
        from eotw_selector import strip_non_lgbtq_pride
        name = strip_non_lgbtq_pride(name)   # "Golden Hurricane Pride" is not Pride
    except Exception:
        pass
    if _OWN_QUEER_RX.search(name):
        return True
    try:
        from eotw_selector import _is_lgbtq_strict
        return bool(_is_lgbtq_strict(ev))
    except Exception:
        return False


# ── private_occasion ─────────────────────────────────────────────────────────
_PRIVATE_OCCASION_RX = _rx(
    r"wedding reception", r"wedding ceremony", r"rehearsal dinner",
    r"baby shower", r"bridal shower", r"gender reveal",
    r"private (?:party|event|rental|function|booking)",
    r"(?:facility|room|venue) rental",
)

# ── non_affirming_faith ──────────────────────────────────────────────────────
# Name, venue or description: organisation names that are unambiguous.
_FAITH_ORG_RX = _rx(
    r"bible stud(?:y|ies)", r"collegiate ministr(?:y|ies)", r"campus ministr(?:y|ies)",
    r"student ministr(?:y|ies)", r"baptist student", r"baptist collegiate",
    r"christian (?:sisterhood|brotherhood|sorority|fraternity)",
    r"kappa phi", r"chi alpha", r"campus crusade", r"young life", r"intervarsity",
    r"fellowship of christian athletes", r"(?:campus|christian|student|bible) fellowship",
    r"catholic student", r"newman (?:center|club)", r"campus outreach",
)
# Name or venue only: words that appear harmlessly in descriptions.
_FAITH_NAME_RX = _rx(
    r"worship", r"praise (?:and|&) worship", r"tent revival", r"revival (?:meetings?|services?)",
    r"sermon", r"gospel meeting",
    r"church service", r"worship service", r"prayer (?:meeting|night|breakfast|service)",
    r"(?:holy|daily|sunday|catholic|campus|student|latin) mass", r"rosary",
    r"eucharistic", r"adoration", r"evangeli(?:sm|stic|cal)", r"apologetics",
    r"mission trip", r"missionar(?:y|ies)",
    # NOT "cru" or "fca": "2026 FCA National Meet" is the Falcon Club of America.
)
# Phrases that mark an affirming congregation or event.
_AFFIRMING_FAITH_RX = _rx(
    r"affirming", r"open and affirming", r"reconciling", r"more light",
    r"welcoming congregation", r"unitarian", r"metropolitan community church",
    r"mcc", r"dignity ?usa",
)


def _affirming_congregations() -> tuple:
    """Names and source keys of the affirming congregations registered in
    config.SOURCES (type "church"), lowercased. The registry is the vetted
    list (OkEq-listed, Reconciling, More Light, Open and Affirming ...)."""
    names, keys = set(), set()
    for key, spec in (getattr(_config, "SOURCES", {}) or {}).items():
        if not isinstance(spec, dict) or spec.get("type") != "church":
            continue
        keys.add(str(key).lower())
        nm = (spec.get("name") or "").lower().strip()
        if nm:
            names.add(nm)
            # "Fellowship Congregational UCC" -> also "fellowship congregational"
            core = re.sub(r"\b(church|ucc|umc|uu|pcusa|elca|episcopal)\b", "", nm).strip(" ,.-")
            if len(core) >= 8:
                names.add(re.sub(r"\s+", " ", core))
    for extra in getattr(_config, "AFFIRMING_VENUE_KEYWORDS_CITY", []) or []:
        names.add(str(extra).lower())
    keys |= {"all_souls", "all_souls_special"}
    return tuple(sorted(names)), keys


_AFFIRMING_NAMES, _AFFIRMING_KEYS = _affirming_congregations()


def _is_affirming_faith(ev: Dict, text: str) -> bool:
    if (ev.get("source") or "").lower() in _AFFIRMING_KEYS:
        return True
    if any(n in text for n in _AFFIRMING_NAMES):
        return True
    return bool(_AFFIRMING_FAITH_RX.search(text))


# ── campus_closed ────────────────────────────────────────────────────────────
# Matched against venue + url + source_urls. Hostnames are the calendars the
# rendered_sites layer reads (data/rendered_site_specs.json).
_CAMPUS_RX = _rx(
    r"university of tulsa", r"utulsa", r"tulsa community college", r"tulsacc",
    r"tcc (?:metro|northeast|southeast|west) campus", r"okstate\.edu",
    r"osu[- ]tulsa", r"oklahoma state university[- ]tulsa", r"ou[- ]tulsa",
    r"oral roberts", r"oru\.edu", r"northeastern state", r"nsuok", r"rogers state",
    r"rsu\.edu", r"langston university", r"presence\.io",
)
# A campus whose student code forbids same-sex relationships: nothing it hosts
# is a place the average gay reader is welcome, performances included.
_HOSTILE_CAMPUS_RX = _rx(r"oral roberts", r"oru\.edu", r"oru")
# Public performances and exhibitions on a campus stay on the guide.
_CAMPUS_PUBLIC_ARTS_RX = _rx(
    r"concerts?", r"recitals?", r"symphony", r"orchestra", r"philharmonic", r"choir",
    r"chorale", r"chorus", r"ensemble", r"jazz band", r"wind band", r"opera", r"ballet",
    r"dance concert", r"musical", r"theat(?:re|er)", r"film screening", r"screenings?",
    r"film festival",
    r"gallery", r"exhibition", r"exhibit", r"art show", r"artist talk", r"art opening",
    r"opening reception", r"poetry reading", r"author reading", r"book signing",
    r"storytell(?:er|ers|ing)",
)
# Campus rows that read like the arts but are not open performances.
_CAMPUS_NOT_PUBLIC_RX = _rx(r"rehearsals?", r"auditions?", r"club meeting", r"practice")
_OPEN_TO_PUBLIC_RX = _rx(r"open to the public", r"free and open to (?:the|all) public")

# ── straight_dating ──────────────────────────────────────────────────────────
_STRAIGHT_DATING_RX = re.compile(
    r"(?<![a-z0-9])singles?(?![a-z0-9])[^.!?]{0,40}?(?<![a-z0-9])"
    r"(?:mixer|social|night|mingle|event|party|meetup|meet-up|friendsgiving|dance|"
    r"dinner|happy hour|brunch|speed)(?![a-z0-9])"
    r"|(?<![a-z0-9])speed[- ]?dating(?![a-z0-9])|(?<![a-z0-9])matchmak",
    re.IGNORECASE)

# ── partisan_hostile ─────────────────────────────────────────────────────────
_HOSTILE_ORG_RX = _rx(
    r"turning point usa", r"tpusa", r"young republicans", r"college republicans",
    r"republican women", r"moms for liberty", r"right to life",
    r"crisis pregnancy", r"pregnancy resource cent(?:er|re)",
    r"family policy council", r"promise keepers", r"focus on the family",
    r"american family association", r"alliance defending freedom",
)
_HOSTILE_NAME_RX = _rx(r"patriotism", r"pro-?life", r"maga", r"america first", r"gop")

# ── closed_audience ──────────────────────────────────────────────────────────
_CLOSED_AUDIENCE_RX = _rx(
    r"alumn(?:i|ae) (?:reception|mixer|dinner|brunch|lunch|luncheon|weekend|association|"
    r"event|gathering|tailgate|social|night)", r"(?:&|and) alumn(?:i|ae)", r"alumn(?:i|ae) (?:&|and)",
    r"faculty (?:&|and) staff", r"faculty in residence",
    r"faculty (?:meeting|senate|only|dinner|lunch|luncheon|appreciation|development)",
    r"staff only", r"employees? only", r"students? only", r"student-only", r"current students",
    r"parents,? (?:&|and) famil(?:y|ies)", r"residence hall", r"res(?:idence)? life",
    r"first-year students?", r"members[- ]only", r"invitation[- ]only", r"invite[- ]only",
)


# ── Big enough for a slide ───────────────────────────────────────────────────
# William, 2026-11-11, after the first fix: "Some things are okay if they're big
# things but like some are not." A NON-gay event may take a slide slot only when
# it is a big, citywide thing: the curated major-events list
# (data/major_tulsa_events.json, source "major_tulsa", his rule "we have to have
# the major events"), a festival / parade / Route 66 Centennial event / art crawl
# / state fair / fireworks, an arena show at the BOK Center, or a Broadway tour.
# A Circle Cinema screening, a Philbrook docent tour, a comedian at Bricktown or
# a DJ in a casino lounge is welcoming but small: it stays on the website and is
# never on a slide.
_BIG_NAME_RX = re.compile(
    r"(?<![a-z0-9])(?:festivals?|fest|oktoberfest|mayfest|winterfest|juneteenth|"
    r"(?<!a )parades?|centennial|100 years of route 66|route 66 birthday|state fair|"
    r"street fair|art crawl|block party|carnival|fireworks|holiday lights|"
    r"christmas lights|tulsa tough)(?![a-z0-9])", re.IGNORECASE)
# Small formats that borrow a big word.
_SMALL_FORMAT_RX = _rx(
    r"book club", r"volunteers?", r"volunteer opportunity", r"co-?working",
    r"junior olympics", r"trunk or treat", r"supper club", r"festival energy",
    r"film fest(?:ival)?", r"short films?", r"screenings?",
)
_BIG_VENUE_RX = _rx(r"bok center", r"celebrityattractions(?:\.com)?")
_BROADWAY_RX = _rx(r"broadway", r"(?:the )?broadway musical")


def is_big_event(ev: Dict) -> bool:
    """True for a big, citywide event that earns a slide slot without being gay."""
    if (ev.get("source") or "").lower() == "major_tulsa":
        return True
    name = ev.get("name") or ""
    if _BIG_NAME_RX.search(name) and not _SMALL_FORMAT_RX.search(name):
        return True
    loc = _location_blob(ev)
    if _BIG_VENUE_RX.search(loc) or _BROADWAY_RX.search(name):
        return True
    return False


def _location_blob(ev: Dict) -> str:
    urls = [ev.get("url") or ""] + list(ev.get("source_urls") or [])
    return " ".join([ev.get("venue") or "", ev.get("address") or ""] + urls).lower()


def unwelcoming_reason(ev: Dict) -> str:
    """Short reason this event does not belong on an LGBTQ+ guide, or ""."""
    name = (ev.get("name") or "").strip()
    low_name = name.lower()
    venue = (ev.get("venue") or "").lower()
    desc = (ev.get("description") or "").lower()

    if _PRIVATE_OCCASION_RX.search(low_name):
        return "private occasion (not open to the public)"

    if is_queer_in_itself(ev):
        return ""

    name_venue = f"{low_name} {venue}"
    full = f"{name_venue} {desc}"

    if _FAITH_ORG_RX.search(full) or _FAITH_NAME_RX.search(name_venue):
        if not _is_affirming_faith(ev, full):
            return "non-affirming religious programming"

    desc_queer = bool(_DESC_QUEER_RX.search(desc))

    loc = _location_blob(ev)
    if _CAMPUS_RX.search(loc) and not desc_queer:
        if _HOSTILE_CAMPUS_RX.search(loc):
            return "campus event at a school that bans same-sex relationships"
        public = (_CAMPUS_PUBLIC_ARTS_RX.search(low_name)
                  or _OPEN_TO_PUBLIC_RX.search(desc))
        if (not public or _CLOSED_AUDIENCE_RX.search(low_name)
                or _CAMPUS_NOT_PUBLIC_RX.search(low_name)):
            return "campus student-life programming (not a public event)"

    if _STRAIGHT_DATING_RX.search(low_name) and not desc_queer:
        return "straight singles / dating event"

    if _HOSTILE_ORG_RX.search(full) or _HOSTILE_NAME_RX.search(low_name):
        return "partisan or anti-LGBTQ organisation"

    if _CLOSED_AUDIENCE_RX.search(low_name) and not desc_queer:
        return "closed audience (alumni / students / members only)"

    return ""


if __name__ == "__main__":
    def _ev(name, venue="", url="", desc="", source="rendered_sites"):
        return {"name": name, "venue": venue, "url": url, "description": desc, "source": source}

    drop = [
        _ev("Baptist Collegiate Ministries Free Lunch Monday", "University of Tulsa"),
        _ev("Asbury Campus Fellowship Bible Study", "University of Tulsa"),
        _ev("Kappa Phi Christian Sisterhood", "Tulsa, OK"),
        _ev("WOW – Worship on Wednesday", "Tulsa, OK"),
        _ev("Homecoming Weekend Brunch for Parents, Families & Alumni", "University of Tulsa",
            "https://calendar.utulsa.edu/"),
        _ev("Pizza & Patriotism", "NORTH HALL", "https://events.tulsa.okstate.edu/event/pizza"),
        _ev("Mobility Workshop", "NORTH HALL", "https://events.tulsa.okstate.edu/event/mobility"),
        _ev("Yoga with Bea", "University of Tulsa"),
        _ev("Women's Basketball vs. Texas Southern", "Reynolds Center",
            "https://utulsa.trumba.com/event/1"),
        _ev("Intelligent Singles Mixer in Tulsa OK", "Roof Sixty-Six Rooftop Bar", source="eventbrite"),
        _ev("2nd Thursday Game Night: A Singles Friendsgiving Social Event", "Studio Nine18",
            source="eventbrite"),
        _ev("Speed Dating Night (Ages 30-45)", "Fassler Hall", source="eventbrite"),
        _ev("Alistair Wedding Reception", "Dennis R. Neill Equality Center, 621 E 4th St",
            source="okeq"),
        _ev("Turning Point USA Chapter Meeting", "Tulsa, OK"),
        _ev("Gala Night", "Tulsa, OK", desc="Benefiting the Tulsa Pregnancy Resource Center."),
        _ev("Spring Concert", "Mabee Center", "https://www.oru.edu/events/spring-concert"),
        _ev("Members Only Wine Tasting", "Tulsa Country Club"),
        _ev("Tulsa Ensemble Club Rehearsal", "University of Tulsa"),
        _ev("Parent & Family Weekend Check In", "Collins Hall", "https://calendar.utulsa.edu/event/x",
            desc="918 Day is a civic pride day to celebrate Tulsa's diverse heritage.", source="utulsa_pride"),
        _ev("Women's Basketball vs. Oklahoma State", "Reynolds Center", "https://calendar.utulsa.edu/e",
            desc="Show your Golden Hurricane pride!", source="utulsa_pride"),
    ]
    keep = [
        _ev("Queer Bible Study", "Tulsa, OK"),
        _ev("Gay Singles Mixer", "Tulsa Eagle, 1338 E 3rd St"),
        _ev("TU Pride Alumni Mixer", "University of Tulsa"),
        _ev("Lesbian Speed Dating", "Yellow Brick Road"),
        _ev("Sunday Worship", "All Souls Unitarian Church"),
        _ev("Advent Worship Service", "Boston Avenue United Methodist"),
        _ev("Evensong & Worship", "Trinity Episcopal Church"),
        _ev("Interfaith Worship", "Tulsa, OK", desc="An open and affirming service for everyone."),
        _ev("David B. Waters Trust String Quartet Recital", "University of Tulsa"),
        _ev("Cappella Chamber Singers/Concert Chorale Fall Concert", "University of Tulsa"),
        _ev("Continuing the Search: The Legacy of Eddie Faye Gates", "University of Tulsa",
            desc="This lecture is free and open to the public."),
        _ev("Mass Movement Open Studio", "Mass Movement Community Arts"),
        _ev("Critical Mass Bike Ride", "Guthrie Green"),
        _ev("Route 66 Centennial Crawl", "Guthrie Green"),
        _ev("Thank You, Veterans", "Philbrook Museum of Art"),
        _ev("Tanya Tucker", "Hard Rock Live at Hard Rock Hotel & Casino Tulsa"),
        _ev("Single-Origin Coffee Tasting", "Foolish Things Coffee"),
        _ev("The Singles Bar: Album Release Show", "Mercury Lounge"),
        _ev("Prayer Vigil for Trans Day of Remembrance", "Tulsa, OK"),
        _ev("Black Queer Tulsa Monthly Brunch", "Various locations", source="black_queer_tulsa"),
        _ev("Faculty Art Exhibition Opening Reception", "Tulsa Community College"),
        _ev("The Moth x Center for Creativity: Storyteller Showcase", "Tulsa Community College"),
        _ev("Queering Body Image Group", "MAIN HALL", "https://events.tulsa.okstate.edu/event/body-image",
            source="osu_tulsa"),
        _ev("Sex in the Dark", "Allen Chapman Student Union", "https://calendar.utulsa.edu/event/sex",
            desc="The Office of Resilience & Belonging and The Equality Center present a panel."),
        _ev("2026 FCA National Meet", "Falcon Club of America", source="google_events"),
    ]
    big = [
        _ev("Route 66 Tulsa Birthday Bash & Veterans Day Parade", "Downtown Tulsa", source="major_tulsa"),
        _ev("Route 66 Centennial Crawl", "Guthrie Green"),
        _ev("Bob Wills' Texas Playboys - Celebrating 100 Years of Route 66", "Guthrie Green"),
        _ev("Tulsa State Fair", "Expo Square"),
        _ev("First Friday Art Crawl", "Tulsa Arts District"),
        _ev("Zeeco Oktoberfest Tulsa", "River West Festival Park"),
        _ev("BENSON BOONE", "BOK Center"),
        _ev("The Notebook (Broadway Musical)", "Tulsa PAC"),
    ]
    small = [
        _ev("The One", "Circle Cinema, 10 S Lewis Ave", source="circle_cinema"),
        _ev("Docent-Led Tour: Collection Highlights", "Philbrook Museum of Art", source="philbrook_museum"),
        _ev("Ari Matti", "Bricktown Comedy Club Tulsa"),
        _ev("DJ | Oreo", "Riffs at Hard Rock Hotel & Casino Tulsa"),
        _ev("$5 First Friday at LowDown", "LowDown Tulsa"),
        _ev("Manhattan Short Film Fest", "Circle Cinema, 10 S Lewis Ave", source="circle_cinema"),
        _ev("Oktoberfest Volunteer Opportunity", "", source="meetup"),
        _ev("(part 2) DCC Book Club: a Parade of Horribles", "Central Library"),
        _ev("Red Heat Ceramics 6th Annual Ceramic Art Sale", "Tulsa, OK"),
        _ev("Tanya Tucker", "Hard Rock Live at Hard Rock Hotel & Casino Tulsa"),
    ]
    failed = 0
    for e in big:
        if not is_big_event(e):
            print(f"FAIL should be big: {e['name']!r}")
            failed += 1
    for e in small:
        if is_big_event(e):
            print(f"FAIL should be small: {e['name']!r}")
            failed += 1
    for e in drop:
        r = unwelcoming_reason(e)
        if not r:
            print(f"FAIL should drop: {e['name']!r}")
            failed += 1
    for e in keep:
        r = unwelcoming_reason(e)
        if r:
            print(f"FAIL should keep: {e['name']!r} ({r})")
            failed += 1
    print(f"welcome selftest: {len(drop)} drops, {len(keep)} keeps, {len(big)} big, "
          f"{len(small)} small, {failed} failures")
    raise SystemExit(1 if failed else 0)
