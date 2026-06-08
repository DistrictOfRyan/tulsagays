"""
Tailored "best-time" tips by venue (nextlevel Rung 3).

Gives each event a tip genuinely specific to its venue/type instead of a generic
"just show up" line — reliably, even when LLM enrichment falls back to rule-based
copy. Reads data/venue_profiles.json (category-true, conservative tips; no
fabricated specifics). Used by the description pipeline (dedupe_descriptions,
rule-based enrich) to close a long description with a real, useful tip.

API:
    tip_for(event) -> str   # tailored tip, or "" if no confident match
    category_of(event) -> str|None
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_PROFILES = ROOT / "data" / "venue_profiles.json"
_cache = None


def _load():
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_PROFILES.read_text(encoding="utf-8"))
        except Exception:
            _cache = {"venues": [], "category_fallback": {}}
    return _cache


def _haystack(event):
    return " ".join([
        (event.get("venue") or ""),
        (event.get("name") or ""),
        (event.get("location") or ""),
    ]).lower()


def category_of(event):
    hay = _haystack(event)
    for v in _load().get("venues", []):
        if any(m.lower() in hay for m in v.get("match", [])):
            return v.get("category")
    return None


def tip_for(event):
    """Return a venue-tailored tip for the event, or '' if no confident match."""
    hay = _haystack(event)
    data = _load()
    for v in data.get("venues", []):
        if any(m.lower() in hay for m in v.get("match", [])):
            return v.get("tip", "")
    # category fallback only fires if a category keyword is obvious in the name
    name = (event.get("name") or "").lower()
    fb = data.get("category_fallback", {})
    for cat, kw in (("comedy", "comedy"), ("drag", "drag"), ("art", "gallery"),
                    ("outdoor", "park"), ("music_venue", "concert")):
        if kw in name and cat in fb:
            return fb[cat]
    return ""


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    samples = [
        {"name": "Drag Bingo", "venue": "Bricktown Comedy Club Tulsa"},
        {"name": "Friday Night", "venue": "Tulsa Eagle"},
        {"name": "Pride Yoga", "venue": "Guthrie Green"},
        {"name": "Banned Book Club", "venue": "Kendall-Whittier Library"},
        {"name": "Random Thing", "venue": "Some Unknown Place"},
    ]
    for s in samples:
        print(f"{s['venue']:32} -> {tip_for(s) or '(no tip)'}")
