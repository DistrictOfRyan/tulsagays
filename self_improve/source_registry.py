"""Candidate-source registry for the weekly source-growth engine.

One JSON file, ``data/source_candidates.json``, is the single source of truth
for sources that have been *discovered* but not yet wired into the live
scraper. The weekly engine writes candidates here; tools/promote_sources.py
reads them, auto-promotes the strong ones into data/dynamic_sources.json, and
queues the medium ones for William's review.

Candidate schema::

    {
      "id":            "fb_page::facebook.com/example",   # stable dedup key
      "type":          "fb_page | fb_group | calendar | venue_keyword | org_keyword",
      "name":          "Human-readable name",
      "url":           "https://...",        # for fb_page/fb_group/calendar
      "kw":            "example venue",       # for venue_keyword/org_keyword
      "category":      "community",           # for calendar
      "confidence":    0-100,
      "evidence":      "why this is a real, Tulsa, queer/queer-welcoming source",
      "discovered_at": "YYYY-MM-DD",
      "discovered_via":"weekly-search:... | venue-miner",
      "status":        "candidate | promoted | queued | rejected",
      "promoted_at":   null
    }
"""

import os
import sys
import json
import re
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from scraper import dynamic_sources as dyn

logger = logging.getLogger(__name__)

CANDIDATES_FILE = os.path.join(config.DATA_DIR, "source_candidates.json")

VALID_TYPES = {"fb_page", "fb_group", "calendar", "venue_keyword", "org_keyword"}


# ── dedup-key helpers ────────────────────────────────────────────────────────
def _norm_url(url: str) -> str:
    u = (url or "").strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    u = u.rstrip("/")
    u = re.sub(r"/events$", "", u)   # treat page and page/events as the same source
    return u


def _norm_kw(kw: str) -> str:
    return re.sub(r"\s+", " ", (kw or "").strip().lower())


def candidate_id(ctype: str, url: str = "", kw: str = "") -> str:
    if ctype in ("fb_page", "fb_group", "calendar"):
        return f"{ctype}::{_norm_url(url)}"
    return f"{ctype}::{_norm_kw(kw)}"


