"""Dynamic source layer for the TulsaGays scraper.

The weekly source-growth engine (self_improve/source_discovery.py +
tools/promote_sources.py) GROWS the scraper's coverage by appending to
``data/dynamic_sources.json`` -- it never edits the hardcoded source lists in
the .py files. This module reads that JSON and exposes the additions so the
existing scrapers can merge them with their built-in lists.

Why JSON instead of editing code: appending to a data file is safe and
idempotent. Programmatically rewriting Python source risks a syntax error that
would silently break Monday's full scrape. Promotion = append-to-JSON, always.

Schema of data/dynamic_sources.json::

    {
      "fb_pages":         [{"url": "...", "name": "...", "added": "YYYY-MM-DD", "via": "..."}],
      "fb_groups":        [{"url": "...", "name": "...", "added": "YYYY-MM-DD", "via": "..."}],
      "calendars":        [{"url": "...", "name": "...", "category": "...", "added": "...", "via": "..."}],
      "partner_keywords": [{"kw": "...",  "name": "...", "added": "...", "via": "..."}]
    }

This module is intentionally dependency-free (no ``import config``) so that
``config.py`` can import it without a circular import.
"""

import os
import json
import logging

logger = logging.getLogger(__name__)

# data/ lives one level up from scraper/
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DYNAMIC_SOURCES_FILE = os.path.join(_DATA_DIR, "dynamic_sources.json")

_EMPTY = {"fb_pages": [], "fb_groups": [], "calendars": [], "partner_keywords": []}


def _load():
    """Load dynamic_sources.json, returning the empty structure on any problem.

    A missing or corrupt file must NEVER break the scraper -- it just means no
    dynamic additions this run.
    """
    if not os.path.exists(DYNAMIC_SOURCES_FILE):
        return dict(_EMPTY)
    try:
        with open(DYNAMIC_SOURCES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Defensive: ensure every key exists and is a list
        out = dict(_EMPTY)
        for k in _EMPTY:
            v = data.get(k)
            if isinstance(v, list):
                out[k] = v
        return out
    except Exception as e:
        logger.warning("[dynamic_sources] Could not read %s: %s", DYNAMIC_SOURCES_FILE, e)
        return dict(_EMPTY)


def fb_page_urls():
    """Return dynamic Facebook page event-tab URLs (list of strings)."""
    return [e["url"] for e in _load()["fb_pages"] if e.get("url")]


def fb_group_urls():
    """Return dynamic Facebook group event-tab URLs (list of strings)."""
    return [e["url"] for e in _load()["fb_groups"] if e.get("url")]


def calendar_sites():
    """Return dynamic calendar sites as (url, name, category, False) tuples.

    The trailing False matches extended_calendars.SITES' ``requires_keyword``
    slot: dynamic calendars are kept on community relevance, not a hard keyword.
    """
    out = []
    for e in _load()["calendars"]:
        if e.get("url"):
            out.append((e["url"], e.get("name", e["url"]), e.get("category", "community"), False))
    return out


def partner_keywords():
    """Return dynamic community-partner keyword strings (lowercased)."""
    return [e["kw"].lower() for e in _load()["partner_keywords"] if e.get("kw")]


def merge_unique(base, additions):
    """Append ``additions`` to ``base`` preserving order, skipping duplicates.

    Works for both list-of-strings and list-of-tuples (compares by first
    element for tuples so a re-added URL with a different label is still a dup).
    """
    def key(x):
        return x[0].lower() if isinstance(x, tuple) else str(x).lower()

    seen = {key(x) for x in base}
    out = list(base)
    for a in additions:
        if key(a) not in seen:
            seen.add(key(a))
            out.append(a)
    return out


if __name__ == "__main__":
    d = _load()
    print("dynamic_sources.json contents:")
    for k in _EMPTY:
        print(f"  {k}: {len(d[k])}")
    print("fb_pages:", fb_page_urls())
    print("fb_groups:", fb_group_urls())
    print("calendars:", calendar_sites())
    print("partner_keywords:", partner_keywords())
