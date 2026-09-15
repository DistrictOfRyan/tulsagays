"""Instagram-only org event scraper (generalized).

Some Tulsa LGBTQ+ / queer-cultural orgs publish their parties ONLY on Instagram —
no website, no calendar, no Eventbrite. This module reads their public IG profiles
and extracts this-week events, using the exact same robust engine proven on Studio 66
(scraper/studio66.py):

  1. Auth-free public web-profile JSON endpoint (primary, needs no login).
  2. Authenticated instagrapi session shared with @tulsagays (fallback only).
  3. Claude (SITES_ANTHROPIC_KEY) to pull structured dated events from free-text
     captions, with a regex / parse_date_flexible fallback when no key is present.

Each configured org is a trusted LGBTQ source (its key lives in config.LGBTQ_SOURCES),
so no keyword relevance filter is applied — but a parseable in-week date IS required.
Every path degrades to an empty list (never crashes) if Instagram blocks the request.

To add another IG-only org: append a dict to ORGS below and add its `source_name`
to config.LGBTQ_SOURCES (and, optionally, name keywords to COMMUNITY_PARTNER_KEYWORDS
so the org's events also pass when they surface in FB groups / aggregators).

Run standalone:  python scraper/instagram_orgs.py
"""

import os
import sys
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scraper.base import BaseScraper
import config

logger = logging.getLogger(__name__)

# Same session file the @tulsagays engagement tasks use (off the synced drive).
SETTINGS_FILE = Path.home() / ".credentials" / "ig_settings_tulsagays.json"

# Public web App-ID — lets the logged-out web_profile_info JSON endpoint return posts.
IG_WEB_APP_ID = "936619743392459"
WEB_PROFILE_URL = "https://www.instagram.com/api/v1/users/web_profile_info/?username={user}"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36")
POSTS_TO_SCAN = 12      # most recent posts to read each run

# Output budget for one extraction call. Raised 1500 -> 4000 on 2026-09-09: a
# venue that posts DAILY (the Tulsa Eagle posts every day at ~12:03pm CT, and each
# caption carries 2-3 named events) needs ~2.7KB of JSON for 12 posts, and 1500
# tokens truncated it mid-object. Truncated JSON did not degrade gracefully - it
# failed json.loads(), _extract_with_llm returned None, and the whole venue silently
# fell back to the far blunter regex path. That is how the good extractor's output
# ("Monday Movie Night", "Gaymer Night", "Leather Night") got replaced by the
# regex path's guesses without anything looking broken in the log.
MAX_EXTRACT_TOKENS = 4000

# Emoji / pictographic symbol ranges + ZWJ / variation selectors. Stripped from
# caption-derived event names so the regex fallback path is as clean as the LLM path.
_EMOJI_RX = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF\U0000FE00-\U0000FE0F\U0000200D]",
    flags=re.UNICODE,
)

# A caption must look like an event announcement before we bother date-parsing it.
EVENT_KEYWORDS = [
    "join us", "come out", "tonight", "this week", "this saturday", "this friday",
    "this sunday", "this thursday", "tickets", "doors", "doors open", "rsvp",
    "party", "drag", "watch party", "show", "fashion", "ball", "summit", "festival",
    "fundraiser", "market", "bingo", "happy hour", "dance", "live", "performance",
    "lineup", "line up", "presale", "pre-sale", "celebration", "yoga", "brunch",
    "tour", "bash", "@", "pm", "doors @",
]

