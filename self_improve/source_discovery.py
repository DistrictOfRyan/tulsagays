"""Discover new LGBTQ+ event sources for the TulsaGays scraper.

Two complementary discovery modes feed one candidate registry
(self_improve/source_registry.py):

1. VENUE/ORG MINER (this file, ``mine_recent_events``) -- offline + reliable.
   Scans the last several weeks of scraped events and surfaces venues that keep
   hosting queer-relevant events but are NOT yet trusted as community partners.
   A recurring venue is a stream worth trusting by name (sound-bath spaces,
   churches with craft clubs, theaters, etc. -- exactly what William wants).

2. WEB DISCOVERY (the weekly scheduled task, using the WebSearch tool) -- the
   reasoning pass that actively hunts for *net-new* Tulsa gay groups/orgs/pages
   that have never appeared in a scrape yet. ``SEARCH_SEEDS`` below is the
   query bank that task works through. The task writes its finds via
   ``source_registry.add_candidate``.

The old Google-scraping discoverer was removed: requests-based Google scraping
gets anti-bot blocked, and it explicitly skipped Facebook/Meetup/Eventbrite --
which is where Tulsa's queer groups actually live.
"""

import sys
import os
import re
import glob
import logging
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from self_improve import source_registry as registry

logger = logging.getLogger(__name__)


# ── Query bank for the weekly WebSearch reasoning pass ───────────────────────
# Templated by {city} so the SAME engine works for any city (Rung 5: city-
# cloning). Categories cover every flavor of "gay group", including the ones
# William called out (craft clubs at churches, sound baths, meditations).
# {city}-templated generic queries below; per-city named-venue extras live in
# CITY_SPECIFIC_SEEDS so a new city needs zero code changes, just an optional
# extras list.
SEED_TEMPLATES = {
    "core_orgs": [
        "{city} LGBTQ organizations list",
        "{city} queer community groups 2026",
        "{city} gay social club Facebook group",
        "{city} lesbian group meetup",
        "{city} trans support group",
        "{city} nonbinary community",
        "{city} bi+ pan community group",
        "{city} two-spirit indigenous queer group",
        "Black queer {city} group",
        "{city} Latinx LGBTQ group",
    ],
    "affinity_hobby": [
        "{city} LGBTQ craft club",
        "{city} affirming church craft club events",
        "{city} queer book club",
        "{city} gay board game night",
        "{city} LGBTQ hiking outdoors group",
        "{city} queer climbing group",
        "{city} gay sports league kickball volleyball",
        "{city} LGBTQ choir band ensemble",
        "{city} queer crafternoon knitting",
        "{city} rainbow run club",
    ],
    "wellness": [
        "{city} sound bath events",
        "{city} meditation events open to public",
        "{city} breathwork workshop",
        "{city} reiki community event",
        "{city} yoga community class queer-friendly",
        "{city} queer wellness group",
        "{city} grief support LGBTQ",
    ],
    "venues_churches": [
        "{city} affirming church events calendar",
        "{city} open and affirming congregation events",
        "{city} Metropolitan Community Church events",
        "{city} Unitarian Universalist events",
        "{city} Pride center events",
        "{city} LGBTQ equality center calendar",
    ],
    "nightlife_arts": [
        "{city} drag show calendar 2026",
        "{city} queer art opening events",
        "{city} LGBTQ open mic poetry",
        "{city} gay bar events calendar",
        "{city} burlesque cabaret queer",
    ],
    # Family + youth (added 2026-07-01 per William: surface gay-family and
    # kid-friendly events, not just 21+ bar nights). These pull the whole other
    # half of the community the bar-heavy feed was missing.
    "family_youth": [
        "{city} LGBTQ family friendly Pride event",
        "{city} drag queen story hour",
        "{city} rainbow story time library",
        "{city} queer parents family group",
        "{city} LGBTQ youth group meeting",
        "{city} gay straight alliance GSA event",
        "{city} LGBTQ teen program",
        "{city} PFLAG {city} meeting",
        "{city} all ages queer event",
        "{city} affirming family day LGBTQ",
    ],
    # Professional / food / film / civic (added 2026-07-01). Draws a different,
    # broader gay crowd than nightlife: networking mixers, queer makers markets,
    # film screenings, volunteer/activism days.
    "pro_food_film_civic": [
        "{city} LGBTQ professionals networking mixer",
        "{city} gay chamber of commerce event",
        "{city} queer makers market",
        "{city} LGBTQ pop up market",
        "{city} LGBTQ film festival screening",
        "{city} queer sober social event",
        "{city} gaymers group",
        "{city} LGBTQ trivia night",
        "{city} LGBTQ volunteer day",
        "{city} queer potluck community dinner",
    ],
}