# ── load / save ──────────────────────────────────────────────────────────────
def load() -> list:
    if not os.path.exists(CANDIDATES_FILE):
        return []
    try:
        with open(CANDIDATES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("[registry] could not read %s: %s", CANDIDATES_FILE, e)
        return []


def save(candidates: list) -> None:
    config.ensure_dirs()
    with open(CANDIDATES_FILE, "w", encoding="utf-8") as f:
        json.dump(candidates, f, indent=2, ensure_ascii=False)


# ── what the live scraper already covers (so we never re-suggest it) ─────────
def known_keys() -> set:
    """Build the set of dedup keys already represented in the LIVE scraper.

    Covers: config.SOURCES urls, COMMUNITY_PARTNER_KEYWORDS, true/queer venue
    sets, dynamic_sources.json, and the hardcoded FB page/group + calendar
    lists. Discovery dedups against this so it only ever surfaces NEW sources.
    """
    keys = set()

    # config partner keywords + venue sets
    for kw in getattr(config, "COMMUNITY_PARTNER_KEYWORDS", []):
        keys.add(candidate_id("venue_keyword", kw=kw))
        keys.add(candidate_id("org_keyword", kw=kw))
    for vs in ("TRUE_GAY_BAR_VENUES", "QUEER_FRIENDLY_VENUES"):
        for kw in getattr(config, vs, set()):
            keys.add(candidate_id("venue_keyword", kw=kw))
    for src in getattr(config, "SOURCES", {}).values():
        u = src.get("url", "")
        if u:
            keys.add(candidate_id("fb_page", url=u))
            keys.add(candidate_id("calendar", url=u))

    # dynamic_sources.json (already-promoted)
    for u in dyn.fb_page_urls():
        keys.add(candidate_id("fb_page", url=u))
    for u in dyn.fb_group_urls():
        keys.add(candidate_id("fb_group", url=u))
    for (u, _n, _c, _b) in dyn.calendar_sites():
        keys.add(candidate_id("calendar", url=u))
    for kw in dyn.partner_keywords():
        keys.add(candidate_id("venue_keyword", kw=kw))
        keys.add(candidate_id("org_keyword", kw=kw))

    # hardcoded FB page/group lists + calendar SITES (import lazily to avoid
    # pulling playwright at module import time)
    try:
        from scraper import facebook_events as fbe
        for u in getattr(fbe, "PAGE_URLS", []):
            keys.add(candidate_id("fb_page", url=u))
        for u in getattr(fbe, "GROUP_URLS", []):
            keys.add(candidate_id("fb_group", url=u))
    except Exception as e:
        logger.debug("[registry] facebook_events import skipped: %s", e)
    try:
        from scraper import extended_calendars as ec
        for site in getattr(ec, "SITES", []):
            keys.add(candidate_id("calendar", url=site[0]))
    except Exception as e:
        logger.debug("[registry] extended_calendars import skipped: %s", e)

    return keys


# ── add a candidate (deduped) ────────────────────────────────────────────────
def known_partner_substrings() -> set:
    """Raw lowercased keyword strings already trusted (config + dynamic).

    Used for SUBSTRING dedup: a mined venue "shambhala meditation center of
    tulsa" must be recognized as already-known because "shambhala" is a trusted
    partner keyword. Exact-id matching alone misses these.
    """
    subs = set()
    for kw in getattr(config, "COMMUNITY_PARTNER_KEYWORDS", []):
        subs.add(_norm_kw(kw))
    for vs in ("TRUE_GAY_BAR_VENUES", "QUEER_FRIENDLY_VENUES"):
        for kw in getattr(config, vs, set()):
            subs.add(_norm_kw(kw))
    for kw in dyn.partner_keywords():
        subs.add(_norm_kw(kw))
    return {s for s in subs if s}


def add_candidate(ctype, name, url="", kw="", category="community",
                  confidence=0, evidence="", discovered_via="weekly", discovered_at=None):
    """Insert a candidate if it's new. Returns "added" | "exists" | "known" | "invalid".

    - "known"   : already in the live scraper -> skip
    - "exists"  : already in the candidate registry -> skip
    - "added"   : newly recorded
    """
    if ctype not in VALID_TYPES:
        return "invalid"
    cid = candidate_id(ctype, url=url, kw=kw)
    if cid in known_keys():
        return "known"

    # Substring dedup for keyword candidates: skip if an already-trusted keyword
    # is contained in (or contains) the candidate keyword.
    if ctype in ("venue_keyword", "org_keyword"):
        nk = _norm_kw(kw)
        for known in known_partner_substrings():
            if known and (known in nk or nk in known):
                return "known"

    candidates = load()
    if any(c.get("id") == cid for c in candidates):
        return "exists"

    if discovered_at is None:
        # caller (scheduled task) should pass today's date; fall back to file mtime-free stamp
        discovered_at = os.environ.get("SOURCE_GROWTH_DATE", "")

    candidates.append({
        "id": cid,
        "type": ctype,
        "name": name,
        "url": url,
        "kw": kw,
        "category": category,
        "confidence": int(confidence),
        "evidence": evidence,
        "discovered_at": discovered_at,
        "discovered_via": discovered_via,
        "status": "candidate",
        "promoted_at": None,
    })
    save(candidates)
    return "added"


def pending() -> list:
    """Candidates not yet promoted/queued/rejected."""
    return [c for c in load() if c.get("status") == "candidate"]


def set_status(cid: str, status: str, when: str = None) -> None:
    candidates = load()
    for c in candidates:
        if c.get("id") == cid:
            c["status"] = status
            if status == "promoted":
                c["promoted_at"] = when or ""
            break
    save(candidates)


if __name__ == "__main__":
    cands = load()
    print(f"{len(cands)} candidates in registry; {len(pending())} pending")
    print(f"{len(known_keys())} keys already covered by the live scraper")