# ── Configured IG-only orgs ──────────────────────────────────────────────────
# username      : IG handle without the @
# source_name   : must also be added to config.LGBTQ_SOURCES to be trusted
# default_venue : used when a caption names no explicit location (NEVER fabricate
#                 a street address — these orgs rove)
# priority      : 1 = primary LGBTQ org (fun one-offs, good featured/EOTW)
# blurb         : short event-facing description suffix (no em dashes — preflight bans)
ORGS: List[Dict] = [
    {   # PFLAG Tulsa - cross-promo partner (Nicole, 2026-07-07). Meetings are
        # first Saturdays (manual_events carries those); IG catches their
        # special events, fundraisers, and education nights.
        "username": "pflagtulsa",
        "alt_usernames": [],
        "source_name": "pflag_ig",
        "default_venue": "Youth Services of Tulsa, 311 S Madison Ave",
        "priority": 1,
        "blurb": ("PFLAG Tulsa is parents, families, and allies showing up for 2SLGBTQIA+ "
                  "Tulsans: monthly meetings, education, and advocacy. Everyone is welcome. "
                  "Details at tulsapflag.org and @pflagtulsa."),
    },

    {   # TCC Pride, the LGBTQ+ student org at Tulsa Community College
        # (added 2026-08-10 per William). Their events do NOT appear on the
        # college's own calendar: all 323 events on calendar.tulsacc.edu had
        # zero LGBTQ keyword hits when this was wired, so Instagram is the
        # only feed. Verified live: 12 posts read, carrying a real dated event
        # (Aug 27, 11:30am-1pm, Metro Campus 2nd Floor Student Union).
        # Campus events are open to the public and skew young/first-timers,
        # exactly the shy-introvert reader the site writes for.
        "username": "tcc_pride",
        "alt_usernames": ["tccpride"],
        "source_name": "tcc_pride",
        "default_venue": "TCC Metro Campus, 909 S Boston Ave",
        "priority": 2,
        "blurb": "TCC Pride is the LGBTQ+ student organization at Tulsa "
                 "Community College, open to everyone on campus and a soft "
                 "landing if you are new to queer Tulsa. Details on Instagram "
                 "@tcc_pride.",
    },
    {
        "username": "upflykai",
        "source_name": "klassic",
        "default_venue": "Tulsa (location by DM, see @upflykai)",
        "priority": 1,
        "blurb": "Black queer Tulsa events collective (KLASSIC). "
                 "Details and location on Instagram @upflykai.",
    },
    {
        "username": "goff_fest",
        "source_name": "goff_center",
        "default_venue": "Tulsa (see @goff_fest for venue)",
        "priority": 2,
        "blurb": "Goff Center / Goff Fest. Architecture, art, and Pride programming "
                 "celebrating Tulsa's queer cultural legacy. Details on Instagram @goff_fest.",
    },
    # Gay bars (added 2026-06-12). Their websites are DNS-dead; IG is the only
    # place they announce events. W24 missed every Eagle/Majestic Pride event
    # because nothing scraped them.
    {
        "username": "tulsaeagle",
        # The Eagle's handle has been documented both ways (config comment says
        # @tulsaeagleok). Try both so a rename/typo never silently zeroes the
        # main gay bar — the W24 Pride miss class of failure.
        "alt_usernames": ["tulsaeagleok"],
        "source_name": "tulsa_eagle_ig",
        # WHY THIS VENUE YIELDS ALMOST NOTHING FOR A WEEKLY DECK
        # (SETTLED 2026-09-09. Supersedes the 2026-08-20 / gap G513 diagnosis that
        # used to sit here, which said the Eagle's programming was "RECURRING
        # WEEKLY NIGHTS rather than dated one-off events" and that "an undated
        # 'every Friday' caption is correctly dropped". That was WRONG on the facts
        # and it sent three sessions looking for an extraction bug.)
        #
        # MEASURED against 14 real @tulsaeagle captions, 2026-08-27..09-08, read
        # from the venue's own post pages and kept verbatim in
        # tests/fixtures/tulsa_eagle_ig_captions_2026-09-09.json:
        #   - Extraction WORKS. 22 events came out, correctly dated and correctly
        #     named ("Monday Movie Night", "Gaymer Night", "Underwear Night",
        #     "Leather Night", "Tulsa Eagle Tuesday Karaoke", "Thirsty Thursday").
        #   - _within_announce_window drops NONE of them. It was the prime suspect
        #     and it is exonerated: every gap is 0 days. Do NOT loosen
        #     MAX_ANNOUNCE_GAP_DAYS "to make the Eagle work".
        #   - Nothing is undated. Every caption is a day-of post.
        #
        # THE REAL CAUSE is a LOOKAHEAD MISMATCH, not a parsing failure. The Eagle
        # posts ONCE A DAY, ON THE DAY, at ~12:03pm CT - all 12 image posts land
        # inside a two-minute window at 17:03 UTC, which is a scheduled post. So it
        # gives ZERO days of forward notice. A weekly deck built Monday morning can
        # therefore only ever see the days that have already happened, and on a
        # Monday-before-12:03pm run it sees NOTHING. That is arithmetic, not a bug:
        # in-week yield from this venue == days already elapsed this week.
        #
        # THE FIX, and it is already in place: the Eagle's weekly nights now live in
        # scraper/recurring.py, confirmed the way that file demands - the venue's
        # OWN posts showing the same night at the same time in TWO separate weeks,
        # with the two confirming post URLs recorded per entry. Five nights met that
        # bar (Mon Movie Night + Gaymer Night, Tue Tea Party + Karaoke, Fri Happy
        # Hour); the once-seen ones and the Sat/Sun 10pm parties, whose NAME changes
        # every week, deliberately did not and must keep coming from this live scrape.
        # This module still earns its keep: it is what catches the one-off (a Labor
        # Day cookout, a comedy show) and what keeps the recurring ledger fresh.
        "default_venue": "Tulsa Eagle, 1338 E 3rd St",
        "priority": 2,
        "blurb": "Tulsa Eagle, Tulsa's levi-leather LGBTQ+ bar. "
                 "Details on Instagram @tulsaeagle.",
    },
    {
        "username": "clubmajestictulsa",
        "alt_usernames": ["majestictulsa", "clubmajestic"],
        "source_name": "club_majestic_ig",
        "default_venue": "Club Majestic, 124 N Boston Ave",
        "priority": 2,
        "blurb": "Club Majestic, Tulsa's flagship LGBTQ+ nightclub downtown. "
                 "Details on Instagram @clubmajestictulsa.",
    },
    {
        "username": "tulsaybr",
        # @imvalpal added 2026-06-24 per William: Val Pal books/promotes YBR's
        # events and posts them on her IG, often before the venue account does, so
        # she's a reliable second feed for YBR nights. Handles are walked in order
        # until one returns posts, so this also covers a venue-account rename.
        "alt_usernames": ["ybrtulsa", "imvalpal"],
        "source_name": "ybr_ig",
        "default_venue": "Yellow Brick Road, 2630 E 15th St",
        # priority 1 (top tier, 2026-06-20 per William): YBR is Tulsa's only lesbian
        # bar and one of the last in the US — under-loved by the gay-guy crowd, so we
        # FEATURE it and frame it as a welcome-all space every chance we get.
        "priority": 1,
        "blurb": "Yellow Brick Road is Tulsa's only lesbian bar and one of the last "
                 "left in the whole country, and here's the thing the boys keep "
                 "missing: everyone is welcome at the cave, not just the girls. Roll "
                 "up, the whole community is invited. Details on Instagram @tulsaybr.",
    },
    {
        # DVL Club & Lounge (added 2026-06-18). Woman-owned LGBTQ+ bar in the
        # Blue Dome District. Its dvltulsa.com calendar is JS-rendered (unreadable
        # by the static scraper); FB events are wired in facebook_events.py, and
        # this IG path adds a second, durable feed for its queer socials/parties.
        "username": "dvltulsa",
        "source_name": "dvl_ig",
        "default_venue": "DVL Club & Lounge, 302 S Frankfort Ave",
        "priority": 1,
        "blurb": "DVL Club & Lounge, the woman-owned LGBTQ+ bar in Tulsa's Blue "
                 "Dome District. Details on Instagram @dvltulsa.",
    },
    {
        # HotMess Sports Tulsa (added 2026-07-01 per William: "these are cool").
        # LGBTQ+ rec sports league (kickball, dodgeball, sand volleyball, cornhole,
        # bowling, tennis, flag football). Their hotmesssports.com/tulsa site is a
        # JS-rendered SportsEngine page that lists league SEASONS, not single dated
        # events, so the static HotMessSportsScraper (specific_orgs.py) returns 0.
        # The Tulsa IG @hotmesssportstulsa is where they post the actual dated game
        # days, socials, tournaments, and registration pushes. IMPORTANT: use the
        # Tulsa handle, NOT the national @hotmesssports (that mixes every city's
        # events and returns nothing Tulsa-dated). source_name already trusted in
        # config.LGBTQ_SOURCES.
        "username": "hotmesssportstulsa",
        "source_name": "hotmess_sports",
        "default_venue": "Various venues, Tulsa (see @hotmesssportstulsa)",
        "priority": 1,
        "blurb": "HotMess Sports Tulsa, the LGBTQ+ rec sports league (kickball, "
                 "dodgeball, sand volleyball, and more). All skill levels welcome, "
                 "the whole point is showing up and having a blast. Details and "
                 "registration on Instagram @hotmesssportstulsa.",
    },
]