# Per-city named-venue seeds (the things you only know by local knowledge).
# Adding a new city = add a key here (optional). No code changes required.
CITY_SPECIFIC_SEEDS = {
    "Tulsa": [
        "Fellowship Congregational Church Tulsa craft club events",
        "All Souls Unitarian Tulsa events",
        "Dennis R. Neill Equality Center calendar",
        "Council Oak Men's Chorale Tulsa",
        "Black Queer Tulsa events",
        # Family / youth / broader-community named leads (2026-07-01).
        "Oklahomans for Equality youth program events Tulsa",
        "PFLAG Tulsa meeting",
        "Tulsa City-County Library rainbow story time",
        "Freedom Oklahoma Tulsa events",
        "HotMess Sports Tulsa kickball dodgeball",
        "Tulsa Pride family friendly events",
    ],
}


def seed_queries_for_city(city="Tulsa"):
    """Return the category->queries dict for any city. City-agnostic engine."""
    out = {cat: [q.format(city=city) for q in tmpl] for cat, tmpl in SEED_TEMPLATES.items()}
    extras = CITY_SPECIFIC_SEEDS.get(city)
    if extras:
        out["local_named"] = list(extras)
    return out


# Default Tulsa bank (back-compat: existing callers use SEARCH_SEEDS).
SEARCH_SEEDS = seed_queries_for_city("Tulsa")


def all_seed_queries(city="Tulsa"):
    """Flatten the seed bank for ``city`` into a single ordered list."""
    out = []
    for group in seed_queries_for_city(city).values():
        out.extend(group)
    return out


def city_census_template(city, state):
    """Generate a blank census skeleton for a NEW city.

    Returns the universal categories every city has (pride org, affirming
    churches, gay bars, wellness, etc.) as TODO stubs a local can fill. This is
    what build-city seeds when cloning the engine to a new market.
    """
    cats = [
        ("pride", "event", f"{city} Pride"),
        ("equality_center", "org", f"{city} LGBTQ center / equality center"),
        ("pflag", "org", f"PFLAG {city}"),
        ("affirming_church_1", "church", f"{city} affirming/UCC congregation"),
        ("mcc", "church", f"Metropolitan Community Church {city}"),
        ("uu", "church", f"Unitarian Universalist {city}"),
        ("gay_bar_1", "bar", f"{city} gay bar"),
        ("lesbian_bar", "bar", f"{city} lesbian/queer-women bar"),
        ("drag_collective", "org", f"{city} drag collective"),
        ("queer_wellness", "wellness", f"{city} meditation/sound-bath space"),
        ("trans_support", "org", f"{city} trans support group"),
        ("youth", "org", f"{city} LGBTQ youth org"),
    ]
    return {
        "_comment": f"AUTO-GENERATED census skeleton for {city}, {state}. "
                    f"Fill in real names/aliases per stub, then run coverage_report.",
        "city": city, "state": state,
        "orgs": [{"id": cid, "name": "TODO: " + hint, "type": typ,
                  "aliases": [], "note": "stub - fill in"} for cid, typ, hint in cats],
    }


# ── Venue normalization ──────────────────────────────────────────────────────
_ADDRESS_RE = re.compile(r",?\s*\d{2,5}\s+[NSEW]?\.?\s*\w.*$")  # ", 621 E 4th St ..."
_JUNK_VENUES = {
    "", "?", "tulsa", "tulsa, ok", "various locations", "various locations in tulsa",
    "online", "tba", "tbd", "see website", "check listing for time",
    "downtown tulsa", "meetup tulsa", "midtown tulsa", "various", "venue varies",
    "restaurant varies", "location varies", "to be announced", "n/a",
}
# Venue strings that are scraper/FB artifacts, not real venues.
_JUNK_PREFIXES = ("shared by ", "hosted by ", "presented by ", "rsvp", "http")


