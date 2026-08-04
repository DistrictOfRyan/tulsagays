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


def override_venue_for(name, date_str):
    """Return the CONFIRMED override venue for this event, or None.

    Added 2026-08-03. has_override_for() only answers "does an override exist",
    which let preflight PASS a deck whose rendered venue still contradicted the
    override: the W32 deck said "Equality Center, 5:00 PM" while the confirmed
    override said "The Starlite Bar, 5:30 PM", because overrides are applied during
    scrape and the per-week deck snapshot was built before the override was added.
    Callers can now compare the confirmed venue against what the event actually
    carries, i.e. verify the OUTCOME rather than the precondition.
    """
    low = (name or "").lower()
    for ov in _load_doc().get("overrides", []):
        m = (ov.get("match") or "").lower().strip()
        if m and m in low and ov.get("venue") and _scope_matches(ov, date_str):
            return ov.get("venue")
    return None


def override_venue_mismatch(event):
    """Return (confirmed, actual) when a venue_varies event's venue contradicts its
    confirmed override, else None. A mismatch means the rendered deck is STALE and
    must not ship."""
    name = event.get("name") or ""
    confirmed = override_venue_for(name, event.get("date", ""))
    if not confirmed:
        return None
    actual = (event.get("venue") or "").strip()
    # Compare on the venue's leading segment ("The Starlite Bar" out of
    # "The Starlite Bar, 1902 E 11th St, Tulsa") so a shortened but correct
    # rendering still passes, while a different venue entirely does not.
    core = confirmed.split(",")[0].strip().casefold()
    if core and core in actual.casefold():
        return None
    return (confirmed, actual or "(blank)")


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
    # NOTE: assertions here must not depend on which months happen to have an
    # override in data/venue_overrides.json -- the previous version asserted
    # "August QWC has no override", which started FAILING the moment the real
    # August entry was added on 2026-08-03. A guard that goes red for doing its
    # job is a guard nobody runs. Use a month far enough out that no real
    # override will ever cover it for the "unscoped" cases.
    UNCOVERED = "2099-01-06"
    sample = [
        {"name": "Queer Women's Collective Tulsa", "date": "2026-07-01",
         "venue": "Dennis R. Neill Equality Center, 621 E 4th St"},
        {"name": "Queer Women's Collective Tulsa", "date": UNCOVERED,
         "venue": "Dennis R. Neill Equality Center, 621 E 4th St"},
        {"name": "Trivia Night at YBR", "date": "2026-07-07",
         "venue": "Yellow Brick Road, 2630 E 15th St"},
        {"name": "Homo Hotel Happy Hour at Courtyard Downtown", "date": "2026-08-07",
         "venue": "Dennis R. Neill Equality Center, 621 E 4th St"},
    ]
    apply_venue_overrides(sample)
    # July QWC: overridden away from the stale Equality Center, flagged applied.
    assert sample[0].get("venue_override_applied") is True, sample[0]
    assert not sample[0]["venue"].startswith("Dennis"), sample[0]
    # A month with no override -> venue untouched, no applied flag.
    assert not sample[1].get("venue_override_applied"), sample[1]
    assert sample[1]["venue"].startswith("Dennis"), sample[1]
    # Unrelated stable-venue event: never touched.
    assert not sample[2].get("venue_override_applied"), sample[2]
    assert sample[2]["venue"].startswith("Yellow"), sample[2]
    # W32 regression: the August HHHH override must pull the event OFF the
    # Equality Center and onto the real Courtyard Downtown address.
    assert sample[3].get("venue_override_applied") is True, sample[3]
    assert "Courtyard" in sample[3]["venue"], sample[3]
    assert "621 E 4th" not in sample[3]["venue"], sample[3]
    # Registry + override presence the preflight gate relies on.
    assert "queer women's collective" in load_venue_varies()
    assert "homo hotel" in load_venue_varies()
    assert has_override_for("Queer Women's Collective Tulsa", "2026-07-01")
    assert not has_override_for("Queer Women's Collective Tulsa", UNCOVERED)
    assert has_override_for("Homo Hotel Happy Hour", "2026-08-07")
    assert not has_override_for("Homo Hotel Happy Hour", UNCOVERED)
    # override_venue_mismatch: stale rendered venue must be caught.
    _stale = override_venue_mismatch(
        {"name": "Homo Hotel Happy Hour", "date": "2026-08-07",
         "venue": "Dennis R. Neill Equality Center, 621 E 4th St"})
    assert _stale and "Courtyard" in _stale[0], _stale
    assert override_venue_mismatch(
        {"name": "Homo Hotel Happy Hour", "date": "2026-08-07",
         "venue": "Courtyard Downtown, 415 S Boston Ave, Tulsa"}) is None
    print("venue_overrides selftest OK")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _selftest()