class InstagramOrgScraper(BaseScraper):
    """Read one org's public IG posts and extract this-week dated events."""

    def __init__(self, org: Dict):
        super().__init__()
        self.username = org["username"]
        # Primary handle first, then any documented alternates. Every fetch path
        # walks this list until one returns posts, so a renamed/mistyped handle
        # degrades to the alternate instead of a silent 0 events.
        self.usernames = [org["username"]] + [u for u in org.get("alt_usernames", []) if u]
        self.source_name = org["source_name"]
        self.default_venue = org.get("default_venue", f"Tulsa (see @{org['username']})")
        self.priority = int(org.get("priority", 2))
        self.blurb = org.get("blurb", f"Event from @{org['username']}.")
        self.profile_url = f"https://www.instagram.com/{self.username}/"

    # ── week helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _week_range():
        today = datetime.now()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        return (monday.replace(hour=0, minute=0, second=0, microsecond=0),
                sunday.replace(hour=23, minute=59, second=59, microsecond=999999))

    @staticmethod
    def _clean_name(name: str) -> str:
        """Strip em dashes (banned in William's voice / blocked by preflight),
        emoji, and hashtags, and collapse whitespace so caption-derived names are
        safe for slides + website even on the regex fallback path."""
        if not name:
            return ""
        name = name.replace("—", ", ").replace("–", "-")  # em/en dash
        name = name.replace("“", '"').replace("”", '"')   # curly quotes
        name = name.replace("‘", "'").replace("’", "'")
        name = _EMOJI_RX.sub("", name)                    # drop emoji/symbols
        name = re.sub(r"#\w+", "", name)                  # drop trailing hashtags
        return re.sub(r"\s+", " ", name).strip(" ,-")

    # Event-type cues → a clean display label. Ordered: first match wins, so list
    # the more specific phrases before the generic ones. Lets the regex path emit
    # "Dance Party at YBR" instead of the raw hype header "HEADS UP". (2026-06-20)
    #
    # MATCHED ON WORD BOUNDARIES since 2026-09-09, and the bare "brunch" cue no
    # longer says "Drag". Both are the same real defect, caught on live Tulsa Eagle
    # captions: the 2026-08-30 post ("MEGAN opens today @2 to get you started after
    # your brunchin & lunchin !!!") announces no drag brunch and no brunch at all,
    # yet substring matching found "brunch" inside "brunchin" and the regex path
    # emitted "Drag Brunch at Tulsa Eagle" - a fabricated event, on the public deck,
    # for a night the bar was running nothing of the kind. A cue may only fire on a
    # whole word, and only "drag brunch"/"drag show"/"drag" may ever print "Drag".
    _EVENT_TYPE_CUES = [
        ("drag brunch", "Drag Brunch"), ("drag show", "Drag Show"),
        ("drag", "Drag Night"),
        ("b&b", "B&B Dance Party"), ("dance party", "Dance Party"),
        ("dance floor", "Dance Party"), ("dance", "Dance Night"),
        ("talent", "Talent Night"), ("open mic", "Open Mic"),
        ("karaoke", "Karaoke Night"), ("bingo", "Bingo Night"),
        ("trivia", "Trivia Night"), ("watch party", "Watch Party"),
        ("happy hour", "Happy Hour"), ("brunch", "Brunch"),
        ("tea party", "Tea Party"), ("tea time", "Tea Time"),
        ("class", "Craft Class"), ("market", "Market"),
        ("fundraiser", "Fundraiser"), ("pride", "Pride Party"),
        ("party", "Party"), ("show", "Live Show"),
    ]
    # Same cues, precompiled as whole-word patterns (see the note above).
    # A trailing PLURAL is still the same cue ("see your talents!" is a talent
    # night), so an optional s/es is allowed - but no "-ing"/"-in" suffix, which is
    # what let "brunchin & lunchin" read as a brunch in the first place.
    _EVENT_TYPE_RX = [(re.compile(r"(?<!\w)" + re.escape(cue) + r"(?:e?s)?(?!\w)", re.I), label)
                      for cue, label in _EVENT_TYPE_CUES]
    # Lines that are pure hype banners, never the real event name.
    #
    # GREETING BANNERS ADDED 2026-09-09. The old pattern was anchored ^...$ on the
    # whole line, so it only caught a line that was NOTHING but hype ("HEADS UP").
    # Every Tulsa Eagle post opens with a greeting that carries trailing words -
    # "HAPPY MONDAY DIRTY BIRDS !!!", "Happy Thursday Boys and Girls !!!!", "Happy
    # HumpDay you Dirty Birds !! !", "ITS SUNDAYFUNDAY DIRTY BIRDIES !!!!!",
    # "Welcome to the weekend Dirty Birds !!!" - so none of them matched, and on
    # 2026-09-09 three of the Eagle's twelve regex-path events were named after the
    # greeting instead of the event. One of those ("HAPPY MONDAY DIRTY BIRDS !!!")
    # was in-week and would have shipped to the deck as an event title.
    # _HYPE_RX stays whole-line (a line that is nothing but hype);
    # _HYPE_PREFIX_RX catches a greeting that OPENS the line, whatever follows it.
    _HYPE_RX = re.compile(
        r"^\W*(heads?\s*up|this\s+(mon|tues?|wed|thurs?|fri|sat|sun)\w*|tonight|"
        r"tomorrow|today|come\s+(get|on)|reminder|now\s+open|attention|psa|"
        r"this\s+week(end)?|next\s+(week|sun\w*|sat\w*)|mark\s+your)\W*$", re.I)
    _HYPE_PREFIX_RX = re.compile(
        r"^\W*("
        r"(happy|its|it's|welcome\s+to)\b"
        r"|(good\s+)?(morning|afternoon|evening)\b"
        r"|hey+\b|hi\b|hello\b|yo\b"
        r"|(mon|tues?|wed|wednes|thurs?|thur|fri|satur|sun)day\s*funday\b"
        r"|humpday\b"
        r")", re.I)

    @classmethod
    def _venue_short(cls, venue: str) -> str:
        """First clause of a venue string ('Yellow Brick Road, 2630 ...' -> 'YBR')."""
        head = (venue or "").split(",")[0].strip()
        if "yellow brick" in head.lower():
            return "YBR"
        return head

    @classmethod
    def _derive_event_name(cls, caption: str, venue: str) -> str:
        """Turn a bar caption into a presentable event name.

        Prefers an event-type cue ('Dance Party at YBR') over the raw first line,
        because bar posts open with an emoji hype banner ('HEADS UP', 'THIS
        SATURDAY'), not the event title. Falls back to the first non-hype line.
        """
        venue_short = cls._venue_short(venue)
        # 1. The venue's OWN name for the night, when the caption states one.
        named = cls._named_event(caption)
        if named:
            return named
        # 2. An event-type cue, matched on whole words only.
        for rx, label in cls._EVENT_TYPE_RX:
            if rx.search(caption):
                return f"{label} at {venue_short}" if venue_short else label
        # 3. No cue - first substantive line that actually reads as a title.
        #    A line of staff-shift prose ("ISAAC opens today @2 to get your week
        #    started with $5 well cocktails all day") is NOT an event name, and
        #    printing one on the deck looks worse than the generic venue label.
        #    Added 2026-09-09: four of the Eagle's twelve captions reached this
        #    fallback and shipped that sentence as the event title.
        for line in caption.split("\n"):
            stripped = line.strip()
            cleaned = cls._clean_name(line)
            if (cleaned and len(cleaned) >= 4
                    and not cls._HYPE_RX.match(stripped)
                    and not cls._HYPE_PREFIX_RX.match(stripped)
                    and not cls._NOT_A_NAME_RX.search(cleaned)):
                return cleaned[:80]
        return f"Event at {venue_short}" if venue_short else "Community Event"

    # A named night immediately before an "@<time>" marker. Bar captions are
    # written this way ("Monday Movie Night @7", "TULSA EAGLE BINGO @3", "LEATHER
    # NIGHT @10 w/DJ HAZE", "SPECIAL EDITION: SUNDAY KARAOKE @6"), and the name the
    # venue chose beats any label this module could infer. Added 2026-09-09 after
    # the cue table reduced every one of those to a generic "Karaoke Night at Tulsa
    # Eagle" / "Party at Tulsa Eagle" - correct, but not what the bar called it.
    # Two orders occur in real bar captions, so both are matched:
    #   NAME then time  - "Monday Movie Night @7", "TULSA EAGLE BINGO @3"
    #   time then NAME  - "ISAAC has got you @8 for Underwear Night"
    _NAMED_AT_TIME_RX = re.compile(
        r"(?:^|[\n!?.,]|\bfor\b|\bthen\b)\s*"
        r"(?P<name>[A-Za-z][A-Za-z0-9'&:/\-]*(?:[ ]+[A-Za-z0-9'&:/\-]+){0,5}?)"
        r"\s*@\s*\d{1,2}")
    _NAMED_AFTER_TIME_RX = re.compile(
        r"@\s*\d{1,2}(?::\d{2})?\s*(?:[ap]\.?m\.?)?\s*for\s+"
        r"(?P<name>[A-Za-z][A-Za-z0-9'&:/\-]*(?:[ ]+[A-Za-z0-9'&:/\-]+){0,5})",
        re.I)
    # Words that mean the phrase is staff/shift prose, not an event title
    # ("MEGAN opens today @2", "NATHAN has you all night long").
    #
    # NOTE (2026-09-09): "night", "day", "all" and "long" were in this list on the
    # first pass and that was wrong - "night" is the single commonest word in a real
    # bar-night title, so banning it threw away "Monday Movie Night", "Gaymer
    # Night", "Underwear Night" and "Leather Night", i.e. exactly the names this
    # function exists to find. The filler phrases are banned as PHRASES instead.
    _NOT_A_NAME_RX = re.compile(
        r"\b(opens?|opening|has|have|had|got|takes?|taking|starts?|starting|"
        r"come|comes|hang|gets?|keeps?|you|your|yours|us|we|our|"
        r"today|tonight|tomorrow|until|w/|sponsored)\b"
        r"|\ball\s+(night|day)\b", re.I)

    # Filler that a caption wraps around the real title. Cut, don't reject: the
    # 2026-09-09 first pass threw away "Underwear Night" because the regex span ran
    # on into "all night long", and printed "STEVEN and JUSTIN for LEATHER NIGHT"
    # because the staff names sat in front of it.
    _TRIM_AFTER_LAST = (" for ",)                     # keep what follows
    _TRIM_BEFORE = (" then ", " with ", " w/", " all night", " all day",
                    " until ", " sponsored", " to get", " to keep")
    _LEAD_FILLER = ("the ", "a ", "an ", "our ", "your ", "this ")

    @classmethod
    def _trim_title(cls, cand: str) -> str:
        """Strip caption filler from around a candidate title."""
        out = (cand or "").strip()
        for sep in cls._TRIM_AFTER_LAST:
            i = out.lower().rfind(sep)
            if i != -1:
                out = out[i + len(sep):]
        low = out.lower()
        cut = len(out)
        for sep in cls._TRIM_BEFORE:
            i = low.find(sep)
            if i != -1:
                cut = min(cut, i)
        out = out[:cut].strip()
        changed = True
        while changed:
            changed = False
            for lead in cls._LEAD_FILLER:
                if out.lower().startswith(lead):
                    out = out[len(lead):].lstrip()
                    changed = True
        return out.replace(" :", ":").strip(" ,-:")

    @classmethod
    def _looks_like_a_title(cls, cand: str) -> bool:
        """True if `cand` reads as an event title rather than caption prose."""
        if not cand or len(cand) < 4 or " " not in cand:
            return False          # single word / too short to be a title
        if cls._NOT_A_NAME_RX.search(cand):
            return False          # staff-shift prose, not a title
        if cls._HYPE_RX.match(cand) or cls._HYPE_PREFIX_RX.match(cand):
            return False          # greeting banner
        return True

    @classmethod
    def _named_event(cls, caption: str) -> str:
        """The venue's own name for the night, or "" when none is stated."""
        for rx in (cls._NAMED_AT_TIME_RX, cls._NAMED_AFTER_TIME_RX):
            for m in rx.finditer(caption or ""):
                cand = cls._trim_title(cls._clean_name(m.group("name")))
                if cls._looks_like_a_title(cand):
                    return cand[:80]
        return ""

    @classmethod
    def _in_week(cls, date_str: str) -> bool:
        if not date_str:
            return False
        try:
            dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        except ValueError:
            return False
        monday, sunday = cls._week_range()
        return monday <= dt <= sunday

    # ── auth-free public fetch (primary) ────────────────────────────────────────
    # ── Graph API business_discovery (official, credentialed, NOT rate-limited) ──
    def _fetch_via_graph(self) -> List[Dict]:
        """Read a venue's recent posts through Meta's own business_discovery edge.

        WHY (2026-09-07). On W37 all NINE venue Instagram accounts returned zero
        posts: the logged-out public endpoint answered HTTP 429 for every handle,
        and the instagrapi session fallback was dead ("No @tulsagays IG session at
        ~/.credentials/ig_settings_tulsagays.json"). Both tiers down means the gay
        bars - who publish ONLY on Instagram - contributed nothing at all, which
        is why that Monday's deck had, in William's words, "nothing really gay on
        them" for half the week. It also starved the YBR partner rule of its only
        approved source, so the deck fell back to a stale flyer and a 2023
        Facebook event, and THAT is what blocked the post entirely.

        business_discovery is a third path that shares no failure mode with the
        other two: it is the documented Graph API edge, authenticated with the
        TulsaGays page token we already hold for posting, and it needs no scraping
        session and no 2FA. Measured the same morning the other two were dead, it
        returned fresh posts for @tulsaeagle (newest that day), @dvltulsa,
        @clubmajestictulsa and @pflagtulsa.

        LIMIT: business_discovery only resolves BUSINESS/CREATOR accounts. A
        personal account (YBR's @tulsaybr, at time of writing) answers code 110
        "Invalid user id", so it still depends on the other tiers. That is a real
        gap, not a bug here - and for YBR specifically the partner rule already
        says the right answer is to under-promote rather than invent an event.
        """
        import os as _os
        import json as _json
        import urllib.parse as _up
        import urllib.request as _ur

        token = _os.environ.get("TULSAGAYS_PAGE_ACCESS_TOKEN", "")
        ig_id = ""
        try:
            cfg_path = Path(__file__).resolve().parent.parent / "meta_api_config.json"
            ig_id = str(_json.loads(cfg_path.read_text(encoding="utf-8"))
                        .get("instagram_business_account_id") or "")
        except Exception:
            ig_id = ""
        if not token or not ig_id:
            return []

        for user in self.usernames:
            fields = (f"business_discovery.username({user})"
                      f"{{username,media.limit({POSTS_TO_SCAN})"
                      f"{{caption,timestamp,permalink}}}}")
            url = (f"https://graph.facebook.com/v21.0/{ig_id}?"
                   + _up.urlencode({"fields": fields, "access_token": token}))
            try:
                raw = _ur.urlopen(url, timeout=25).read()
                media = ((_json.loads(raw).get("business_discovery") or {})
                         .get("media") or {}).get("data") or []
            except Exception as e:
                # code 110 = not a business/creator account. Normal for some
                # venues; try the next handle rather than treating it as an error.
                logger.debug("[%s] business_discovery @%s unavailable: %s",
                             self.source_name, user, str(e)[:80])
                continue

            posts = []
            for m in media:
                caption = (m.get("caption") or "").strip()
                if not caption:
                    continue
                posts.append({
                    "caption": caption,
                    "url": m.get("permalink") or self.profile_url,
                    "posted_on": (m.get("timestamp") or "")[:10],
                })
            if posts:
                logger.info("[%s] business_discovery @%s returned %d captioned posts",
                            self.source_name, user, len(posts))
                return posts
        return []

    def _fetch_public(self) -> List[Dict]:
        """Read recent posts via Instagram's public web-profile JSON.

        Walks every candidate handle (primary + alts) and returns the first that
        yields captioned posts, so a renamed/mistyped handle never silently
        zeroes the venue. No login / session / credentials.
        """
        for user in self.usernames:
            posts = self._fetch_public_one(user)
            if posts:
                if user != self.username:
                    logger.info("[%s] primary @%s returned nothing — used alt handle @%s",
                                self.source_name, self.username, user)
                return posts
        return []

    def _fetch_public_one(self, user: str) -> List[Dict]:
        """Fetch one handle's recent captioned posts, or [] on any failure."""
        import requests
        headers = {
            "User-Agent": _UA,
            "X-IG-App-ID": IG_WEB_APP_ID,
            "Accept": "*/*",
            "Referer": f"https://www.instagram.com/{user}/",
        }
        try:
            r = requests.get(WEB_PROFILE_URL.format(user=user),
                             headers=headers, timeout=20)
        except Exception as e:
            logger.warning("[%s] @%s public profile request failed: %s %s",
                           self.source_name, user, type(e).__name__, str(e)[:120])
            return []
        if r.status_code != 200:
            logger.warning("[%s] @%s public profile HTTP %s (logged-out endpoint may be "
                           "rate-limited) — will try next handle / session fallback",
                           self.source_name, user, r.status_code)
            return []
        try:
            user = (r.json().get("data", {}) or {}).get("user") or {}
            edges = (user.get("edge_owner_to_timeline_media") or {}).get("edges", [])
        except Exception as e:
            logger.warning("[%s] public profile JSON parse failed: %s",
                           self.source_name, type(e).__name__)
            return []

        posts = []
        for e in edges[:POSTS_TO_SCAN]:
            node = e.get("node", {}) or {}
            cap_edges = (node.get("edge_media_to_caption") or {}).get("edges", [])
            caption = cap_edges[0]["node"]["text"].strip() if cap_edges else ""
            if not caption:
                continue
            code = node.get("shortcode") or node.get("code")
            post_url = f"https://www.instagram.com/p/{code}/" if code else self.profile_url
            ts = node.get("taken_at_timestamp")
            posted_on = ""
            if ts:
                try:
                    posted_on = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
                except (ValueError, OverflowError, OSError):
                    posted_on = ""
            posts.append({"caption": caption, "url": post_url, "posted_on": posted_on})

        logger.info("[%s] public endpoint returned %d captioned posts",
                    self.source_name, len(posts))
        return posts

    # ── instagrapi session (read-only fallback, never a fresh login) ────────────
    def _fetch_via_session(self) -> List[Dict]:
        cl = self._client()
        if cl is None:
            return []
        for user in self.usernames:
            try:
                uid = cl.user_id_from_username(user)
                medias = cl.user_medias(uid, amount=POSTS_TO_SCAN)
            except Exception as e:
                logger.warning("[%s] @%s session fetch failed: %s %s",
                               self.source_name, user, type(e).__name__, str(e)[:160])
                continue
            posts = []
            for m in medias:
                caption = (getattr(m, "caption_text", "") or "").strip()
                if not caption:
                    continue
                code = getattr(m, "code", None)
                post_url = f"https://www.instagram.com/p/{code}/" if code else self.profile_url
                taken = getattr(m, "taken_at", None)
                posted_on = taken.strftime("%Y-%m-%d") if isinstance(taken, datetime) else ""
                posts.append({"caption": caption, "url": post_url, "posted_on": posted_on})
            if posts:
                if user != self.username:
                    logger.info("[%s] session: primary @%s empty — used alt @%s",
                                self.source_name, self.username, user)
                logger.info("[%s] session fallback returned %d captioned posts",
                            self.source_name, len(posts))
                return posts
        return []

    def _client(self):
        if not SETTINGS_FILE.exists():
            logger.warning(
                "[%s] No @tulsagays IG session at %s — run scripts/ig_login_api.py "
                "once to enable session fallback.", self.source_name, SETTINGS_FILE,
            )
            return None
        try:
            from instagrapi import Client
        except ImportError:
            logger.warning("[%s] instagrapi not installed — cannot use session fallback.",
                           self.source_name)
            return None
        cl = Client()
        try:
            cl.load_settings(str(SETTINGS_FILE))
            cl.get_timeline_feed()  # cheap authenticated call to validate the session
            return cl
        except Exception as e:
            logger.warning(
                "[%s] @tulsagays IG session expired (%s) — re-auth once with "
                "scripts/ig_login_api.py.", self.source_name, type(e).__name__,
            )
            return None

    def _fetch_via_web(self) -> List[Dict]:
        """Tier 3 (2026-07-06): logged-in WEB session in the automation Chrome
        profile. The only tier that reaches personal accounts (@tulsaybr,
        @imvalpal) now that the public endpoint 429s and the instagrapi login is
        bloks-walled. One-time human setup: tools/ig_profile_login.py."""
        try:
            from scraper import instagram_web
            return instagram_web.posts_for(self.source_name, self.usernames)
        except Exception as e:
            logger.warning("[%s] web-session tier failed: %s %s",
                           self.source_name, type(e).__name__, str(e)[:120])
            return []

    def scrape(self) -> List[Dict]:
        # WEB-SESSION FIRST (reordered 2026-07-20). The logged-in web session is
        # the authenticated path and is NOT rate-limited the way the logged-out
        # public endpoint is — hammering the public endpoint across every venue in
        # a full scrape is exactly what 429'd it to zero and silently dropped all
        # gay-venue events for months. Try the reliable tier first; only fall back
        # to the public/instagrapi tiers if the web session is down.
        # GRAPH API FIRST (added 2026-09-07). business_discovery is the only tier
        # that is both credentialed and officially supported, so it does not 429
        # and does not expire the way a scraped session does. On the morning both
        # other tiers were dead it was the only one returning posts at all.
        posts = self._fetch_via_graph()
        if not posts:
            posts = self._fetch_via_web()
        if not posts:
            posts = self._fetch_public()
        if not posts:
            posts = self._fetch_via_session()
        # Record how many posts the fetch tiers actually returned so scrape() can
        # tell a genuine "no dated events this week" (posts>0, events==0) apart
        # from a silent fetch failure (posts==0 = rate-limited/blocked/session
        # dead). The latter must never be mistaken for an empty week.
        self.last_posts_count = len(posts or [])
        if not posts:
            logger.info("[%s] No captioned posts from any path — 0 events.",
                        self.source_name)
            return []

        events = self._extract_with_llm(posts)
        if events is None:
            events = self._extract_with_regex(posts)

        # Guard 1 — announcement window: an event may not be dated more than
        # MAX_ANNOUNCE_GAP_DAYS after (or before) the post that announced it. Bars
        # post about events close to when they happen; a stale post's relative
        # weekday ("FRIDAY") must never be projected weeks forward onto the current
        # week. This is the 2026-07-27 YBR fix: a 2026-07-08 "DJ Kylie FRIDAY" post
        # was being published as this Friday (23 days later). Events with no known
        # source-post date skip this check (absolute-dated captions still rely on
        # the in-week filter below).
        fresh = []
        for e in events:
            if self._within_announce_window(e.get("date", ""), e.get("_src_posted_on", "")):
                fresh.append(e)
        dropped = len(events) - len(fresh)

        # Guard 2 — caption support: the announcing post must actually claim the
        # date. Catches an LLM-invented date that the window and the week filter
        # both wave through (the 2026-09-09 "Labor Day Cookout" mis-date).
        supported = []
        for e in fresh:
            if self._date_supported_by_caption(e.get("date", ""),
                                               e.get("_src_caption", ""),
                                               e.get("_src_posted_on", "")):
                supported.append(e)
            else:
                logger.info("[%s] dropped unsupported date %s (post %s): %s",
                            self.source_name, e.get("date"), e.get("_src_posted_on"),
                            str(e.get("name"))[:50])
        unsupported = len(fresh) - len(supported)
        for e in supported:
            e.pop("_src_posted_on", None)
            e.pop("_src_caption", None)

        # Guard 3 — keep only events inside the current Mon–Sun week.
        in_week = [e for e in supported if self._in_week(e.get("date", ""))]
        logger.info("[%s] %d candidate events, %d dropped stale-projection, "
                    "%d dropped unsupported-date, %d in current week",
                    self.source_name, len(events), dropped, unsupported, len(in_week))
        return in_week

    # An event dated more than this many days after its announcing post is treated
    # as unpublishable.
    #
    # Raised 10 -> 31 on 2026-08-10. The 10-day value was a BLUNT PROXY for the
    # forward-dating bug (a stale post's bare "FRIDAY" projected onto the current
    # week — the 2026-07-27 YBR fix). It limited the damage by refusing far dates,
    # but it also silently deleted every LEGITIMATE advance announcement: Club
    # Majestic's "THURSDAY AUGUST 27TH ... Tulsa Supreme Beach Party", posted
    # 2026-08-09 with an EXPLICIT date, is 18 days out and was dropped here. Worse,
    # it could never recover — by the time 8/27's own week came around, the
    # announcing post was 18 days old and still outside the window, so a marquee
    # event was permanently invisible. That is a supply bug of exactly the kind
    # that starved W33's Wednesday.
    #
    # The CAUSE is now fixed where it belongs, in the extraction prompt: a bare
    # weekday resolves to the first such day ON OR AFTER the post date, so it can
    # land at most ~7 days out and can no longer be projected into the current
    # week. Guard 2 (_in_week) still restricts what actually ships. So this window
    # only needs to be loose enough for real venue lead time (bars routinely
    # announce 3-4 weeks ahead) while still rejecting a date BEFORE the post.
    # Locked by tests/test_pipeline.py::test_ig_date_anchor_contract — if you
    # tighten this, the anchoring rules in _extract_with_llm are what keeps the
    # deck safe, so do not remove them.
    MAX_ANNOUNCE_GAP_DAYS = 31

    # Month names for the explicit-date test below.
    _MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
               "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

    @classmethod
    def _date_supported_by_caption(cls, event_date: str, caption: str,
                                   posted_on: str) -> bool:
        """True if the announcing caption can actually support `event_date`.

        WHY (2026-09-09). The LLM tier is much better than the regex tier at
        NAMING events, and it will also quietly invent a date the caption never
        states. Measured on the Tulsa Eagle's own posts: the 2026-09-06 caption
        ("ITS SUNDAYFUNDAY ... NATHAN & JUSTIN open @2 to get you ready for the
        LABOR DAY COOKOUT @4") describes a Sunday-afternoon cookout, and the model
        dated it 2026-09-07 because that was Labor Day. Both other guards passed it
        (gap +1 is inside the announce window, and 09-07 is in the current week), so
        a cookout that happened Sunday would have shipped to the deck as a Monday
        event. The 2026-09-07 post itself names only Movie Night and Gaymer Night,
        which is the contradiction that gives this away.

        A date is supported when the caption gives a reason to believe it:
          - it IS the post date (a day-of post, which is how bars post),
          - the caption says "tomorrow" and it is the day after the post,
          - the caption names that weekday, or
          - the caption carries an explicit month/day that resolves to it.
        Anything else is a date the post does not claim, so it is dropped. A
        holiday NAME is deliberately not accepted as a date: "LABOR DAY COOKOUT"
        says what the party is about, not which day it runs.
        """
        if not event_date:
            return False
        if not posted_on:
            return True          # can't judge without an anchor; other guards apply
        try:
            ed = datetime.strptime(event_date[:10], "%Y-%m-%d")
            pd = datetime.strptime(posted_on[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return True
        if ed.date() == pd.date():
            return True
        low = (caption or "").lower()
        if (ed - pd).days == 1 and "tomorrow" in low:
            return True
        # The caption names the event's weekday ("THIS SATURDAY", "SUNDAYFUNDAY").
        wd = ed.strftime("%A").lower()                     # e.g. "saturday"
        if wd in low or wd[:3] in re.findall(r"[a-z]{3,}", low):
            return True
        # An explicit month/day in the caption: "8/15", "AUGUST 27TH", "27 Aug".
        for mm, dd in re.findall(r"(\d{1,2})\s*/\s*(\d{1,2})", low):
            if int(mm) == ed.month and int(dd) == ed.day:
                return True
        for mon, dd in re.findall(r"([a-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?", low):
            if cls._MONTHS.get(mon[:3]) == ed.month and int(dd) == ed.day:
                return True
        for dd, mon in re.findall(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3,9})", low):
            if cls._MONTHS.get(mon[:3]) == ed.month and int(dd) == ed.day:
                return True
        return False

    @classmethod
    def _within_announce_window(cls, event_date: str, posted_on: str) -> bool:
        """True if event_date is plausibly announced by a post on posted_on:
        within [posted_on - 1 day, posted_on + MAX_ANNOUNCE_GAP_DAYS]. Unknown
        posted_on -> True (can't judge; other guards apply)."""
        if not posted_on or not event_date:
            return True
        try:
            ed = datetime.strptime(event_date[:10], "%Y-%m-%d")
            pd = datetime.strptime(posted_on[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return True
        gap = (ed - pd).days
        return -1 <= gap <= cls.MAX_ANNOUNCE_GAP_DAYS

    # ── LLM extraction (preferred) ──────────────────────────────────────────────
    def _extract_with_llm(self, posts: List[Dict]) -> Optional[List[Dict]]:
        """Return events parsed by Claude, or None if no key / call failed."""
        import os
        if not config.ANTHROPIC_API_KEY and not os.environ.get("WORKER_API_KEY"):
            return None  # no LLM available at all -> regex fallback

        monday, sunday = self._week_range()
        today = datetime.now().strftime("%Y-%m-%d (%A)")
        blob = []
        for i, p in enumerate(posts):
            blob.append(f"POST {i} (posted {p['posted_on']}):\n{p['caption'][:900]}")
        captions_text = "\n\n---\n\n".join(blob)

        system = (
            "You extract concrete, dated events from a Tulsa LGBTQ+ / queer-cultural "
            "org's Instagram captions. The org may rove between venues. Return ONLY "
            "events that have an identifiable calendar date. Resolve relative dates "
            "against THE POST DATE, never against the current week. Output STRICT "
            "JSON only."
        )
        user = (
            f"Today is {today}. The current week runs {monday.strftime('%Y-%m-%d')} "
            f"(Monday) through {sunday.strftime('%Y-%m-%d')} (Sunday).\n\n"
            "From the captions below, extract every distinct event that has a real "
            "date. For each, output an object with keys:\n"
            '  "name"  - short event title (no hashtags/emoji, no em dashes)\n'
            '  "date"  - YYYY-MM-DD (resolve relative dates; year is the current year)\n'
            "\n"
            "DATE RULES - the post date is the anchor, NOT the current week. Bars post\n"
            "day-of or a few days ahead, and mis-dating one publishes an event on a\n"
            "night it is not happening:\n"
            "  1. An EXPLICIT date in the caption ALWAYS wins ('SATURDAY 8/15',\n"
            "     'FRIDAY AUGUST 14TH' -> use exactly that, even if weeks out).\n"
            "  2. A BARE weekday with no date ('SATURDAY NIGHT!', 'THIS FRIDAY') means\n"
            "     the FIRST such weekday ON OR AFTER the post date. A post made\n"
            "     2026-08-06 saying 'SATURDAY NIGHT!' is 2026-08-08, NOT a later\n"
            "     Saturday. Never roll a bare weekday forward into the current week.\n"
            "  3. 'tonight'/'today' = the post date itself. 'tomorrow' = post date + 1.\n"
            "  4. NEVER output a date BEFORE the post date.\n"
            "The event may already be in the past relative to today. That is correct and\n"
            "expected. Date it honestly from the post; later filters drop stale events.\n"
            "\n"
            '  "time"  - like "9:00 PM" or "" if none stated\n'
            '  "venue" - the venue/address ONLY if explicitly named in the caption, '
            'else "" (do NOT invent a location)\n'
            '  "post"  - the POST number it came from\n'
            "Skip generic promo with no date, recaps of past events, and merch/donation "
            "posts. Return a JSON object: {\"events\": [ ... ]}. No prose.\n\n"
            f"CAPTIONS:\n{captions_text}"
        )
        raw = None
        if config.ANTHROPIC_API_KEY:
            try:
                from anthropic import Anthropic
                client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
                msg = client.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=MAX_EXTRACT_TOKENS,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                raw = msg.content[0].text.strip()
            except Exception as e:
                logger.warning("[%s] Anthropic extraction failed (%s) — trying DeepSeek",
                               self.source_name, type(e).__name__)
        if raw is None:
            # DeepSeek worker fallback (2026-07-06): SITES_ANTHROPIC_KEY was never
            # set, so extraction silently ran regex-only forever. Structured JSON
            # extraction is squarely cheap-worker work; sanity + preflight gates
            # guard quality downstream. (Key dead as of 2026-07-06, gap G35 —
            # kept wired so it self-heals when William renews it.)
            raw = self._deepseek_complete(system, user)
        if raw is None:
            # claude CLI fallback: runs on the subscription auth the fleet already
            # uses; haiku + hard timeout so a hang can never wedge the scrape.
            raw = self._claude_cli_complete(system, user)
        if raw is None:
            logger.warning("[%s] no LLM produced output — using regex fallback",
                           self.source_name)
            return None

        # Tolerate code fences / stray prose around the JSON.
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            logger.warning("[%s] LLM returned no JSON — using regex fallback", self.source_name)
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            # SALVAGE (2026-09-09) before giving up on the whole venue. A response
            # cut off at max_tokens ends mid-object, and the events BEFORE the cut
            # are complete and correct. Discarding them threw away a good
            # extraction and handed the venue to the regex path, which is exactly
            # what happened to the Eagle. Recover every whole {...} object.
            salvaged = []
            for om in re.finditer(r"\{[^{}]*\}", m.group(0), re.DOTALL):
                try:
                    obj = json.loads(om.group(0))
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and obj.get("name") and obj.get("date"):
                    salvaged.append(obj)
            if not salvaged:
                logger.warning("[%s] LLM JSON parse error, nothing salvageable — "
                               "using regex fallback", self.source_name)
                return None
            logger.warning("[%s] LLM JSON truncated — salvaged %d complete events",
                           self.source_name, len(salvaged))
            data = {"events": salvaged}

        events = []
        for item in data.get("events", []):
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or "").strip()
            date = (item.get("date") or "").strip()
            if not name or not date:
                continue
            try:
                idx = int(item.get("post", -1))
            except (TypeError, ValueError):
                idx = -1
            url = posts[idx]["url"] if 0 <= idx < len(posts) else self.profile_url
            src_posted = posts[idx]["posted_on"] if 0 <= idx < len(posts) else ""
            venue = (item.get("venue") or "").strip() or self.default_venue
            ev = self.make_event(
                name=self._clean_name(name),
                date=date,
                time=(item.get("time") or "").strip(),
                venue=venue,
                description=self.blurb,
                url=url,
                priority=self.priority,
            )
            # Tag with the announcing post's date so the caller can reject stale
            # relative-date projections (a month-old "FRIDAY" post becoming this
            # Friday — the 2026-07-27 YBR "DJ Kylie" bug), and with the caption
            # itself so guard 2 can check the date against what the post says.
            ev["_src_posted_on"] = src_posted
            ev["_src_caption"] = posts[idx]["caption"] if 0 <= idx < len(posts) else ""
            events.append(ev)
        logger.info("[%s] LLM extracted %d dated events", self.source_name, len(events))
        return events

    @staticmethod
    def _deepseek_complete(system: str, user: str):
        """OpenAI-compatible DeepSeek call using the standing WORKER_API_KEY."""
        import os
        import urllib.request
        key = os.environ.get("WORKER_API_KEY", "")
        if not key:
            return None
        body = json.dumps({
            "model": "deepseek-chat",
            "max_tokens": MAX_EXTRACT_TOKENS,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {key}"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                j = json.loads(r.read().decode("utf-8"))
            return (j["choices"][0]["message"]["content"] or "").strip()
        except Exception as e:
            logger.warning("[deepseek] extraction call failed: %s %s",
                           type(e).__name__, str(e)[:120])
            return None

    @staticmethod
    def _claude_cli_complete(system: str, user: str):
        """claude -p (haiku) with a hard timeout. Resolved by absolute path so it
        works under the pythonw scheduled runner too (the 2026-05-25 'claude CLI
        not found in PATH' failure mode)."""
        import os
        import shutil
        import subprocess
        exe = shutil.which("claude")
        if not exe:
            for cand in (os.path.expanduser("~/.local/bin/claude"),
                         os.path.expanduser("~/.local/bin/claude.exe"),
                         os.path.expanduser("~/AppData/Roaming/npm/claude.cmd")):
                if os.path.exists(cand):
                    exe = cand
                    break
        if not exe:
            logger.warning("[claude-cli] not found — skipping CLI extraction tier")
            return None
        # Dual-token failover, same mechanism as the runner's claude-tier tasks:
        # the primary account token 401s as of 2026-07 and the fleet succeeds via
        # the secondary ("[account: personal, FALLBACK]" in runner.log). Try the
        # CLI's own auth first, then each stored token.
        tokens = [None]
        try:
            vals = {}
            for line in (Path.home() / ".credentials" / "claude_tokens.env").read_text(
                    encoding="utf-8").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip()
            for key in ("CLAUDE_TOKEN_PRIMARY", "CLAUDE_TOKEN_SECONDARY"):
                if vals.get(key):
                    tokens.append(vals[key])
        except Exception:
            pass
        for tok in tokens:
            try:
                env = os.environ.copy()
                env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
                # Nested-session vars make claude -p 401 when invoked from inside a
                # live Claude Code session; strip them, then inject the token.
                for k in list(env):
                    if k.startswith("CLAUDE_CODE_") or k in ("CLAUDECODE", "CLAUDE_EFFORT",
                                                              "CLAUDE_CHROME_PERMISSION_MODE"):
                        env.pop(k, None)
                if tok:
                    env["CLAUDE_CODE_OAUTH_TOKEN"] = tok
                r = subprocess.run(
                    [exe, "-p", "--model", "claude-haiku-4-5-20251001"],
                    input=system + "\n\n" + user,
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=180, env=env)
                out = (r.stdout or "").strip()
                if r.returncode == 0 and out and "Failed to authenticate" not in out:
                    return out
                logger.warning("[claude-cli] rc=%s (%s): %s — trying next token",
                               r.returncode, "stored-token" if tok else "default-auth",
                               (out or r.stderr or "")[:100])
            except subprocess.TimeoutExpired:
                logger.warning("[claude-cli] timed out after 180s — trying next token")
            except Exception as e:
                logger.warning("[claude-cli] failed: %s %s", type(e).__name__, str(e)[:120])
        return None

    # ── relative-date resolution (works WITHOUT the LLM) ────────────────────────
    _WEEKDAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1,
                 "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3, "thur": 3,
                 "thurs": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5,
                 "sunday": 6, "sun": 6}

    @classmethod
    def _resolve_relative_date(cls, low_caption: str, posted_on: str) -> str:
        """Resolve a relative date phrase against the post date.

        Bars post in relative time ("THIS SATURDAY", "tomorrow", "THURSDAY",
        "tonight"). Anchor on the day the post went up (falling back to today),
        and resolve the FIRST relative cue found. A bare weekday resolves to its
        next occurrence on/after the post date (within the next 7 days), which is
        exactly how a "come THURSDAY" promo reads. Returns YYYY-MM-DD or "".
        """
        try:
            base = datetime.strptime(posted_on, "%Y-%m-%d") if posted_on else datetime.now()
        except (ValueError, TypeError):
            base = datetime.now()

        # tonight / today  → the post date itself
        if re.search(r"\b(tonight|today)\b", low_caption):
            return base.strftime("%Y-%m-%d")
        # tomorrow / tmrw / tmw  → +1 day
        if re.search(r"\b(tomorrow|tmrw|tmw|2morrow)\b", low_caption):
            return (base + timedelta(days=1)).strftime("%Y-%m-%d")

        # "this saturday" / "saturday" / "sat" → next occurrence on/after the post
        # date. Match longest weekday tokens first so "thurs" isn't shadowed by "thu".
        for token in sorted(cls._WEEKDAYS, key=len, reverse=True):
            if re.search(r"\b" + token + r"\b", low_caption):
                target = cls._WEEKDAYS[token]
                delta = (target - base.weekday()) % 7
                # A weekday named on its own day means that day (delta 0), not +7.
                return (base + timedelta(days=delta)).strftime("%Y-%m-%d")
        return ""

    # ── regex fallback (no API key / LLM unavailable) ───────────────────────────
    def _extract_with_regex(self, posts: List[Dict]) -> List[Dict]:
        events = []
        time_rx = re.compile(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b", re.I)
        num_rx = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")
        month_rx = re.compile(
            r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b",
            re.I,
        )
        months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                  "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
        year = datetime.now().year

        for p in posts:
            caption = p["caption"]
            low = caption.lower()
            if not any(kw in low for kw in EVENT_KEYWORDS):
                continue

            date_str = ""
            m = num_rx.search(caption)
            if m:
                mo, da = int(m.group(1)), int(m.group(2))
                yr = m.group(3)
                yr = int(yr) + 2000 if yr and len(yr) == 2 else (int(yr) if yr else year)
                try:
                    date_str = datetime(yr, mo, da).strftime("%Y-%m-%d")
                except ValueError:
                    date_str = ""
            if not date_str:
                mm = month_rx.search(caption)
                if mm:
                    mo = months[mm.group(1)[:3].lower()]
                    da = int(mm.group(2))
                    try:
                        date_str = datetime(year, mo, da).strftime("%Y-%m-%d")
                    except ValueError:
                        date_str = ""

            if not date_str:
                # Relative dates resolved against the POST date (bars almost never
                # write "6/20" — they write "THIS SATURDAY", "TOMORROW", "THURSDAY",
                # "tonight"). Without this, every IG-only bar source (YBR, Eagle,
                # Majestic, Studio 66) silently yields 0 events whenever the LLM key
                # is unset and the regex path runs. (2026-06-20, per William.)
                date_str = self._resolve_relative_date(low, p.get("posted_on", ""))

            if not date_str:
                continue  # genuinely no resolvable date — skip

            tmatch = time_rx.search(caption)
            time_str = tmatch.group(1).upper() if tmatch else ""
            ev_name = self._derive_event_name(caption, self.default_venue)

            ev = self.make_event(
                name=ev_name,
                date=date_str,
                time=time_str,
                venue=self.default_venue,
                description=self.blurb,
                url=p["url"],
                priority=self.priority,
            )
            ev["_src_posted_on"] = p.get("posted_on", "")
            ev["_src_caption"] = caption
            events.append(ev)
        logger.info("[%s] Regex fallback extracted %d dated events",
                    self.source_name, len(events))
        return events


def scrape() -> List[Dict]:
    """Module-level entry point (matches the runner's scraper contract).

    Runs every configured IG-only org independently so one failure never aborts
    the rest, and returns the combined in-week event list.
    """
    import time as _time
    all_events = []
    health = {}          # source_name -> {"posts": int, "events": int}
    for _i, org in enumerate(ORGS):
        sn = org["source_name"]
        if _i:
            _time.sleep(4)   # pace venue fetches so we don't trip IG rate-limiting
        try:
            sc = InstagramOrgScraper(org)
            events = sc.safe_scrape()
            posts_n = getattr(sc, "last_posts_count", 0)
            health[sn] = {"posts": posts_n, "events": len(events)}
            logger.info("[instagram_orgs] %s: %d posts -> %d events", sn, posts_n, len(events))
            all_events.extend(events)
        except Exception as e:
            health[sn] = {"posts": 0, "events": 0, "error": str(e)[:120]}
            logger.error("[instagram_orgs] %s crashed: %s", sn, e)

    # Completeness signal (William 2026-07-20): a post must never be built on a
    # silently-empty IG venue scrape. Distinguish a genuine quiet week (some
    # venues returned posts, just no dated events) from a fetch failure (NO venue
    # returned any posts = rate-limited / blocked / session dead). Persist a
    # health record the prep/health tasks read; loud-log the failure signature.
    venues_with_posts = sum(1 for v in health.values() if v.get("posts", 0) > 0)
    attempted = len(health)
    fetch_failed = attempted > 0 and venues_with_posts == 0
    # DEGRADED: the fetch technically returned something, but from so few venues
    # that the rest were almost certainly rate-limited (429) rather than genuinely
    # postless. 1-of-8 is the same silent hole as 0-of-8 in practice (William
    # 2026-07-20). Treated the same as a failure by the prep guard: cool down +
    # retry, and flag if it persists.
    fetch_degraded = attempted >= 4 and venues_with_posts <= max(1, attempted // 4)
    try:
        import json as _json
        from datetime import datetime as _dt
        _rec = {
            "checked_at": _dt.now().strftime("%Y-%m-%d %H:%M"),
            "venues_attempted": attempted,
            "venues_with_posts": venues_with_posts,
            "total_events": len(all_events),
            "fetch_failed": fetch_failed,
            "fetch_degraded": fetch_degraded,
            "per_venue": health,
        }
        _p = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ig_scrape_health.json")
        with open(_p, "w", encoding="utf-8") as _f:
            _json.dump(_rec, _f, ensure_ascii=False, indent=2)
    except Exception as _e:
        logger.warning("[instagram_orgs] could not write ig_scrape_health.json: %s", _e)
    if fetch_failed or fetch_degraded:
        logger.error("[instagram_orgs] IG-FETCH-%s: only %d/%d venues returned posts "
                     "(rate-limited/blocked) — gay-venue events likely missing this "
                     "run; do NOT treat as an empty week.",
                     "FAILED" if fetch_failed else "DEGRADED", venues_with_posts, attempted)
    return all_events


def _selftest() -> int:
    """Offline regression test for the no-LLM extraction path.

    Locks the 2026-06-20 fix: bar captions written in relative time + hype banners
    must still resolve to dated, presentably-named events without any network or
    API key. A silent regression here re-zeroes every IG-only bar source.
    """
    S = InstagramOrgScraper
    fails = []

    def _a(s):  # console (cp1252) safe — selftest must never crash on emoji
        return str(s).encode("ascii", "ignore").decode("ascii")

    # 1. Relative-date resolution anchored on the post date.
    cases = [
        ("come dance tonight!", "2026-06-20", "2026-06-20"),  # tonight = post day
        ("party tomorrow at 9", "2026-06-19", "2026-06-20"),  # tomorrow = +1
        ("THIS SATURDAY join us", "2026-06-17", "2026-06-20"),  # Wed post -> Sat
        ("come THURSDAY for talent", "2026-06-16", "2026-06-18"),  # Tue -> Thu
        ("see you sunday", "2026-06-20", "2026-06-21"),  # Sat -> next Sun
        ("no date here at all", "2026-06-17", ""),  # nothing resolvable
    ]
    for cap, posted, expect in cases:
        got = S._resolve_relative_date(cap.lower(), posted)
        tag = "OK" if got == expect else "FAIL"
        if got != expect:
            fails.append(f"reldate {cap!r}@{posted}: got {got!r} expected {expect!r}")
        print(f"[selftest] reldate {cap[:28]:28s} -> {got or '(none)':12s} {tag}")

    # 2. Smart name derivation — hype banners must NOT become the event name.
    venue = "Yellow Brick Road, 2630 E 15th St"
    name_cases = [
        ("‼️HEADS UP‼️\nWe're opening the back for our dance party tomorrow!",
         "Dance Party at YBR"),
        ("THIS SATURDAY\nsummer pride edition of B&B y'all!", "B&B Dance Party at YBR"),
        ("🎤THURSDAY🎤\nCome show us what you got, we're ready to see your talents!",
         "Talent Night at YBR"),
        ("Next Sunday making little queer donuts in a craft class!", "Craft Class at YBR"),
    ]
    for cap, expect in name_cases:
        got = S._derive_event_name(cap, venue)
        tag = "OK" if got == expect else "FAIL"
        if got != expect:
            fails.append(f"name {_a(cap[:25])!r}: got {got!r} expected {expect!r}")
        print(f"[selftest] name -> {_a(got):24s} {tag}")

    if fails:
        print("\n[selftest] FAILURES:")
        for f in fails:
            print("  -", _a(f))
        print("[selftest] FAILED")
        return 1
    print("[selftest] ALL PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    monday, sunday = InstagramOrgScraper._week_range()
    print(f"Instagram-org scraper — week {monday.date()} to {sunday.date()}")
    print("=" * 64)
    results = scrape()
    print(f"\nTOTAL IN-WEEK EVENTS: {len(results)}")

    def _ascii(s):  # console (cp1252) safe — diagnostics must never crash on emoji
        return str(s).encode("ascii", "ignore").decode("ascii")

    for e in results:
        print(f"  {e['date']} {_ascii(e.get('time','')):8s} | "
              f"{_ascii(e['name'])[:50]:50s} | {_ascii(e.get('venue',''))[:30]}")
    if not results:
        print("\n(0 events — either no configured org has an event dated this week, or the "
              "public endpoint was rate-limited. It needs no login; just re-run.)")
