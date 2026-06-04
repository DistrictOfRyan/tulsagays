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
# Grouped so the task can cover every flavor of "gay group in Tulsa", including
# the categories William called out explicitly (craft clubs at churches, sound
# baths, meditations). The task runs these through WebSearch, then validates and
# records finds as candidates.
SEARCH_SEEDS = {
    "core_orgs": [
        "Tulsa LGBTQ organizations list",
        "Tulsa queer community groups 2026",
        "Tulsa gay social club Facebook group",
        "Tulsa lesbian group meetup",
        "Tulsa trans support group",
        "Tulsa nonbinary community Tulsa",
        "Tulsa bi+ pan community group",
        "Tulsa two-spirit indigenous queer group",
        "Black queer Tulsa group",
        "Tulsa Latinx LGBTQ group",
    ],
    "affinity_hobby": [
        "Tulsa LGBTQ craft club",
        "Fellowship Congregational Church Tulsa craft club events",
        "Tulsa queer book club",
        "Tulsa gay board game night",
        "Tulsa LGBTQ hiking outdoors group",
        "Tulsa queer climbing group",
        "Tulsa gay sports league kickball volleyball",
        "Tulsa LGBTQ choir band ensemble",
        "Tulsa queer crafternoon knitting",
        "Tulsa rainbow run club",
    ],
    "wellness": [
        "Tulsa sound bath events",
        "Tulsa meditation events open to public",
        "Tulsa breathwork workshop",
        "Tulsa reiki community event",
        "Tulsa yoga community class queer-friendly",
        "Tulsa queer wellness group",
        "Tulsa grief support LGBTQ",
    ],
    "venues_churches": [
        "Tulsa affirming church events calendar",
        "Tulsa open and affirming congregation events",
        "Fellowship Congregational Church Tulsa events",
        "All Souls Unitarian Tulsa events",
        "Tulsa Metropolitan Community Church events",
        "Tulsa Pride Center events",
        "Dennis R. Neill Equality Center calendar",
    ],
    "nightlife_arts": [
        "Tulsa drag show calendar 2026",
        "Tulsa queer art opening events",
        "Tulsa LGBTQ open mic poetry",
        "Tulsa gay bar events calendar",
        "Tulsa burlesque cabaret queer",
    ],
}


def all_seed_queries():
    """Flatten SEARCH_SEEDS into a single ordered list of query strings."""
    out = []
    for group in SEARCH_SEEDS.values():
        out.extend(group)
    return out


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
