"""
Late-stage venue corrections for the Tulsa Gays pipeline.

Recurring events whose location rotates month to month (e.g. Queer Women's
Collective) cannot carry a reliable hardcoded/scraped venue -- the value goes
stale the moment the event moves, which is exactly how a wrong venue once
shipped on a slide.

This module applies operator-supplied overrides from data/venue_overrides.json
AFTER scrape + resurfacing + dedup, so a known-correct venue beats any stale
scraped, hardcoded, or ledger value. It also exposes the `venue_varies` registry
so the preflight gate can refuse to feature a rotating-venue event that has no
confirmed venue for the month.

Never raises into callers; a missing or broken file logs and no-ops.
"""
import json
import logging
import os
import sys

# Allow running this file directly (python scraper/venue_overrides.py) for the
# selftest; at runtime it is imported as scraper.venue_overrides with root on path.
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

import config

logger = logging.getLogger(__name__)

OVERRIDES_PATH = os.path.join(config.DATA_DIR, "venue_overrides.json")


def _load_doc():
    try:
        with open(OVERRIDES_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.error("[venue-override] could not read %s: %s", OVERRIDES_PATH, exc)
        return {}


def _scope_matches(ov, date_str):
    d = (date_str or "")[:10]
    if ov.get("date"):
        return d == ov["date"]
    if ov.get("month"):
        return d[:7] == ov["month"]
    return True  # always-on override (no month/date scope)


def load_venue_varies():
    """Lowercase name-substrings whose venue rotates month to month."""
    doc = _load_doc()
    return [str(s).lower().strip() for s in doc.get("venue_varies", []) if str(s).strip()]


def has_override_for(name, date_str):
    """True if a venue override entry matches this event name AND covers its date."""
    low = (name or "").lower()
    for ov in _load_doc().get("overrides", []):
        m = (ov.get("match") or "").lower().strip()
        if m and m in low and ov.get("venue") and _scope_matches(ov, date_str):
            return True
    return False


def apply_venue_overrides(events):
    """Overwrite venue (and optional time/url) on any event matching an override
    whose scope covers the event's date. Tags the event `venue_override_applied`
    and records the prior value in `venue_override_from`. Mutates and returns the
    same list."""
    overrides = _load_doc().get("overrides", [])
    if not overrides:
        return events
    applied = 0
    for ev in events:
        low = (ev.get("name") or "").lower()
        for ov in overrides:
            m = (ov.get("match") or "").lower().strip()
            if not m or m not in low:
                continue
            if not _scope_matches(ov, ev.get("date", "")):
                continue
            new_venue = ov.get("venue")
            if new_venue and ev.get("venue") != new_venue:
                ev["venue_override_from"] = ev.get("venue", "")
                ev["venue"] = new_venue
            if ov.get("time"):
                ev["time"] = ov["time"]
            if ov.get("url"):
                ev["url"] = ov["url"]
            ev["venue_override_applied"] = True
            applied += 1
            break
    if applied:
        logger.info("[venue-override] applied %d venue correction(s)", applied)
    return events


def _selftest():
    sample = [
        {"name": "Queer Women's Collective Tulsa", "date": "2026-07-01",
         "venue": "Dennis R. Neill Equality Center, 621 E 4th St"},
        {"name": "Queer Women's Collective Tulsa", "date": "2026-08-05",
         "venue": "Dennis R. Neill Equality Center, 621 E 4th St"},
        {"name": "Trivia Night at YBR", "date": "2026-07-07",
         "venue": "Yellow Brick Road, 2630 E 15th St"},
    ]
    apply_venue_overrides(sample)
    # July QWC: overridden away from the stale Equality Center, flagged applied.
    assert sample[0].get("venue_override_applied") is True, sample[0]
    assert not sample[0]["venue"].startswith("Dennis"), sample[0]
    # August QWC: no override this month -> venue untouched, no applied flag.
    assert not sample[1].get("venue_override_applied"), sample[1]
    assert sample[1]["venue"].startswith("Dennis"), sample[1]
    # Unrelated stable-venue event: never touched.
    assert not sample[2].get("venue_override_applied"), sample[2]
    assert sample[2]["venue"].startswith("Yellow"), sample[2]
    # Registry + override presence the preflight gate relies on.
    assert "queer women's collective" in load_venue_varies()
    assert has_override_for("Queer Women's Collective Tulsa", "2026-07-01")
    assert not has_override_for("Queer Women's Collective Tulsa", "2026-08-05")
    print("venue_overrides selftest OK")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _selftest()
