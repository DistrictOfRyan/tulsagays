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
