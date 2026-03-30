"""Central configuration for Tulsa Gays automation."""
import os
from datetime import datetime

# ── Paths ────────────────────────────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
EVENTS_DIR = os.path.join(DATA_DIR, "events")
LOGO_PATH = os.path.join(PROJECT_DIR, "logo", "tulsagays_logo.png")
BLOG_DIR = os.path.join(PROJECT_DIR, "blog")
SOURCES_FILE = os.path.join(DATA_DIR, "sources.json")
GROWTH_LOG = os.path.join(DATA_DIR, "growth_log.json")

# ── API Keys (set via environment variables) ─────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
META_ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN", "")
META_IG_USER_ID = os.environ.get("META_IG_USER_ID", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ── Event Sources ────────────────────────────────────────────────────────
# Priority: 1 = always feature, 2 = feature if good, 3 = only if special/slow week
SOURCES = {
    "homo_hotel": {
        "name": "Homo Hotel Happy Hour",
        "url": "",  # Will be discovered/set
        "priority": 1,  # ALWAYS TOP BILLING
        "type": "priority",
        "description": "The signature weekly happy hour event - ALWAYS featured first",
    },
    "okeq": {
        "name": "Oklahomans for Equality (OKEQ)",
        "url": "https://www.okeq.org/events",
        "priority": 1,
        "type": "priority",
        "description": "Dennis R. Neill Equality Center events",
    },
    "twisted_arts": {
        "name": "Twisted Arts",
        "url": "https://twistedfest.org",
        "priority": 1,
        "type": "priority",
        "description": "Art events, drag shows, queer performances",
    },
    "all_souls": {
        "name": "All Souls Unitarian Church",
        "url": "https://www.allsoulschurch.org/calendar",
        "priority": 2,
        "type": "church",
        "description": "Affirming church with community events",
    },
    "church_restoration": {
        "name": "Church of the Restoration",
        "url": "https://www.churchoftherestoration.org",
        "priority": 2,
        "type": "church",
        "description": "UU affirming congregation",
    },
    "tulsa_eagle": {
        "name": "Tulsa Eagle",
        "url": "https://www.facebook.com/TheTulsaEagle/",
        "priority": 3,
        "type": "bar",
        "description": "Bar - only feature special events",
    },
    "ybr": {
        "name": "Yellow Brick Road (YBR)",
        "url": "https://www.facebook.com/YBRTulsa/",
        "priority": 3,
        "type": "bar",
        "description": "Bar - only feature special events",
    },
    "majestic": {
        "name": "Majestic Night Club",
        "url": "https://www.facebook.com/clubmajestictulsa/",
        "priority": 3,
        "type": "bar",
        "description": "Nightclub - only feature special events",
    },
    "tulsa_arts_district": {
        "name": "Tulsa Arts District",
        "url": "https://thetulsaartsdistrict.org/events/list/",
        "priority": 2,
        "type": "community",
        "description": "Arts district community events",
    },
    "circle_cinema": {
        "name": "Circle Cinema",
        "url": "https://www.circlecinema.org",
        "priority": 2,
        "type": "arts",
        "description": "Independent cinema hosting Twisted Arts events and screenings",
    },
    "council_oak_chorus": {
        "name": "Council Oak Men's Chorus",
        "url": "https://www.facebook.com/CouncilOakMensChorus/",
        "priority": 1,
        "type": "priority",
        "description": "Gay men's chorus, concerts ALWAYS get Event of the Week",
    },
    "black_queer_tulsa": {
        "name": "Black Queer Tulsa",
        "url": "https://www.blackqueertulsa.org/",
        "priority": 1,
        "type": "priority",
        "description": "Black Queer Proud festival, OTA balls, brunches, wellness",
    },
    "studio_66": {
        "name": "Studio 66",
        "url": "https://www.s66tulsa.com/",
        "priority": 2,
        "type": "arts",
        "description": "Dance parties, drag race watch parties, fashion shows",
    },
    "lambda_bowling": {
        "name": "Lambda Bowling League",
        "url": "https://okeq.org/esa/",
        "priority": 2,
        "type": "sports",
        "description": "LGBTQ+ bowling league through Equality Sports Alliance",
    },
    "hotmess_sports": {
        "name": "HotMess Sports",
        "url": "",
        "priority": 2,
        "type": "sports",
        "description": "LGBTQ+ recreational sports leagues in Tulsa",
    },
    "qwc_tulsa": {
        "name": "Queer Women's Collective Tulsa",
        "url": "https://www.facebook.com/queerwomenscollectivetulsa/",
        "priority": 2,
        "type": "community",
        "description": "Monthly happy hour (1st Wednesday) for queer women and allies",
    },
    "pflag_tulsa": {
        "name": "PFLAG Tulsa",
        "url": "https://tulsapflag.org/",
        "priority": 2,
        "type": "community",
        "description": "Monthly support/education meetings (1st Saturday, 7pm)",
    },
    "green_country_bears": {
        "name": "Green Country Bears",
        "url": "https://greencountrybears.com/",
        "priority": 2,
        "type": "community",
        "description": "Monthly meetups (2nd Thursday), pool parties, social events",
    },
    "prime_timers": {
        "name": "Tulsa Area Prime Timers",
        "url": "https://okeq.org/okeq-events/tulsa-area-prime-timers/",
        "priority": 2,
        "type": "community",
        "description": "Monthly social for mature gay/bi men (2nd Tuesday, 7pm)",
    },
    "elote_drag_brunch": {
        "name": "Elote Drag Brunch",
        "url": "https://www.elotetulsa.com/events",
        "priority": 2,
        "type": "arts",
        "description": "Monthly drag brunch (2nd Saturday), all ages, two seatings",
    },
    "hope_unitarian": {
        "name": "Hope Unitarian Church",
        "url": "https://www.hopeuu.org/",
        "priority": 2,
        "type": "church",
        "description": "UUA Welcoming Congregation with community events",
    },
    "fellowship_ucc": {
        "name": "Fellowship Congregational UCC",
        "url": "https://www.ucctulsa.org/",
        "priority": 2,
        "type": "church",
        "description": "Open and Affirming UCC congregation",
    },
    "house_church": {
        "name": "House Church Tulsa",
        "url": "https://housechurchtulsa.com/",
        "priority": 2,
        "type": "church",
        "description": "Fully affirming faith community",
    },
    "st_dunstans": {
        "name": "Saint Dunstan's Episcopal",
        "url": "http://www.stduntulsa.org/",
        "priority": 2,
        "type": "church",
        "description": "Inclusive Episcopal congregation with LGBTQ involvement",
    },
    "qlist_tulsa": {
        "name": "QLIST Tulsa",
        "url": "https://qlist.app/cities/Oklahoma/Tulsa/163",
        "priority": 1,
        "type": "aggregator",
        "description": "LGBTQ+ event aggregator with structured listings",
    },
    "the_gayly": {
        "name": "The Gayly",
        "url": "https://www.gayly.com/tags/tulsa-events",
        "priority": 2,
        "type": "media",
        "description": "Oklahoma LGBTQ+ media covering Tulsa events",
    },
    "eventbrite_tulsa": {
        "name": "Eventbrite LGBTQ+ Tulsa",
        "url": "https://www.eventbrite.com/d/ok--tulsa/gay-parties/",
        "priority": 2,
        "type": "aggregator",
        "description": "Ticketed LGBTQ+ events in Tulsa",
    },
    "meetup_tulsa": {
        "name": "Meetup LGBTQ+ Tulsa",
        "url": "https://www.meetup.com/find/us--ok--tulsa/lgbtq/",
        "priority": 2,
        "type": "aggregator",
        "description": "LGBTQ+ meetup groups and events in Tulsa",
    },
    "tulsa_artist_fellowship": {
        "name": "Center for Queer Prairie Studies",
        "url": "https://www.tulsaartistfellowship.org/calendar/cqps",
        "priority": 2,
        "type": "arts",
        "description": "Queer art exhibitions, fashion shows, film screenings",
    },
    # ── Bars & Nightlife (expanded) ────────────────────────────────────
    "st_vitus": {
        "name": "St. Vitus",
        "url": "https://www.stvitustulsa.com",
        "priority": 3,
        "type": "bar",
        "description": "Late-night electronic/techno club, queer-friendly, craft cocktails",
    },
    "473_bar": {
        "name": "(473)",
        "url": "",
        "priority": 3,
        "type": "bar",
        "description": "Queer-friendly bar in Kendall-Whittier, local beer, live music",
    },
    "broadway_clubhouse": {
        "name": "The Broadway Clubhouse",
        "url": "",
        "priority": 3,
        "type": "bar",
        "description": "Theater community bar, proceeds support OkEq",
    },
    # ── Drag (expanded) ───────────────────────────────────────────────
    "diva_royale": {
        "name": "Diva Royale Tulsa",
        "url": "https://www.divaroyale.com/dragquenshow-locations.html",
        "priority": 2,
        "type": "arts",
        "description": "Fri/Sat evening 7pm, Sat/Sun brunch, celebrity drag impersonations",
    },
    "tulsa_house_of_drag": {
        "name": "Tulsa House of Drag",
        "url": "https://www.tulsahouseofdrag.com/",
        "priority": 2,
        "type": "arts",
        "description": "Tulsa drag scene platform, show listings, performer directory",
    },
    "dragnificent_majestic": {
        "name": "DRAGNIFICENT! at Club Majestic",
        "url": "https://downtowntulsa.com/do/dragnificent-at-club-majestic-1",
        "priority": 2,
        "type": "arts",
        "description": "Every Thursday drag show hosted by Shanel Sterling",
    },
    # ── Sports (expanded) ─────────────────────────────────────────────
    "pride_sports_kickball": {
        "name": "Pride Sports Tulsa / Gay Kickball",
        "url": "https://pridesportstulsa.leagueapps.com/leagues",
        "priority": 2,
        "type": "sports",
        "description": "LGBTQ+ kickball leagues",
    },
    "tulsa_metro_softball": {
        "name": "Tulsa Metro Softball League",
        "url": "",
        "priority": 2,
        "type": "sports",
        "description": "LGBTQ+ softball league",
    },
    # ── Two-Spirit & Native LGBTQ+ ────────────────────────────────────
    "antss": {
        "name": "All Nations Two-Spirit Society",
        "url": "https://www.facebook.com/allnations2S/",
        "priority": 1,
        "type": "priority",
        "description": "Indigenous Two-Spirit advocacy, annual festival, community events",
    },
    # ── Trans Support ─────────────────────────────────────────────────
    "taco_ok": {
        "name": "Trans Advocacy Coalition of Oklahoma (TACO)",
        "url": "https://transadvocacyok.org/events",
        "priority": 2,
        "type": "community",
        "description": "Weekly meetings, advocacy, Trans Day of Remembrance, youth programs",
    },
    "okeq_gender_support": {
        "name": "OkEq Gender Outreach Support Group",
        "url": "https://okeq.org/transgender-support/",
        "priority": 2,
        "type": "community",
        "description": "Every Wednesday 7-9pm at Equality Center for trans/intersex 18+",
    },
    # ── Professional ──────────────────────────────────────────────────
    "equality_business_alliance": {
        "name": "Equality Business Alliance",
        "url": "https://okeq.org/eba/",
        "priority": 2,
        "type": "community",
        "description": "LGBTQ+ business networking, last Thursday monthly 6-7:30pm",
    },
    # ── Youth ─────────────────────────────────────────────────────────
    "okeq_youth": {
        "name": "OkEq Youth Programs",
        "url": "https://okeq.org/youth/",
        "priority": 2,
        "type": "community",
        "description": "2SLGBTQIA+ youth resources and programming",
    },
    # ── Book Clubs ────────────────────────────────────────────────────
    "queerlit_collective": {
        "name": "QueerLit Collective",
        "url": "https://www.facebook.com/queerlitcollective",
        "priority": 2,
        "type": "arts",
        "description": "Library openings, banned book events, queer literature access",
    },
    # ── Queer-friendly Businesses ─────────────────────────────────────
    "fulton_street_books": {
        "name": "Fulton Street Books & Coffee",
        "url": "",
        "priority": 3,
        "type": "community",
        "description": "Community bookstore, BIPOC and marginalized authors, inclusive space",
    },
    "magic_city_books": {
        "name": "Magic City Books",
        "url": "",
        "priority": 3,
        "type": "community",
        "description": "Independent bookstore in Arts District, hosts queer author events",
    },
    # ── Theater & Film ────────────────────────────────────────────────
    "tulsa_fringe": {
        "name": "Tulsa Fringe Festival",
        "url": "https://okeq.org/fringe/",
        "priority": 1,
        "type": "arts",
        "description": "OkEq-produced boundary-pushing theater, comedy, dance, music",
    },
    # ── Outdoor / Camping ─────────────────────────────────────────────
    "camp_willowswish": {
        "name": "Camp Willowswish",
        "url": "https://willowswish.org/",
        "priority": 2,
        "type": "community",
        "description": "Annual September LGBTQ camping event at Lake Murray, since 1969",
    },
    # ── Additional Aggregators ────────────────────────────────────────
    "gayout_tulsa": {
        "name": "GayOut Tulsa",
        "url": "https://www.gayout.com/tulsa-ok-gay-events-hotspots-the-ultimate-guide",
        "priority": 3,
        "type": "aggregator",
        "description": "Events and hotspots guide",
    },
}

# ── Posting Schedule ─────────────────────────────────────────────────────
WEEKDAY_POST_DAY = "monday"
WEEKDAY_POST_HOUR = 9  # 9am CT
WEEKEND_POST_DAY = "thursday"
WEEKEND_POST_HOUR = 17  # 5pm CT

# ── Instagram ────────────────────────────────────────────────────────────
IG_HANDLE = "tulsagays"
IG_DISPLAY_NAME = "Tulsa Gays"
IG_BIO = "Your weekly LGBTQ+ event guide for Tulsa \nEvents every Mon & Thu \nHomoHotelHappyHour"

# ── Blog ─────────────────────────────────────────────────────────────────
BLOG_URL = "https://tulsagays.github.io"
GITHUB_REPO = "tulsagays/tulsagays.github.io"

# ── Hashtags ─────────────────────────────────────────────────────────────
HASHTAGS = [
    "#TulsaGays", "#TulsaPride", "#GayTulsa", "#TulsaLGBTQ",
    "#QueerTulsa", "#TulsaEvents", "#LGBTQTulsa", "#OklahomaPride",
    "#TulsaNightlife", "#HomoHotelHappyHour", "#TulsaQueer",
    "#GayOklahoma", "#TulsaCommunity", "#LoveIsLove",
]

# ── Self-Improvement ─────────────────────────────────────────────────────
SEARCH_QUERIES = [
    "tulsa lgbtq events",
    "tulsa gay events this week",
    "tulsa queer events",
    "tulsa pride events",
    "tulsa drag show",
    "tulsa lgbtq community",
]

# ── Helpers ──────────────────────────────────────────────────────────────
def ensure_dirs():
    """Create data directories if they don't exist."""
    for d in [DATA_DIR, EVENTS_DIR]:
        os.makedirs(d, exist_ok=True)

def current_week_key():
    """Get a key for the current week like '2026-W13'."""
    now = datetime.now()
    return f"{now.year}-W{now.isocalendar()[1]:02d}"
