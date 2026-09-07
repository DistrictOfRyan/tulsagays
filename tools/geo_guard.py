#!/usr/bin/env python3
"""
geo_guard.py - drop events that belong to a DIFFERENT city.

Built 2026-07-23 for gap G204: LexingtonGays published 11 of 84 events at TULSA
venues (Philbrook Museum, Circle Cinema, Dennis R. Neill Equality Center) with
the city string find-replaced to "Lexington", while the venue name, street
address and URL stayed Tulsa. A reader could be sent to an address that does
not exist in their city, for an event 700 miles away.

WHY THIS LIVES HERE AND NOT IN THE SCRAPERS
The offending scrapers (philbrook_museum, circle_cinema) are hardcoded in
SHARED files - scraper/playwright_scrapers.py, scraper/extended_calendars.py,
scraper/rendered_sites.py - which sync_from_tulsa.py overlays onto every city
site. Deleting them locally would be silently reverted by the next sync. A
publish-time guard is sync-safe and city-agnostic, so every city site gets the
same protection from one file.

THE RULE
Never rewrite a city name into a venue string. If the city is wrong, DROP the
event. A confidently wrong event is worse than a missing one.

Usage:
    from tools.geo_guard import filter_events
    kept, dropped = filter_events(events, city="Lexington", state="KY")

    # audit an existing file without changing it:
    python tools/geo_guard.py data/events/2026-W30_all.json
"""
from __future__ import annotations
import json
import re
import sys

# Domains that belong to a specific metro. If an event's URL is on one of these
# and the site is not that metro, the event is foreign no matter what its venue
# string claims. Extend as other-city inheritance is found.
CITY_DOMAINS = {
    "tulsa": [
        "philbrook.org",
        "circlecinema",
        "okeq.org",
        "tulsaballet.org",
        "gilcrease.org",
        "woodyguthriecenter.org",
        "counciloakmenschorale",
        "greencountrybears",
        "aaoklahoma",
    ],
    "oklahoma city": ["okcmoa.com", "myriadgardens.org"],
    "lexington": ["lexpridecenter.org", "lexpridefest.org", "pflaglexington.org"],
}

# Venue names / street addresses that pin an event to a metro regardless of the
# city token appended to them. These are the exact strings that leaked in G204.
CITY_VENUE_MARKERS = {
    "tulsa": [
        "philbrook museum",
        "2727 s rockford",
        "circle cinema",
        "10 s lewis",
        "dennis r. neill",
        "621 e 4th",
        "equality center",
        "guthrie green",
        "cain's ballroom",
    ],
    "oklahoma city": ["myriad botanical", "paseo arts"],
    # Added 2026-09-07 (W37). Facebook events for Puerto Vallarta bars and for
    # HotMess Sports' out-of-state chapters were shipping in the Tulsa deck.
    # facebook.com/events/<id> URLs carry no geography, so CITY_DOMAINS and
    # _path_city could never see them and only the venue string was left.
    # tools/fb_event_truth.py is the real fix (it asks Facebook where the event
    # is); these markers are the backstop for when Facebook serves no og: card.
    "mexico": ["puerto vallarta", "lazaro cardenas", "olas altas", "col. amapas",
               "jalisco", "méxico", ", mexico", "sayulita", "cdmx",
               "ciudad de méxico", "guadalajara"],
    "out of state": ["north charleston", ", knoxville", ", chattanooga",
                     "mobile, al", ", columbia, sc", ", overbrook",
                     # HotMess Sports is a NATIONAL league and its other-city
                     # chapters kept landing in the Tulsa deck. Little Rock is
                     # the one that nearly shipped: it rode into a real Tulsa
                     # event through name-similarity dedup (see _dedup_day).
                     "little rock", ", ar,", ", tn,", ", sc,", ", al,",
                     "kanis park", "victor ashe park", "oyster city"],
}


def _hay(ev: dict) -> str:
    parts = [
        str(ev.get("venue") or ""),
        str(ev.get("url") or ""),
        str(ev.get("description") or ""),
        " ".join(str(u) for u in (ev.get("source_urls") or [])),
    ]
    return " ".join(parts).lower()


# Cities whose name appearing in a URL PATH means the event is theirs.
# Caught qlist.app/events/Tulsa/... leaking onto LexingtonGays (G204). This is
# the most general rule: aggregators namespace their events by city in the path,
# so the path is authoritative even when the venue field is blank.
PATH_CITIES = [
    "tulsa", "oklahoma-city", "oklahomacity", "okc", "lexington",
    "louisville", "austin", "kansas-city", "kansascity", "denver", "nashville",
]


def _path_city(ev: dict, city_l: str) -> str | None:
    urls = [str(ev.get("url") or "")] + [str(u) for u in (ev.get("source_urls") or [])]
    for u in urls:
        path = re.sub(r"^https?://[^/]+", "", u).lower()
        for other in PATH_CITIES:
            if other == city_l:
                continue
            if re.search(rf"/{re.escape(other)}(/|$|[?#])", path):
                return other
    return None


