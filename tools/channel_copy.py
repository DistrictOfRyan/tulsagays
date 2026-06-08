"""
Channel-aware copy derivation + length contracts (nextlevel Rung 4).

One event, four native variants, all from the same voice base so nothing reads
copy-pasted across channels:
  slide       short pitch, hard-capped slide-safe (<= SLIDE_MAX chars)
  web         full website_description (long)
  newsletter  the long copy trimmed to its first 2 sentences
  group       short pitch + a date/venue line + venue-tailored tip

Also exposes the length CONTRACTS preflight enforces so a slide blurb can never
silently overflow the card.

API:
    variants(event) -> dict(slide, web, newsletter, group)
    slide_text(event) -> str         # always slide-safe
    contract_violations(event) -> list[str]   # [] = clean
"""
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SLIDE_MAX = 200        # hard cap for a slide short pitch
SLIDE_SOFT = 150       # target; the generator aims for this
EOTW_LONG_MIN = 180    # the hero needs real substance


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s.strip()]


def slide_text(event):
    """A slide-safe short pitch: prefer description; if missing or too long,
    derive from the long copy's first sentence. Never exceeds SLIDE_MAX."""
    short = (event.get("description") or "").strip()
    if short and len(short) <= SLIDE_MAX:
        return short
    # derive from long copy's first sentence
    longd = (event.get("website_description") or "").strip()
    cand = (_sentences(longd)[0] if longd else short) or short
    if len(cand) > SLIDE_MAX:
        cand = cand[:SLIDE_MAX - 1].rsplit(" ", 1)[0].rstrip(",;:") + "."
    return cand


def newsletter_text(event):
    longd = (event.get("website_description") or event.get("description") or "").strip()
    sents = _sentences(longd)
    return " ".join(sents[:2]) if sents else longd


def group_text(event):
    short = slide_text(event)
    bits = [short]
    when = " ".join(x for x in [event.get("date", ""), event.get("time", "")] if x).strip()
    venue = (event.get("venue") or "").split(",")[0].strip()
    line = " | ".join(x for x in [when, venue] if x)
    if line:
        bits.append(line)
    try:
        from tools.venue_tips import tip_for
        t = tip_for(event)
        if t and t not in short:
            bits.append(t)
    except Exception:
        pass
    return "\n".join(bits)


def variants(event):
    return {
        "slide": slide_text(event),
        "web": (event.get("website_description") or event.get("description") or "").strip(),
        "newsletter": newsletter_text(event),
        "group": group_text(event),
    }


def contract_violations(event, is_eotw=False):
    """Return a list of length-contract violations (empty = clean)."""
    out = []
    short = (event.get("description") or "").strip()
    longd = (event.get("website_description") or "").strip()
    name = event.get("name", "?")
    if short and len(short) > SLIDE_MAX:
        out.append(f"slide short for '{name}' is {len(short)} chars (>{SLIDE_MAX}, will overflow)")
    if is_eotw and longd and len(longd) < EOTW_LONG_MIN:
        out.append(f"EOTW long for '{name}' is {len(longd)} chars (<{EOTW_LONG_MIN}, too thin for the hero)")
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ev = {"name": "Drag Bingo", "venue": "Bricktown Comedy Club Tulsa", "date": "2026-06-14",
          "time": "3 PM", "description": "Porsche Lynn runs the room, 18+, dab those cards.",
          "website_description": "Oklahomans for Equality presents Pride Era Drag Bingo. "
          "Doors at 2, show at 3. Bring singles. It is the most fun you will have on a Sunday."}
    import json
    print(json.dumps(variants(ev), indent=2))
    print("violations:", contract_violations(ev, is_eotw=True))
