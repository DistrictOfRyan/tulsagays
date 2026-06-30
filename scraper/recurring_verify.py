"""
Reality-check for recurring events (scraper/recurring.py).

The recurring list emits ~30 events every week from a hardcoded table with no
check that the event still happens or still lives at that venue. A closed bar,
a cancelled night, or a moved meetup would keep posting a ghost.

This module runs inside the scrape and:
  1. DROPS recurring events whose ledger status is 'paused' or 'dead'.
  2. AUTO-CONFIRMS a recurring event when a real live scrape corroborates it
     this week -- but ONLY on a conservative name match whose VENUE also agrees
     (or where the recurring venue is blank, so there's nothing to contradict).
     That stamps last_verified + verified_by='live-scrape:<source>' and, for a
     blank-venue recurring event, adopts the live venue.
  3. Flags a name match whose VENUE DISAGREES as a possible-move CONFLICT for
     human confirmation -- it never silently adopts a venue from a loose match
     (that produced wrong venues: a different "trivia night", an OKEQ calendar
     default). The freshness clock is NOT refreshed on a conflict.
  4. Tracks verification freshness so preflight can warn on stale events and
     block featuring ones unconfirmed past the hard deadline.

Honest by design: it never fabricates "still happening at X". Anything it can't
confidently corroborate falls onto the freshness clock and surfaces for a human
confirmation pass.

Ledger: data/recurring_confirmations.json. Never raises into the caller.
"""
import json
import logging
import os
import re
import sys
from datetime import date

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

import config

logger = logging.getLogger(__name__)

LEDGER_PATH = os.path.join(config.DATA_DIR, "recurring_confirmations.json")

DEFAULT_STALE_AFTER = 60
DEFAULT_BLOCK_AFTER = 180

# Words with no identifying signal for NAME matching: articles/preps, generic
# event nouns, and venue tokens/abbreviations that appear inside event names.
# What's left -- the distinctive tokens -- must all appear in a live event's
# name for a candidate "same event" match (then the venue must also agree).
_STOPWORDS = {
    "at", "the", "a", "an", "of", "and", "with", "for", "to", "in", "on", "&",
    "night", "nights", "show", "party", "weekly", "monthly", "event", "events",
    "tulsa", "ok", "oklahoma", "downtown",
    "ybr", "yellow", "brick", "road", "majestic", "club", "eagle", "center",
    "equality", "dennis", "neill", "elote", "cafe", "doubletree", "hilton",
    "souls", "unitarian", "church", "fellowship", "park", "central",
}

# Words with no signal for VENUE agreement (street/suffix noise).
_VENUE_STOP = {
    "the", "at", "of", "and", "st", "ave", "blvd", "rd", "dr", "ln", "ste",
    "suite", "n", "s", "e", "w", "tulsa", "ok", "oklahoma",
}


def load_ledger():
    try:
        with open(LEDGER_PATH, "r", encoding="utf-8") as f:
            doc = json.load(f) or {}
    except FileNotFoundError:
        doc = {}
    except Exception as exc:
        logger.error("[recurring-verify] could not read %s: %s", LEDGER_PATH, exc)
        doc = {}
    doc.setdefault("stale_after_days", DEFAULT_STALE_AFTER)
    doc.setdefault("block_after_days", DEFAULT_BLOCK_AFTER)
    doc.setdefault("events", {})
    return doc