def foreign_city(ev: dict, city: str) -> str | None:
    """Return the name of the OTHER city this event belongs to, or None."""
    city_l = (city or "").strip().lower()
    hay = _hay(ev)
    for other, domains in CITY_DOMAINS.items():
        if other == city_l:
            continue
        if any(d in hay for d in domains):
            return other
    for other, markers in CITY_VENUE_MARKERS.items():
        if other == city_l:
            continue
        if any(m in hay for m in markers):
            return other
    return _path_city(ev, city_l)


# ---------------------------------------------------------------------------
# STATE-level guard (added 2026-09-07 after G204 recurred on LexingtonGays).
#
# The city lists above are whack-a-mole: they only catch domains someone already
# noticed. Two Oklahoma sources still reached the Kentucky site:
#   aaoklahoma.org/meetings/?tsml-region=lexington   -> Lexington, OKLAHOMA
#   greencountrybears.com                            -> Green Country = Tulsa metro
# The first is the nastiest shape of this bug: the foreign source carries OUR
# city's name in its query string, so every city-name check reads it as local.
#
# The rule: match state tokens against the URL HOST ONLY, never the description.
# A host that names a state which is not this site's state is foreign, whatever
# its venue string or query parameters claim.
# ---------------------------------------------------------------------------
STATE_HOST_TOKENS = {
    "oklahoma": "OK", "greencountry": "OK", "green-country": "OK", "okeq": "OK",
    "kentucky": "KY", "kygov": "KY",
    "tennessee": "TN", "arkansas": "AR", "missouri": "MO", "kansas": "KS",
    "colorado": "CO", "texas": "TX", "nebraska": "NE", "iowa": "IA",
    "illinois": "IL", "indiana": "IN", "ohio": "OH", "virginia": "VA",
}


def _hosts(ev: dict) -> list:
    urls = [str(ev.get("url") or "")] + [str(u) for u in (ev.get("source_urls") or [])]
    out = []
    for u in urls:
        if not u:
            continue
        out.append(re.sub(r"^https?://", "", u).split("/")[0].lower())
    return out


def foreign_state(ev: dict, state: str) -> str | None:
    """Return the OTHER state's code if the event HOST names a non-local state."""
    st = (state or "").strip().upper()
    if not st:
        return None
    for host in _hosts(ev):
        for token, code in STATE_HOST_TOKENS.items():
            if token in host and code != st:
                return code
    return None


def filter_events(events: list, city: str, state: str = "") -> tuple[list, list]:
    """Split events into (kept, dropped). Dropped carry a _dropped_reason."""
    kept, dropped = [], []
    for ev in events:
        if not isinstance(ev, dict):
            kept.append(ev)
            continue
        other = foreign_city(ev, city)
        if not other:
            st = foreign_state(ev, state)
            if st:
                other = st
        if other:
            ev = dict(ev)
            ev["_dropped_reason"] = f"geo_guard: belongs to {other}, not {city}"
            dropped.append(ev)
        else:
            kept.append(ev)
    return kept, dropped


def resolve_city(cfg) -> str:
    """
    Best-effort city name for a city-site config module. Returns "" when the
    city cannot be determined - callers MUST NOT guess, because filtering
    against the wrong city would drop the site's own legitimate events.
    Checks explicit config attrs first, then falls back to the site domain
    (e.g. SITE_URL "https://lexingtongays.com" -> "lexington").
    """
    for attr in ("CITY_NAME", "CITY", "SITE_CITY", "METRO"):
        val = getattr(cfg, attr, None)
        if val and str(val).strip():
            return str(val).strip()
    for attr in ("SITE_URL", "SITE_DOMAIN", "BASE_URL", "DOMAIN"):
        val = str(getattr(cfg, attr, "") or "")
        m = re.search(r"([a-z]+)gays\.com", val.lower())
        if m:
            return m.group(1)
    return ""


def _load(path: str) -> tuple[list, dict | None]:
    with open(path, encoding="utf-8") as fh:
        j = json.load(fh)
    if isinstance(j, dict) and "events" in j:
        return j["events"], j
    return j, None


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    path = argv[1]
    city = argv[2] if len(argv) > 2 else "Lexington"
    events, _wrapper = _load(path)
    kept, dropped = filter_events(events, city)
    print(f"{path}")
    print(f"  total:   {len(events)}")
    print(f"  kept:    {len(kept)}")
    print(f"  DROPPED: {len(dropped)}  (would have been published as {city})")
    for ev in dropped:
        print(f"    - {str(ev.get('name'))[:44]:<44} | "
              f"{str(ev.get('venue'))[:40]:<40} | {ev['_dropped_reason']}")
    return 0 if not dropped else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
