"""Central configuration for Tulsa Gays automation."""
import os
from datetime import datetime

# Load .env if present
_env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                if _v.strip():
                    # Always set from .env — overrides empty env vars (e.g. inherited shell vars)
                    os.environ[_k.strip()] = _v.strip()

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
        "url": "https://www.meetup.com/tulsa-4h-homo-hotel-happy-hour/",
        "priority": 1,  # ALWAYS TOP BILLING
        "type": "priority",
        "description": "Monthly LGBTQIA+ social at rotating Tulsa hotel bars, 1st Friday 7pm. Benefits local queer charities. Meetup group has event listings.",
    },
    "okeq": {
        "name": "Oklahomans for Equality (OKEQ)",
        "url": "https://okeq.org/event-calendar/",
        "priority": 1,
        "type": "priority",
        "description": "Dennis R. Neill Equality Center events - comprehensive event calendar",
    },
    "twisted_arts": {
        "name": "Twisted Arts",
        "url": "https://twistedfest.org/events/",
        "facebook": "https://www.facebook.com/TwistedArtsTulsa/",
        "priority": 1,
        "type": "priority",
        "description": "LGBTQ+ art organization. Film festival, drag shows, queer performances, art events, Pride kickoff. Year-round programming.",
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
        "url": "https://www.instagram.com/studio.66_/",
        "fallback_url": "https://www.s66tulsa.com/",
        "priority": 2,
        "type": "arts",
        "description": "LGBTQIA+ nonprofit hosting dance parties, drag race watch parties, fashion shows, and multi-day festivals. s66tulsa.com ECONNREFUSED on 2026-04-09 and 2026-04-16 — use Instagram @studio.66_ for event listings.",
    },
    "lambda_bowling": {
        "name": "Lambda Bowling League",
        "url": "https://okeq.org/okeq-events/lambda-bowling-league/",
        "facebook": "https://www.facebook.com/tulsalambdaleague/",
        "priority": 1,
        "type": "sports",
        "description": "LGBTQ+ bowling league (2nd Tuesday monthly). Meets at AMF Sheridan Lanes (3121 S Sheridan Rd). Part of Equality Sports Alliance. Doubles teams, social, competitive.",
    },
    "hotmess_sports": {
        "name": "HotMess Sports Tulsa",
        "url": "https://www.hotmesssports.com/tulsa",
        "instagram": "https://www.instagram.com/hotmesssports/",
        "priority": 1,
        "type": "sports",
        "description": "LGBTQ+ recreational sports. Dodgeball, kickball, volleyball, cornhole, bowling, tennis, flag football. Commissioner: Grant Cobb (Grant@HotMessSports.com). Currently registering for Dodgeball Winter 2026.",
    },
    "pride_sports_tulsa": {
        "name": "Pride Sports Tulsa - Gay Kickball",
        "url": "https://pridesportstulsa.leagueapps.com/leagues",
        "priority": 1,
        "type": "sports",
        "description": "LGBTQ+ kickball league. Spring, Summer, Fall seasons. Organized, competitive, community-focused.",
    },
    "gay_kickball_tulsa": {
        "name": "Gay Kickball Tulsa",
        "url": "https://www.gaykickball.com/tulsa.html",
        "priority": 1,
        "type": "sports",
        "description": "LGBTQ+ & Ally kickball league. Community-based, organized, competitive, fun. Multiple seasons (Spring/Summer/Fall).",
    },
    "tulsa_metro_softball_league": {
        "name": "Tulsa Metro Softball League (TMSL)",
        "url": "https://www.hometeamsonline.com/teams/default.asp?u=TULSAMSL&s=softball&p=about",
        "priority": 1,
        "type": "sports",
        "description": "Amateur softball league for LGBT community and allies. Tulsa Metro Area.",
    },
    "equality_sports_alliance": {
        "name": "Equality Sports Alliance - OkEq Recreation",
        "url": "https://okeq.org/esa/",
        "priority": 1,
        "type": "sports",
        "description": "Umbrella organization for LGBTQ+ sports in Tulsa (est. 2011). Supports, promotes, recruits, and grows LGBT-welcoming sports. Includes Lambda Bowling, kickball, softball.",
    },
    "usgsn_tulsa": {
        "name": "United States Gay Sports Network - Tulsa",
        "url": "https://www.usgsn.com/tulsa",
        "priority": 1,
        "type": "sports",
        "description": "National LGBTQ+ sports network with Tulsa chapter. Kickball, bowling, and other sports listings.",
    },
    "outloud_sports": {
        "name": "OutLoud Sports - National Queer+ Rec Sports",
        "url": "https://outloudsports.com/",
        "priority": 2,
        "type": "sports",
        "description": "Nation's original Queer+ recreational sports organization. Multi-sport leagues and events.",
    },
    "qwc_tulsa": {
        "name": "Queer Women's Collective Tulsa",
        "url": "https://www.facebook.com/queerwomenscollectivetulsa/",
        "fb_group_url": "https://www.facebook.com/share/14Vwhcwwq2i/",
        "contact": "Hannah Jackson",
        "priority": 2,
        "type": "community",
        "description": "Monthly happy hour on the FIRST WEDNESDAY of each month for queer women and allies. Contact Hannah Jackson for details. Check FB group for venue/time.",
        "recurring": "1st Wednesday monthly",
    },
    "wclub_tulsa": {
        "name": "WClub Tulsa",
        "url": "https://www.facebook.com/share/18DoQE9Jb4/",
        "priority": 2,
        "type": "community",
        "description": "Queer women's social club in Tulsa. Check admin profile for event listings and announcements.",
        "notes": "Admin profile URL provided — check for event posts and group link",
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
    # ── Affirming Churches (33 total) ────────────────────────────────────
    # UCC
    "fellowship_ucc": {"name": "Fellowship Congregational UCC", "url": "https://ucctulsa.org/", "priority": 2, "type": "church", "description": "Open and Affirming, 2900 S Harvard Ave"},
    "community_hope_ucc": {"name": "Community of Hope UCC", "url": "", "priority": 3, "type": "church", "description": "UCC congregation, social justice focused, 2545 S Yale Ave"},
    # Unitarian
    "all_souls_uu": {"name": "All Souls Unitarian Church", "url": "https://allsoulschurch.org/", "priority": 2, "type": "church", "description": "Largest UU in US, Welcoming Congregation, 2952 S Peoria Ave"},
    "hope_unitarian": {"name": "Hope Unitarian Church", "url": "https://www.hopeuu.org/", "priority": 2, "type": "church", "description": "UUA Welcoming Congregation, 8432 S Sheridan Ave"},
    "church_restoration": {"name": "Church of the Restoration UU", "url": "", "priority": 3, "type": "church", "description": "UU, racial justice focus, 1314 N Greenwood Ave"},
    # Episcopal
    "trinity_episcopal": {"name": "Trinity Episcopal Church", "url": "https://www.trinitytulsa.org/", "priority": 2, "type": "church", "description": "Affirming, 501 S Cincinnati Ave"},
    "st_aidans": {"name": "St. Aidan's Episcopal Church", "url": "https://www.staidanstulsa.org/", "priority": 2, "type": "church", "description": "Inclusive and affirming, 4045 N Cincinnati Ave"},
    "st_dunstans": {"name": "Saint Dunstan's Episcopal", "url": "http://www.stduntulsa.org/", "priority": 2, "type": "church", "description": "Open and affirming, marches in Pride, 5635 E 71st St"},
    "christ_church_episcopal": {"name": "Christ Church Episcopal", "url": "https://www.christchurchtulsa.org/", "priority": 3, "type": "church", "description": "Affirming (ChurchClarity), 10901 S Yale Ave"},
    "st_patricks_ba": {"name": "St. Patrick's Episcopal", "url": "https://www.saint-patricks.com/", "priority": 3, "type": "church", "description": "OkEq listed, Broken Arrow"},
    # Methodist
    "boston_ave_umc": {"name": "Boston Avenue United Methodist", "url": "https://www.bostonavenue.org/", "priority": 2, "type": "church", "description": "Affirming, hosts Pride Parade start, 1301 S Boston Ave"},
    "st_pauls_umc": {"name": "St. Paul's United Methodist", "url": "https://stpaulstulsa.com/", "priority": 2, "type": "church", "description": "Reconciling Congregation, 1442 S Quaker Ave"},
    "university_umc": {"name": "University United Methodist", "url": "", "priority": 3, "type": "church", "description": "OkEq listed, 500 S College Ave"},
    # Presbyterian
    "southminster_pcusa": {"name": "Southminster Presbyterian", "url": "https://www.southminstertulsa.org/", "priority": 2, "type": "church", "description": "More Light Presbyterian, full LGBTQ inclusion, 3500 S Peoria Ave"},
    # Lutheran
    "first_lutheran_elca": {"name": "First Evangelical Lutheran", "url": "https://www.felctulsa.org/", "priority": 2, "type": "church", "description": "Reconciling in Christ (2023), 1244 S Utica Ave"},
    # Independent/Non-denom
    "house_church": {"name": "House Church Tulsa", "url": "https://housechurchtulsa.com/", "priority": 2, "type": "church", "description": "Fully affirming, LGBTQ lead pastor, 1244 S Utica Ave"},
    # Ecumenical/Old Catholic
    "st_jerome_ecc": {"name": "Parish Church of St. Jerome", "url": "https://www.saintjerometulsa.org/", "priority": 2, "type": "church", "description": "Ecumenical Catholic, founded 1995 for full inclusion, 205 W King St"},
    "all_saints_catholic": {"name": "All Saints / Todos los Santos", "url": "https://www.allsaintstulsa.org/", "priority": 2, "type": "church", "description": "Old Catholic, bilingual, DignityUSA partner"},
    # MCC
    "mcc_tulsa": {"name": "Metropolitan Community Church", "url": "", "priority": 2, "type": "church", "description": "LGBTQ-founded denomination, 1623 N Maplewood Ave (verify)"},
    # Disciples of Christ
    "bethany_christian": {"name": "Bethany Christian Church", "url": "https://bethanybelieves.com/", "priority": 3, "type": "church", "description": "Open and Affirming DOC, 6730 S Sheridan Rd"},
    # Quaker
    "green_country_friends": {"name": "Green Country Friends Meeting", "url": "http://www.scym.org/greencountry/", "priority": 3, "type": "church", "description": "FGC Quakers, LGBTQ affirming"},
    # Unity
    "unity_center": {"name": "Unity Center of Tulsa", "url": "https://unitytulsa.org/", "priority": 3, "type": "church", "description": "All welcome, 1830 S Boston Ave"},
    "unity_midtown": {"name": "Unity of Tulsa-Midtown", "url": "https://tulsaunity.org/", "priority": 3, "type": "church", "description": "Inclusive spiritual community, 3355 S Jamestown Ave"},
    # Jewish
    "bnai_emunah": {"name": "Congregation B'nai Emunah", "url": "https://tulsagogue.com/", "priority": 2, "type": "church", "description": "Open and affirming Conservative synagogue, 1719 S Owasso Ave"},
    "temple_israel": {"name": "Temple Israel", "url": "https://templetulsa.com/", "priority": 2, "type": "church", "description": "Reform Judaism, welcomes LGBTQ Jews, 2004 E 22nd Pl"},
    # Muslim
    "muslims4mercy": {"name": "Muslims4Mercy", "url": "", "priority": 3, "type": "church", "description": "LGBTQ-affirming Muslim community, OkEq listed"},
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
        "url": "https://www.facebook.com/people/Tulsa-House-of-Drag/61557097803540/",
        "fallback_url": "https://www.tulsahouseofdrag.com/",
        "instagram": "https://www.instagram.com/tulsahouseofdrag/",
        "priority": 2,
        "type": "arts",
        "description": "Tulsa drag scene landing page — show listings, performer directory, merch. tulsahouseofdrag.com ECONNREFUSED on 2026-04-16; use Facebook or Instagram @tulsahouseofdrag.",
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
    "yst_lgbtq": {
        "name": "Youth Services of Tulsa (YST) LGBTQ+",
        "url": "https://www.ysthelp.com/",
        "priority": 2,
        "type": "community",
        "description": "LGBTQ+ youth programs: weekly Coffee House, LGBTQ Support Group (ages 13-20), Out and About community activities, Pride Prom. Drop-in center at 311 S Madison Ave.",
        "recurring": "Weekly Coffee House; LGBTQ support group for ages 13-20",
    },
    "queer_night_tulsa": {
        "name": "Queer Night Tulsa",
        "url": "https://www.instagram.com/queernight.tulsa/",
        "priority": 2,
        "type": "community",
        "description": "Monthly sober community gathering at YWCA Tulsa. Skill-sharing, trivia, crafts, performances. Created by Irissa Baxter-Luper after Nex Benedict tragedy. Active as of March 2025.",
        "recurring": "Monthly at YWCA Tulsa",
    },
    "urban_lgbt_tulsa": {
        "name": "Urban LGBT Tulsa Inc",
        "url": "https://www.facebook.com/p/Urban-Lgbt-Tulsa-inc-100085937172262/",
        "priority": 3,
        "type": "community",
        "description": "Nonprofit at 4th & Peoria with Rainbow Room, Pride Socials, community events. 15+ years serving Tulsa LGBTQ+ community.",
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
    "tulsa_lgbtq_hot_list": {
        "name": "TULSA LGBTQ HOT LIST",
        "url": "https://www.facebook.com/groups/472710852857064/",
        "priority": 3,
        "type": "aggregator",
        "description": "Facebook community group where members post and share LGBTQ+ events happening in Tulsa. Good crowdsourced aggregator for events not listed elsewhere.",
    },
    # ── New sources added 2026-04-20 ─────────────────────────────────────
    "lgbt_of_oklahoma_fb": {
        "name": "LGBT of Oklahoma (Facebook Group)",
        "url": "https://www.facebook.com/groups/673721549395149/",
        "priority": 2,
        "type": "aggregator",
        "description": "Public Facebook group, 955 members. Statewide LGBTQ+ community group — filter for Tulsa-area events.",
    },
    "okc_lgbtq_events_fb": {
        "name": "OKC Area LGBTQ+ Events and Community Activities (Facebook Group)",
        "url": "https://www.facebook.com/groups/526396531335580/",
        "priority": 2,
        "type": "aggregator",
        "description": "Public Facebook group, 14K members, 219 friends in group, 7+ posts/day. Covers OKC and statewide — filter for Tulsa events. High-volume source.",
    },
    # ── New sources added 2026-04-16 ─────────────────────────────────────
    "tulsa_pride_site": {
        "name": "Tulsa Pride (tulsapride.org)",
        "url": "https://tulsapride.org/",
        "priority": 1,
        "type": "priority",
        "description": "Dedicated site for Tulsa Pride — a program of Oklahomans for Equality. Annual parade and festival (2nd Saturday in October), VIP tickets, parade applications, and lead-up events. Separate from okeq.org event calendar.",
    },
    "tulsa_lgbtq_nightlife_fb": {
        "name": "Tulsa's LGBT Nightlife (Facebook Group)",
        "url": "https://www.facebook.com/groups/220878821301627/",
        "priority": 3,
        "type": "aggregator",
        "description": "Facebook group focused on LGBT nightlife in Tulsa. Members share bar events, club nights, and niche gatherings not listed on official venues. Good secondary crowdsourced check.",
    },
    # ── Bars & Nightlife (EXPANDED) ───────────────────────────────────────
    "dvl_tulsa": {
        "name": "DVL Club & Lounge",
        "url": "https://www.dvltulsa.com",
        "facebook": "https://www.facebook.com/dvltulsa/",
        "instagram": "https://www.instagram.com/dvltulsa/",
        "priority": 1,
        "type": "bar",
        "description": "Woman-owned LGBTQ+ nightlife venue in Blue Dome District (302 S. Frankfort). Themed events, gay nights, ladies nights, EDM, dancing. Hours: Thu-Sat 4pm-2am. Happy hour 4pm-10pm.",
    },
    # ── Wellness & Soundbaths ────────────────────────────────────────────────
    "nicholas_ray_bradford_soundbaths": {
        "name": "Nicholas Ray Bradford - Soundbaths & Wellness Events",
        "url": "https://www.facebook.com/nicholas.bradford.54",
        "priority": 3,
        "type": "wellness",
        "description": "Soundbath and meditation events in Tulsa. Check Facebook for event listings and scheduling.",
    },
    "tulsa_yoga_meditation_center": {
        "name": "Tulsa Yoga Meditation Center",
        "url": "https://www.tulsayogameditationcenter.com/",
        "priority": 2,
        "type": "wellness",
        "description": "Yoga classes, Buddhist meditation, Vedic education, Ayurveda, Reiki. Classes Tue/Thu evenings and other times. Drop-in $20 or 5-class passes $75.",
    },
    "tulsa_shambhala_meditation": {
        "name": "Tulsa Shambhala Meditation Group",
        "url": "https://tulsa.shambhala.org/",
        "priority": 2,
        "type": "wellness",
        "description": "Free monthly open gatherings for Shambhala teachings and mindfulness meditation. Thursday evenings with meditation and Pema Chodron book discussions.",
    },
    "brahma_kumaris_tulsa": {
        "name": "Brahma Kumaris Meditation Center - Tulsa",
        "url": "https://www.eventbrite.com/o/brahma-kumaris-meditation-center-tulsa-oklahoma-74686218343",
        "priority": 2,
        "type": "wellness",
        "description": "Raja Yoga Meditation courses, self-realization, inner peace, spiritual transformation. Non-profit spiritual organization.",
    },
    "tulsa_zen_sangha": {
        "name": "Tulsa Zen Sangha",
        "url": "https://tulsazensangha.wordpress.com/",
        "priority": 2,
        "type": "wellness",
        "description": "Community of lay people practicing Zen meditation. Monthly days of meditation at Osage Forest of Peace, weekly sitting meditation gatherings.",
    },
    "forest_of_peace": {
        "name": "Forest of Peace (Osage Forest of Peace)",
        "url": "https://forestofpeace.org/",
        "priority": 2,
        "type": "wellness",
        "description": "45 wooded acres meditation and retreat center, 20 minutes from downtown Tulsa. Hosts Zen Sangha and other meditation events.",
    },
    "art_of_living_tulsa": {
        "name": "Art of Living Tulsa",
        "url": "https://www.artofliving.org/us-en/tulsa",
        "priority": 2,
        "type": "wellness",
        "description": "Free introductions to SKY Breath Meditation and breathing techniques for quieting the mind.",
    },
    "aarp_soundbath_guthrie_green": {
        "name": "AARP Soundbath & Guided Meditation Series",
        "url": "https://www.guthriegreen.com/",
        "priority": 2,
        "type": "wellness",
        "description": "Free meditative experiences at Guthrie Green (117 N. Boston Ave). Free, all ages, first-come-first-serve. AARP hosts in partnership with Guthrie Green.",
    },
    # ── Art Studios & Galleries ──────────────────────────────────────────────
    "the_church_studio": {
        "name": "The Church Studio",
        "url": "https://www.thechurchstudio.com/events/",
        "priority": 1,
        "type": "arts",
        "description": "Historic recording studio and concert venue in Tulsa. Legacy concert series, indie performances, Tunes @ Noon (Tue/Thu/Sat live music), CarnyFest. Major cultural venue.",
    },
    "liggett_studio": {
        "name": "Liggett Studio",
        "url": "https://www.liggettstudio.com/",
        "priority": 2,
        "type": "arts",
        "description": "Tulsa art gallery and studio offering classes and workshops. Space available for events. Located in East End Village District of Downtown Tulsa.",
    },
    "living_arts_tulsa": {
        "name": "Living Arts Tulsa",
        "url": "https://livingarts.org/",
        "priority": 2,
        "type": "arts",
        "description": "Contemporary art exhibitions, workshops, performances, films, lectures, education. Open Tue-Sat 12-4pm. Free admission.",
    },
    "tac_gallery_artists_coalition": {
        "name": "TAC Gallery (Tulsa Artists' Coalition)",
        "url": "https://www.tacgallery.org/",
        "priority": 2,
        "type": "arts",
        "description": "Tulsa Artists' Coalition gallery featuring artist-run exhibitions and community art projects.",
    },
    "tulsa_artist_fellowship_first_friday": {
        "name": "Tulsa Artist Fellowship - First Friday Art Crawl",
        "url": "https://www.tulsaartistfellowship.org/",
        "priority": 1,
        "type": "arts",
        "description": "Host of First Friday Art Crawl since 2016. Monthly free series with artistic workspaces, exhibitions, workshops, live music, food. 1st Friday every month.",
    },
    "tulsa_arts_district_first_friday": {
        "name": "Tulsa Arts District - First Friday Art Crawl",
        "url": "https://thetulsaartsdistrict.org/first-friday-art-crawl/",
        "priority": 1,
        "type": "arts",
        "description": "Year-round monthly First Friday Art Crawl. Galleries, studios, museums open evenings. Hundreds to thousands attend for visual art, performances, kid-friendly exhibitions.",
    },
    "hardesty_arts_center": {
        "name": "Hardesty Arts Center",
        "url": "https://www.arts.ok.gov/our_programs/Cultural_District/Tulsa_Arts_District.html",
        "priority": 2,
        "type": "arts",
        "description": "Home to the Arts & Humanities Council of Tulsa. Exhibitions, artist studios, workshops. Features Tulsa Glassblowing School and Philbrook Downtown satellite.",
    },
    "tulsa_glassblowing_school": {
        "name": "Tulsa Glassblowing School",
        "url": "https://www.visittulsa.com/listing/tulsa-glassblowing-school/1278/",
        "priority": 2,
        "type": "arts",
        "description": "Glassblowing classes and demonstrations in the Tulsa Arts District.",
    },
    "philbrook_downtown": {
        "name": "Philbrook Downtown",
        "url": "https://www.philbrook.org/",
        "priority": 2,
        "type": "arts",
        "description": "Satellite location of Philbrook Museum of Art in Tulsa Arts District. Art exhibitions and cultural programs.",
    },
    # ── Parks & Nature Events ────────────────────────────────────────────────
    "tulsa_park_recreation_events": {
        "name": "Tulsa Park and Recreation - Events & Programs",
        "url": "https://www.cityoftulsa.org/government/departments/park-and-recreation/",
        "priority": 2,
        "type": "community",
        "description": "City of Tulsa parks system manages 135 parks across 6,500+ acres. Classes, programs, and community events. Register online for programs.",
    },
    "tulsa_county_parks_events": {
        "name": "Tulsa County Parks - Events Calendar",
        "url": "https://www2.tulsacounty.org/parks/events/",
        "priority": 2,
        "type": "community",
        "description": "Tulsa County Parks events calendar. Outdoor recreation, community programs, natural area events.",
    },
    "gathering_place": {
        "name": "Gathering Place Park",
        "url": "https://www.gatheringplace.org/parkcalendar",
        "priority": 1,
        "type": "community",
        "description": "World-class park in downtown Tulsa. Free events showcasing art, history, entertainment, culture. STEAM-inspired pop-ups and community events.",
    },
    "sand_springs_herbal_affair": {
        "name": "Sand Springs Herbal Affair & Festival",
        "url": "https://www.sandspringsok.gov/118/Herbal-Affair-Festival",
        "priority": 1,
        "type": "regional",
        "description": "Annual herbal festival in Sand Springs (April 18-19, 2026). 150+ vendors, medicinal/culinary/decorative herbs, food trucks, live music, family activities. Free admission.",
    },
    # ── Regional Events & Aggregators ────────────────────────────────────────
    "visit_tulsa_events": {
        "name": "Visit Tulsa - Events & Cultural Calendar",
        "url": "https://www.visittulsa.com/events/",
        "priority": 1,
        "type": "aggregator",
        "description": "Official Tulsa tourism site with comprehensive events calendar: concerts, festivals, cultural events, live music, family activities.",
    },
    "city_tulsa_special_events": {
        "name": "City of Tulsa - Calendar of Special Events",
        "url": "https://www.cityoftulsa.org/developmentbusiness/special-events-office/calendar-of-special-events/",
        "priority": 1,
        "type": "aggregator",
        "description": "Official city events calendar. Community celebrations, festivals, parades, athletic/recreational activities on public property.",
    },
    "downtown_tulsa_events": {
        "name": "Downtown Tulsa - Events Calendar",
        "url": "https://downtowntulsa.com/experience/calendar",
        "priority": 1,
        "type": "aggregator",
        "description": "Downtown Tulsa events including live music, art crawls, theatre productions, and entertainment.",
    },
    "guthrie_green": {
        "name": "Guthrie Green - Events Calendar",
        "url": "https://www.guthriegreen.com/",
        "priority": 1,
        "type": "community",
        "description": "Community gathering space in downtown Tulsa. Free events, concerts, festivals, soundbaths, cultural programs.",
    },
    "elote_cinco_de_mayo_festival": {
        "name": "Elote Cinco de Mayo Street Festival",
        "url": "https://www.elotetulsa.com/events",
        "priority": 1,
        "type": "regional",
        "description": "Major downtown Tulsa celebration (May 5, 2026). Live Luchador wrestling, margaritas, tacos, kids activities, Mariachi music. One of downtown's biggest parties.",
    },
    "tpac_events": {
        "name": "Tulsa Performing Arts Center (TPAC) - Events",
        "url": "https://tulsapac.com/events",
        "priority": 1,
        "type": "arts",
        "description": "Premier cultural venue. Broadway tours, Tulsa Ballet, Tulsa Symphony, performances, concerts, comedy. Chapman Music Hall and Williams Theatre.",
    },
    # ── MAJOR EVENT AGGREGATORS & DIRECTORIES ──────────────────────────────
    "tulsago_events": {
        "name": "TulsaGo - Events in Tulsa",
        "url": "https://www.tulsago.com/experience",
        "priority": 1,
        "type": "aggregator",
        "description": "Official guide to events and things to do in Tulsa. Live music, festivals, sports, entertainment, family activities.",
    },
    "valuenews_calendar": {
        "name": "ValueNews - Community Calendar of Events",
        "url": "https://www.valuenews.com/calendar-of-events_id12",
        "priority": 1,
        "type": "aggregator",
        "description": "Monthly calendar of Tulsa events: concerts, bazaars, classes, shows, festivals, fairs.",
    },
    "tulsapeople_events": {
        "name": "TulsaPeople Magazine - Local Events",
        "url": "https://www.tulsapeople.com/local-events/",
        "facebook": "https://www.facebook.com/TulsaPeopleMag/",
        "priority": 1,
        "type": "media",
        "description": "Tulsa's award-winning city magazine. Local events calendar, A-List voting, event coverage.",
    },
    "tulsa_world_events": {
        "name": "Tulsa World - Events Calendar",
        "url": "https://tulsaworld.com/events/",
        "priority": 1,
        "type": "media",
        "description": "Tulsa World newspaper events calendar. Breaking news, local events, entertainment, community activities.",
    },
    "eventbrite_tulsa": {
        "name": "Eventbrite - Tulsa Events",
        "url": "https://www.eventbrite.com/d/ok--tulsa/events/",
        "priority": 1,
        "type": "aggregator",
        "description": "Comprehensive ticketed events platform. Concerts, festivals, classes, workshops, shows.",
    },
    "green_country_ok_events": {
        "name": "Green Country Oklahoma - Events & Festivals",
        "url": "https://www.greencountryok.com/cities/tulsa/festivals-events-in-tulsa/",
        "priority": 1,
        "type": "aggregator",
        "description": "Regional events calendar for Tulsa and surrounding areas. Festivals, concerts, community events.",
    },
    "bandsintown_tulsa": {
        "name": "Bandsintown - Tulsa Concerts & Shows",
        "url": "https://www.bandsintown.com/c/tulsa-ok",
        "priority": 1,
        "type": "aggregator",
        "description": "Concert and live music discovery platform. Upcoming shows, artist alerts, venue tracking.",
    },
    "concertfix_tulsa": {
        "name": "ConcertFix - Tulsa Concerts",
        "url": "https://concertfix.com/concerts/tulsa-ok+venues",
        "priority": 1,
        "type": "aggregator",
        "description": "Concert venue and event aggregator. Tulsa concert schedule and tickets.",
    },
    # ── MAJOR CULTURAL VENUES & MUSIC HALLS ────────────────────────────────
    "philbrook_museum": {
        "name": "Philbrook Museum of Art",
        "url": "https://philbrook.org/calendar/",
        "facebook": "https://www.facebook.com/PhilbrookMuseum/",
        "priority": 1,
        "type": "arts",
        "description": "Major art museum with exhibitions, events, and programming. Free First Saturday, $5 after 5pm Fridays.",
    },
    "woody_guthrie_center": {
        "name": "Woody Guthrie Center",
        "url": "https://woodyguthriecenter.org/",
        "facebook": "https://www.facebook.com/WoodyGuthrieCtr/",
        "priority": 2,
        "type": "arts",
        "description": "Folk music and social justice venue in Tulsa Arts District. Concert series, exhibitions, special events.",
    },
    "cains_ballroom": {
        "name": "Cain's Ballroom",
        "url": "https://www.cainsballroom.com/events/",
        "facebook": "https://www.facebook.com/cainsballroom/",
        "priority": 1,
        "type": "music",
        "description": "Historic live music venue (\"Home of Bob Wills\"). Western swing, concerts, performances. 28+ events 2026-2027.",
    },
    "bok_center": {
        "name": "BOK Center",
        "url": "https://www.bokcenter.com/events/",
        "facebook": "https://www.facebook.com/rockthebok/",
        "priority": 1,
        "type": "music",
        "description": "Major concert and event venue. Top artists, large concerts, sports events.",
    },
    "tulsa_theater": {
        "name": "Tulsa Theater",
        "url": "https://tulsatheater.com/",
        "priority": 2,
        "type": "music",
        "description": "Live music and event venue. Concerts, performances, community events.",
    },
    "hard_rock_live": {
        "name": "Hard Rock Live - Hard Rock Hotel & Casino",
        "url": "https://www.hardrockcasinotulsa.com/entertainment/hard-rock-live",
        "priority": 1,
        "type": "music",
        "description": "Award-winning venue with state-of-the-art sound and seating for 2,700+. World-class performances.",
    },
    "jazz_on_the_green": {
        "name": "Jazz On The Green Festival",
        "url": "https://jazzonthegreentulsa.com/",
        "facebook": "https://www.facebook.com/JazzOnTheGreenTulsa/",
        "priority": 1,
        "type": "music",
        "description": "Annual jazz festival at Guthrie Green. Free live music, community celebration.",
    },
    "oklahoma_jazz_hall_of_fame": {
        "name": "Oklahoma Jazz Hall of Fame",
        "url": "https://www.travelok.com/listings/view.profile/id.5473",
        "priority": 2,
        "type": "music",
        "description": "State's only facility devoted to gospel, jazz, and blues musicians with OK ties. Sunday concerts 5-7pm.",
    },
    # ── REMOTE WORK & COMMUNITY NETWORKS ───────────────────────────────────
    "tulsa_remote_events": {
        "name": "Tulsa Remote - Member Events Calendar",
        "url": "https://memberevents.tulsaremote.com/s/",
        "priority": 1,
        "type": "community",
        "description": "Community platform for 2,500+ remote workers in Tulsa. Dozens of monthly events: park days, concerts, tastings, networking.",
    },
    "tulsa_remote_slack": {
        "name": "TulsaRemote Slack Community",
        "url": "https://tulsaremote.slack.com/",
        "priority": 2,
        "type": "community",
        "description": "Private Slack with 2,500+ members sharing events, recommendations, startup advice. **REQUIRES LOGIN** — goldmine for real-time event announcements and community happenings.",
    },
    "gradient_slack_events": {
        "name": "Gradient Slack Channel (TulsaRemote)",
        "url": "https://tulsaremote.slack.com/archives/CGV2YLJSG",
        "priority": 1,
        "type": "community",
        "description": "Private Slack channel within TulsaRemote. **REQUIRES LOGIN** — specifically focused on events and community activities. Described as 'a gold mine for events.'",
    },
    # ── ADDITIONAL MUSIC & TICKETING PLATFORMS ─────────────────────────────
    "songkick_tulsa": {
        "name": "Songkick - Tulsa Concerts",
        "url": "https://www.songkick.com/metro-areas/1826-us-tulsa",
        "priority": 2,
        "type": "aggregator",
        "description": "Music discovery platform tracking artists and venue events in Tulsa.",
    },
    "jambase_tulsa": {
        "name": "JamBase - Tulsa Concert Venue Schedule",
        "url": "https://www.jambase.com/",
        "priority": 2,
        "type": "aggregator",
        "description": "Concert listings and venue schedules for Tulsa music venues.",
    },
    "ticketmaster_tulsa": {
        "name": "Ticketmaster - Tulsa Events",
        "url": "https://www.ticketmaster.com/tulsa-oklahoma-concerts-sports-arts-theater-family/",
        "priority": 1,
        "type": "aggregator",
        "description": "Official ticketing platform for major venues and events in Tulsa.",
    },
    "axs_tulsa": {
        "name": "AXS - Tulsa Events & Tickets",
        "url": "https://www.axs.com/venues/101571/bok-center-tulsa-tickets",
        "priority": 2,
        "type": "aggregator",
        "description": "Ticketing platform for Tulsa venues and events.",
    },
    "livenation_tulsa": {
        "name": "Live Nation - Tulsa Events",
        "url": "https://www.livenation.com/",
        "priority": 1,
        "type": "aggregator",
        "description": "Major ticketing and event platform. Concerts, shows, festivals across Tulsa venues.",
    },
    # ── WOMPA & CREATIVE COMMUNITY EVENTS ──────────────────────────────────
    "wompa_tulsa": {
        "name": "WOMPA - Event Venue & Creative Community",
        "url": "https://app.wompatulsa.com/events-1/c/0",
        "website": "https://wompatulsa.com/",
        "facebook": "https://www.facebook.com/WOMPATULSA/",
        "priority": 1,
        "type": "community",
        "description": "Major event venue & coworking in Tulsa. 6 event spaces. Hosts art markets, music festivals, weddings, retreats, performances. Wompa Bazaar (90+ vendors). All-ages events.",
    },
    # ── MUSIC FESTIVALS & CARNEY FEST ─────────────────────────────────────
    "carney_fest": {
        "name": "Carney Fest",
        "url": "https://carneyfest.com/",
        "priority": 1,
        "type": "festival",
        "description": "Annual music festival (May 1-2, 2026) at The Church Studio & Cain's Ballroom. Tulsa-focused artists, live performances.",
    },
    "tulsa_kids_festivals": {
        "name": "TulsaKids - Family Festivals Calendar",
        "url": "https://www.tulsakids.com/family-friendly-festivals-in-the-tulsa-area/",
        "priority": 2,
        "type": "festival",
        "description": "Family-friendly festivals and community events in Tulsa area throughout the year.",
    },
    "margaritaville_tulsa": {
        "name": "Jimmy Buffett's Margaritaville - Live Music Calendar",
        "url": "https://www.margaritavilletulsa.com/calendar",
        "priority": 2,
        "type": "music",
        "description": "Live music events and entertainment at Margaritaville Tulsa venue.",
    },
    "the_vanguard_tulsa": {
        "name": "The Vanguard - Live Music Venue",
        "url": "https://www.thevanguardtulsa.com/shows",
        "priority": 1,
        "type": "music",
        "description": "Indie music venue hosting concerts, EDM events (United We Dance rave series), performances.",
    },
    "river_spirit_casino_events": {
        "name": "River Spirit Casino Resort - Entertainment",
        "url": "https://www.riverspirittulsa.com/entertainment",
        "priority": 1,
        "type": "music",
        "description": "Casino resort with concert hall, live music, comedy shows, major entertainment events.",
    },
    "skyline_event_center": {
        "name": "Skyline Event Center - Concerts & Events",
        "url": "https://skylineeventcenter.com/",
        "priority": 2,
        "type": "music",
        "description": "Major event venue hosting concerts, festivals, and large-scale entertainment.",
    },
    # ── ELECTRONIC MUSIC & RAVES ───────────────────────────────────────────
    "bandsintown_electronic": {
        "name": "Bandsintown - Electronic Music Tulsa",
        "url": "https://www.bandsintown.com/c/tulsa-ok/all-dates/genre/electronic",
        "priority": 1,
        "type": "aggregator",
        "description": "Electronic music, EDM, and rave events in Tulsa. Filter by electronic genre.",
    },
    "electronic_midwest": {
        "name": "Electronic Midwest - EDM Calendar",
        "url": "https://electronicmidwest.com/edm-event-calendar/oklahoma/tulsa/",
        "priority": 1,
        "type": "aggregator",
        "description": "Dedicated EDM and electronic music event calendar for Oklahoma/Tulsa region.",
    },
    "edmtrain": {
        "name": "EDMTrain - Oklahoma EDM Events",
        "url": "https://edmtrain.com/oklahoma",
        "priority": 1,
        "type": "aggregator",
        "description": "Electronic dance music events, raves, and festivals across Oklahoma including Tulsa.",
    },
    "allevents_raves_tulsa": {
        "name": "AllEvents.in - Tulsa Raves",
        "url": "https://allevents.in/tulsa/raves",
        "priority": 2,
        "type": "aggregator",
        "description": "Dedicated rave and electronic music events for Tulsa.",
    },
    "united_we_dance": {
        "name": "United We Dance - EDM Rave Series",
        "url": "https://www.unitedwedanceparty.com/tulsa",
        "priority": 1,
        "type": "music",
        "description": "Recurring EDM rave experience in Tulsa. House, techno, bass, trance. DJs mixing artists like FISHER, Skrillex, Martin Garrix.",
    },
    "ravers_of_tulsa_fb": {
        "name": "Ravers of Tulsa (Facebook Community)",
        "url": "https://www.facebook.com/groups/430327683824332/",
        "priority": 2,
        "type": "community",
        "description": "Facebook group for Tulsa rave community. Members share event information, rave culture, electronic music happenings.",
    },
    "oklahoma_edm_community_fb": {
        "name": "Oklahoma EDM Events (Facebook Community)",
        "url": "https://www.facebook.com/groups/355786151171302/",
        "priority": 2,
        "type": "community",
        "description": "Facebook group for Oklahoma EDM events and electronic music community.",
    },
    "songkick_electronic": {
        "name": "Songkick - Electronic Concerts Tulsa",
        "url": "https://www.songkick.com/metro-areas/1826-us-tulsa/genre/electronic",
        "priority": 1,
        "type": "aggregator",
        "description": "Electronic concerts and music events filtered by Tulsa area and electronic genre.",
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
BLOG_URL = "https://www.tulsagays.com"
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