def save_ledger(doc):
    try:
        with open(LEDGER_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.error("[recurring-verify] could not write %s: %s", LEDGER_PATH, exc)


def _key(name):
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _tokens(text):
    return [t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t]


def _distinctive(name):
    return {t for t in _tokens(name) if t not in _STOPWORDS and len(t) > 1}


def _strong_match(recurring_name, live_name):
    """Conservative 'same event' name test: every distinctive token of the
    recurring event must appear in the live event's name."""
    dist = _distinctive(recurring_name)
    if not dist:
        return False
    return dist.issubset(set(_tokens(live_name)))


def _venue_tokens(v):
    return {t for t in _tokens(v) if not t.isdigit() and len(t) > 2 and t not in _VENUE_STOP}


def _venue_agrees(a, b):
    """True if two venue strings clearly name the same place (share a real
    token). Blank on either side is NOT agreement -- handled by callers."""
    ta, tb = _venue_tokens(a), _venue_tokens(b)
    return bool(ta and tb and (ta & tb))


def _days_since(date_str, today_str):
    try:
        d = date.fromisoformat((date_str or "")[:10])
        t = date.fromisoformat((today_str or "")[:10])
        return (t - d).days
    except Exception:
        return None


def tier_for(entry, today_str, ledger):
    """Return (tier, days_since). tier in {dropped, expired, stale, fresh}."""
    status = (entry or {}).get("status", "active")
    if status in ("paused", "dead"):
        return ("dropped", None)
    lv = (entry or {}).get("last_verified")
    if not lv:
        return ("expired", None)  # tracked but never confirmed
    days = _days_since(lv, today_str)
    if days is None:
        return ("stale", None)
    if days > ledger.get("block_after_days", DEFAULT_BLOCK_AFTER):
        return ("expired", days)
    if days > ledger.get("stale_after_days", DEFAULT_STALE_AFTER):
        return ("stale", days)
    return ("fresh", days)


def lookup_tier(name, today_str, ledger):
    """For preflight: (is_tracked, tier, days, entry). Untracked names (not in
    the ledger, i.e. not recurring) return is_tracked=False."""
    entry = ledger.get("events", {}).get(_key(name))
    if entry is None:
        return (False, "untracked", None, None)
    tier, days = tier_for(entry, today_str, ledger)
    return (True, tier, days, entry)


def verify_recurring(recurring_events, live_events, today_str, ledger):
    """Drop dead/paused recurring events; confirm + (for blank-venue events)
    adopt a venue when a live scrape corroborates with an AGREEING venue; flag
    name-matches whose venue disagrees as conflicts. Mutates `ledger` and the
    kept event dicts. Returns (kept_events, report)."""
    events_map = ledger.setdefault("events", {})
    report = {"dropped": [], "live_confirmed": [], "venue_adopted": [],
              "seeded": [], "venue_conflicts": []}
    kept = []
    live = [lv for lv in live_events if (lv.get("source") or "") != "recurring"]

    for ev in recurring_events:
        name = ev.get("name", "")
        k = _key(name)
        entry = events_map.get(k) or {
            "status": "active", "last_verified": None,
            "verified_venue": ev.get("venue", ""), "verified_by": None,
            "verified_through": None, "note": "",
        }

        if entry.get("status") in ("paused", "dead"):
            report["dropped"].append(f"{name} ({entry.get('status')})")
            events_map[k] = entry  # keep so it can be resumed
            continue

        rec_venue = (ev.get("venue") or "").strip()
        name_matches = [lv for lv in live if _strong_match(name, lv.get("name", ""))]

        # A confident corroboration: name matches AND (venue agrees, or one side
        # has no venue to contradict). Prefer such a match if one exists.
        chosen = None
        for lv in name_matches:
            lvv = (lv.get("venue") or "").strip()
            if not rec_venue or not lvv or _venue_agrees(rec_venue, lvv):
                chosen = lv
                break

        if chosen is not None:
            entry["last_verified"] = today_str
            entry["verified_by"] = "live-scrape:" + (chosen.get("source") or "unknown")
            lvv = (chosen.get("venue") or "").strip()
            if lvv:
                entry["verified_venue"] = lvv
                # Only adopt onto the event when the recurring venue was blank
                # (nothing to contradict). A real venue is never overwritten from
                # a loose match -- a differing venue is a conflict, handled below.
                if not rec_venue and lvv != rec_venue:
                    ev["venue_adopted_from"] = rec_venue
                    ev["venue"] = lvv
                    report["venue_adopted"].append(f"{name}: (blank) -> {lvv}")
            entry.pop("pending_venue_conflict", None)
            ev["recurring_confirmed_live"] = True
            report["live_confirmed"].append(name)
        elif name_matches:
            # Name matched but every candidate sits at a DIFFERENT venue: a
            # possible move (or a same-named different event). Never auto-adopt;
            # flag for human confirmation and leave the freshness clock alone.
            lv = name_matches[0]
            lvv = (lv.get("venue") or "").strip()
            entry["pending_venue_conflict"] = {
                "known_venue": rec_venue, "live_venue": lvv,
                "live_name": lv.get("name", ""), "source": lv.get("source", ""),
                "seen": today_str,
            }
            report["venue_conflicts"].append(
                f"{name}: known '{rec_venue}' vs live '{lvv}' "
                f"({lv.get('source', '')}) -- confirm whether it moved")

        if not entry.get("last_verified"):
            # Never corroborated -> start the clock honestly (assumed-current
            # baseline at install, not an independent check).
            entry["last_verified"] = today_str
            entry["verified_by"] = "seed-baseline"
            if not entry.get("verified_venue"):
                entry["verified_venue"] = ev.get("venue", "")
            report["seeded"].append(name)

        events_map[k] = entry
        kept.append(ev)

    return kept, report


def report_lines(ledger, today_str):
    """Human-readable state of every tracked recurring event, worst tier first."""
    order = {"expired": 0, "dropped": 1, "stale": 2, "fresh": 3}
    rows = []
    for name_key, entry in ledger.get("events", {}).items():
        tier, days = tier_for(entry, today_str, ledger)
        rows.append((order.get(tier, 9), tier, name_key, entry, days))
    rows.sort(key=lambda r: (r[0], r[2]))
    out = []
    for _, tier, name_key, entry, days in rows:
        age = f"{days}d" if days is not None else "never"
        line = (f"[{tier:7}] {name_key} | last_verified={entry.get('last_verified')} "
                f"({age}) by={entry.get('verified_by')} venue={entry.get('verified_venue')!r} "
                f"status={entry.get('status')}")
        conflict = entry.get("pending_venue_conflict")
        if conflict:
            line += (f"\n            !! possible move: live '{conflict.get('live_venue')}' "
                     f"({conflict.get('source')}) vs known '{conflict.get('known_venue')}' -- confirm")
        out.append(line)
    return out


def _selftest():
    ledger = {"stale_after_days": 60, "block_after_days": 180, "events": {}}
    today = "2026-06-30"

    recurring = [
        {"name": "Gaymer Night at YBR", "date": "2026-06-29",
         "venue": "Yellow Brick Road, 2630 E 15th St", "source": "recurring"},
        {"name": "Trivia Night at YBR", "date": "2026-06-30",
         "venue": "Yellow Brick Road, 2630 E 15th St", "source": "recurring"},
        {"name": "Queer Women's Collective", "date": "2026-07-01",
         "venue": "", "source": "recurring"},
        {"name": "DRAGNIFICENT! Drag Show", "date": "2026-07-02",
         "venue": "Club Majestic, 124 N Boston Ave", "source": "recurring"},
        {"name": "Ghost Bar Night", "date": "2026-07-03",
         "venue": "Closed Bar", "source": "recurring"},
    ]
    live = [
        # Same event, same venue -> confirm, no adoption, no conflict.
        {"name": "Gaymer Night returns to Yellow Brick Road", "date": "2026-06-29",
         "venue": "Yellow Brick Road", "source": "ybr_ig"},
        # Same NAME token (trivia) but DIFFERENT venue -> conflict, NOT adopted.
        {"name": "Trivia Night", "date": "2026-06-30",
         "venue": "Good Cause Brewing", "source": "eventbrite"},
        # Blank recurring venue -> safe to adopt the live venue.
        {"name": "Queer Women's Collective Tulsa", "date": "2026-07-01",
         "venue": "Dennis R. Neill Equality Center", "source": "okeq"},
        # Generic; must NOT confirm DRAGNIFICENT (no 'dragnificent' token).
        {"name": "A drag show somewhere", "date": "2026-07-02",
         "venue": "Somewhere", "source": "eventbrite"},
    ]
    ledger["events"][_key("Ghost Bar Night")] = {
        "status": "dead", "last_verified": "2026-01-01",
        "verified_venue": "Closed Bar", "verified_by": "human:test", "note": "bar closed"}

    kept, report = verify_recurring(recurring, live, today, ledger)
    kept_names = {e["name"] for e in kept}

    assert "Ghost Bar Night" not in kept_names, "dead event should be dropped"
    # Gaymer Night: confirmed at agreeing venue, NOT adopted (real venue kept).
    g = next(e for e in kept if e["name"] == "Gaymer Night at YBR")
    assert g.get("recurring_confirmed_live") is True, g
    assert g["venue"].startswith("Yellow Brick Road, 2630"), g
    # Trivia: venue disagrees -> conflict flagged, venue NOT changed.
    t = next(e for e in kept if e["name"] == "Trivia Night at YBR")
    assert t["venue"].startswith("Yellow Brick Road"), t
    assert "venue_adopted_from" not in t, "must NOT adopt a conflicting venue"
    te = ledger["events"][_key("Trivia Night at YBR")]
    assert te.get("pending_venue_conflict"), "trivia venue conflict must be recorded"
    assert any("Trivia" in c for c in report["venue_conflicts"]), report["venue_conflicts"]
    # QWC: blank recurring venue -> live venue safely adopted + confirmed.
    q = next(e for e in kept if e["name"] == "Queer Women's Collective")
    assert q["venue"] == "Dennis R. Neill Equality Center", q
    assert any("Queer" in s for s in report["venue_adopted"]), report["venue_adopted"]
    # DRAGNIFICENT not corroborated -> seeded, not falsely confirmed.
    de = ledger["events"][_key("DRAGNIFICENT! Drag Show")]
    assert de["verified_by"] == "seed-baseline", de

    # Tier transitions
    ge = ledger["events"][_key("Gaymer Night at YBR")]
    assert tier_for(ge, today, ledger)[0] == "fresh"
    assert tier_for(ge, "2026-09-01", ledger)[0] == "stale"
    assert tier_for(ge, "2027-01-01", ledger)[0] == "expired"
    assert tier_for({"status": "active", "last_verified": None}, today, ledger)[0] == "expired"
    assert tier_for({"status": "paused"}, today, ledger)[0] == "dropped"

    # Matchers
    assert _strong_match("Gaymer Night at YBR", "Gaymer Night returns to Yellow Brick Road")
    assert not _strong_match("DRAGNIFICENT! Drag Show", "A drag show somewhere")
    assert _venue_agrees("Yellow Brick Road, 2630 E 15th St", "Yellow Brick Road")
    assert not _venue_agrees("AMF Sheridan Lanes", "Dennis R. Neill Equality Center")

    is_tracked, tier, days, _ = lookup_tier("Gaymer Night at YBR", today, ledger)
    assert is_tracked and tier == "fresh"
    assert lookup_tier("Some Untracked One-off", today, ledger)[0] is False

    print("recurring_verify selftest OK")
    print(f"live_confirmed={report['live_confirmed']}")
    print(f"venue_adopted={report['venue_adopted']}")
    print(f"venue_conflicts={report['venue_conflicts']}")
    print(f"seeded={report['seeded']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _selftest()