def _venue_keyword(raw: str) -> str:
    """Reduce a raw venue string to a stable, trust-able keyword.

    "Dennis R. Neill Equality Center, 621 E 4th St" -> "dennis r. neill equality center"
    "Shambhala Meditation Center of Tulsa"           -> "shambhala meditation center of tulsa"
    """
    if not raw:
        return ""
    v = raw.strip()
    # Drop a trailing street address ("..., 621 E 4th St, Tulsa, OK")
    v = _ADDRESS_RE.sub("", v)
    # If still comma-laden, keep the part before the first comma (the name)
    if "," in v:
        v = v.split(",")[0]
    v = re.sub(r"\s+", " ", v).strip().lower()
    return v


def mine_recent_events(weeks: int = 8, min_events: int = 2):
    """Mine recent scrape output for recurring venues worth trusting.

    Returns a list of dicts describing candidates that were ADDED to the
    registry this run (already-known and already-recorded venues are skipped by
    add_candidate's dedup).
    """
    import json
    files = sorted(glob.glob(os.path.join(config.EVENTS_DIR, "*_all.json")),
                   key=os.path.getmtime)[-weeks:]
    if not files:
        logger.info("[discovery] no *_all.json files to mine")
        return []

    # venue keyword -> {weeks: set, events: set, example: str}
    stats = defaultdict(lambda: {"weeks": set(), "events": set(), "example": ""})

    for fpath in files:
        wk = os.path.basename(fpath).split("_all.json")[0]
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        # Two on-disk shapes: a bare list of events, or {"events": [...]}
        events = data.get("events", []) if isinstance(data, dict) else data
        for e in events:
            if not isinstance(e, dict):
                continue
            kw = _venue_keyword(e.get("venue", ""))
            if not kw or kw in _JUNK_VENUES or len(kw) < 4:
                continue
            if kw.startswith(_JUNK_PREFIXES):
                continue
            name = (e.get("name") or "").strip()
            stats[kw]["weeks"].add(wk)
            if name:
                stats[kw]["events"].add(name.lower())
                if not stats[kw]["example"]:
                    stats[kw]["example"] = name

    added = []
    for kw, s in stats.items():
        n_events = len(s["events"])
        n_weeks = len(s["weeks"])
        if n_events < min_events:
            continue

        # Honest confidence from recurrence. Capped below auto-promote (85) so a
        # pure-miner find is *queued* for a human glance -- the Claude reasoning
        # pass can raise confidence with explicit queer-welcoming evidence.
        if n_events >= 5 and n_weeks >= 2:
            conf = 80
        elif n_events >= 3:
            conf = 70
        else:
            conf = 58

        evidence = (f"Hosted {n_events} distinct events across {n_weeks} week(s) "
                    f"in recent scrapes (e.g. \"{s['example']}\"). Recurring venue "
                    f"-> trust by name so its community events flow through.")
        result = registry.add_candidate(
            ctype="venue_keyword",
            name=kw.title(),
            kw=kw,
            confidence=conf,
            evidence=evidence,
            discovered_via="venue-miner",
        )
        if result == "added":
            added.append({"kw": kw, "events": n_events, "weeks": n_weeks, "confidence": conf})
            logger.info("[discovery] new candidate venue: %s (%d events / %d wk, conf %d)",
                        kw, n_events, n_weeks, conf)

    return added


def discover_new_sources():
    """Back-compat entry point used by ``main.py discover``.

    Runs the venue/org miner and returns human-readable strings for the CLI.
    Net-new org/page discovery happens in the weekly scheduled task via
    WebSearch (see SEARCH_SEEDS).
    """
    added = mine_recent_events()
    return [f"{a['kw']} (venue: {a['events']} events / {a['weeks']} wk, conf {a['confidence']})"
            for a in added]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print("=== TulsaGays Source Discovery: venue miner ===")
    finds = discover_new_sources()
    if finds:
        print(f"{len(finds)} new candidate(s):")
        for f in finds:
            print("  -", f)
    else:
        print("No new venue candidates (all recurring venues already trusted).")
    print(f"\nSeed queries for the weekly web pass: {len(all_seed_queries())}")
