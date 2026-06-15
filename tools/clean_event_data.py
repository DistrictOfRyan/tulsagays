"""
Event-data cleaner — runs AFTER scrape, BEFORE generate-all.

Fixes the recurring scraper artifacts that made the 2026-06-08 carousel look
unprofessional and forced a manual review:

  1. Placeholder URLs: events whose only link is a search-engine fallback
     (google.com/search, bing, duckduckgo, "/search?...") get their url BLANKED
     so the slide/website fall back to the event's own /e/<id> share page
     instead of printing "www.google.com/search" on a slide.

  2. Source-prefix titles: the scraper sometimes prepends an ALL-CAPS source tag
     directly onto the name ("TULSA-TCDP Happy Hour", "TULSA,Queerlit Turns 2").
     Strip that leading "SOURCE," / "SOURCE-" / "SOURCE em-dash" prefix.

  3. Em dashes in titles: replaced with " - " (William's no-em-dash voice rule
     applies to slide text too).

Idempotent. Operates on data/events/<week>_all.json (the file generate-all
reads). Usage: python tools/clean_event_data.py [WEEK_KEY]
Prints a JSON summary of what it changed.
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402

PLACEHOLDER_URL = re.compile(
    r"(google\.[a-z.]+/search|bing\.com/search|duckduckgo\.com|/search\?|"
    r"^https?://(www\.)?google\.[a-z.]+/?$)", re.I)

# Leading ALL-CAPS source tag glued onto the title by an em dash, comma, or
# hyphen with no following space (the scraper-artifact signature).
SOURCE_PREFIX = re.compile(r"^[A-Z][A-Z0-9]{2,}\s*[—,\-](?=\S)")


def clean_title(name):
    if not name:
        return name, False
    orig = name
    # strip a leading SOURCE prefix (e.g. "TULSA-", "TULSA,")
    m = SOURCE_PREFIX.match(name)
    if m:
        name = name[m.end():].lstrip()
    # em dashes -> " - "
    name = name.replace("—", " - ").replace("–", " - ")
    name = re.sub(r"\s{2,}", " ", name).strip(" -")
    return name, (name != orig)


def is_placeholder(url):
    return bool(url) and bool(PLACEHOLDER_URL.search(url))


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").lower()).strip(" -\n")


def is_venue_artifact(name, venue):
    """True if the venue field is really just the event name echoed back (a
    scraper artifact, e.g. event 'Starlight Concert Band - Above and Below' with
    venue 'Starlight Concert Band -'), NOT a real venue. Conservative: only fires
    when the venue has no real-venue signal (no street address, no venue-type word)
    AND it mirrors the name. Blanking a wrong venue beats showing a garbage one."""
    n, v = _norm(name), _norm(venue)
    if not v or not n:
        return False
    # real venues have an address (digit/comma) or a venue-type word -> keep them
    if any(c.isdigit() for c in v) or "," in v:
        return False
    VENUE_WORDS = ("library", "center", "centre", "church", "bar", "club", "lounge",
                   "theater", "theatre", "park", "hall", "gallery", "museum", "cafe",
                   "coffeehouse", "brewery", "pub", "market", "studio", "house", "room",
                   "school", "university", "stadium", "arena", "venue", "district",
                   "eagle", "majestic", "vanguard", "guthrie")
    if any(w in v for w in VENUE_WORDS):
        return False
    # artifact when the venue is a leading fragment of the name (or equal)
    return n.startswith(v) or v.startswith(n) or v == n


def clean_events(events):
    changed = {"titles": [], "urls_blanked": [], "venues_blanked": []}
    for e in events:
        nm = e.get("name", "")
        new_nm, did = clean_title(nm)
        if did:
            e["name"] = new_nm
            changed["titles"].append({"from": nm, "to": new_nm})
        url = (e.get("url") or "").strip()
        if is_placeholder(url):
            e["url"] = ""
            # also clear any mirrored source_urls list if present
            if isinstance(e.get("source_urls"), list):
                e["source_urls"] = [u for u in e["source_urls"] if not is_placeholder(u)]
            changed["urls_blanked"].append({"name": e.get("name"), "was": url})
        # venue-as-event-name artifact (the "@ Starlight Concert Band -" bug)
        vn = e.get("venue", "")
        if is_venue_artifact(e.get("name", ""), vn):
            e["venue"] = ""
            changed["venues_blanked"].append({"name": e.get("name"), "was": vn})
    return changed


def main():
    week = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") \
        else config.current_week_key()
    path = Path(config.DATA_DIR) / "events" / f"{week}_all.json"
    if not path.exists():
        print(json.dumps({"ok": False, "error": f"no events file {path}"}))
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    events = data if isinstance(data, list) else data.get("events", [])
    changed = clean_events(events)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "ok": True, "week": week,
        "titles_fixed": len(changed["titles"]),
        "urls_blanked": len(changed["urls_blanked"]),
        "detail": changed,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
