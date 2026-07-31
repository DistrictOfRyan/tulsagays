#!/usr/bin/env python3
"""
textclean.py — ONE implementation of the scraper-artifact scrubbers.

Built 2026-07-31 after the same three defects shipped on three different
surfaces because each surface had its own (or no) cleaning:

  * "in 5 days" rendered as the VENUE on 85 live website cards and inside the
    schema.org location name;
  * "6:00 PM8:30 PM18:0020:30" rendered as the TIME on a carousel slide (the
    scraper concatenates 12-hour start, 12-hour end, then the 24-hour range);
  * a raw ?fbclid= URL ran off both edges of a slide.

Import from here rather than re-deriving the patterns. The carousel, the
website generator and the slide renderer all call the same functions, so a fix
lands everywhere at once.

    python content/textclean.py --selftest
"""
from __future__ import annotations

import re
from typing import Optional

__all__ = ["clean_time", "clean_venue_junk", "scrub_copy", "scrub_voice",
           "is_junk_venue", "URL_RE", "REL_DATE_PHRASE_RE", "REL_DATE_BARE_RE",
           "JUNK_VENUE_RE"]

# ── Venue ────────────────────────────────────────────────────────────────────

# Relative dates land in the venue field from Eventbrite / Google Events cards.
JUNK_VENUE_RE = re.compile(
    r'^(in\s+(a|an|\d+)\s+(day|days|hour|hours|week|weeks|month|months)'
    r'|today|tonight|tomorrow|yesterday|this\s+\w+|next\s+\w+|tba|tbd)$', re.I)

# Button text and truncation artifacts that are not venues.
JUNK_VENUE_EXACT = {
    'obtener entradas', 'entradas', 'detalles', 'informacion', 'información',
    'mas informacion', 'más información', 'get tickets', 'buy tickets',
    'tickets', 'tickets & info', 'more info', 'more information', 'mar',
    'online', 'virtual',
}


def is_junk_venue(raw: Optional[str]) -> bool:
    v = (raw or "").strip().rstrip('.!')
    if not v:
        return False
    return bool(JUNK_VENUE_RE.match(v)) or v.lower() in JUNK_VENUE_EXACT


def clean_venue_junk(raw: Optional[str]) -> str:
    """Venue string, or '' when it is a scraper artifact."""
    v = (raw or "").strip()
    return "" if is_junk_venue(v) else v


# ── Time ─────────────────────────────────────────────────────────────────────

_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([ap])\.?m\.?", re.I)
_NARROW_SPACES = (" ", " ", " ")


def clean_time(raw: Optional[str]) -> str:
    """Repair concatenated time strings. Returns '' when nothing is recoverable.

    "6:00 PM8:30 PM18:0020:30" -> "6:00 PM - 8:30 PM"
    "9:45 PM"                  -> "9:45 PM"
    """
    s = (raw or "").strip()
    for ch in _NARROW_SPACES:
        s = s.replace(ch, " ")
    if not s:
        return ""
    found = _TIME_RE.findall(s)
    if not found:
        # Bare 24-hour or unparseable: keep only if short and not a digit run.
        return s if len(s) <= 20 and not re.search(r"\d{4}", s) else ""

    seen, times = set(), []
    for hh, mm, ap in found:
        t = f"{int(hh)}:{mm} {ap.upper()}M"
        if t not in seen:
            seen.add(t)
            times.append(t)
    return f"{times[0]} - {times[1]}" if len(times) >= 2 else times[0]


# ── Copy ─────────────────────────────────────────────────────────────────────

# " at in 5 days", " at TBD" — the venue junk baked into a generated sentence.
REL_DATE_PHRASE_RE = re.compile(
    r'\s+at\s+(in\s+(?:a|an|\d+)\s+(?:day|days|hour|hours|week|weeks|month|months)'
    r'|today|tonight|tomorrow|yesterday|tba|tbd)\b(?=[\s.,!?]|$)', re.I)
# Any remaining bare relative-date fragment, including one whose tail was cut
# off by truncation ("...one. in 6...").
REL_DATE_BARE_RE = re.compile(
    r'\s*\b(in\s+(?:a|an|\d+)\s+(?:day|days|hour|hours|week|weeks|month|months))\b'
    r'|\s+in\s+\d+\s*\.{0,3}\s*$', re.I)
URL_RE = re.compile(r'\S*(?:https?://|www\.|fbclid=)\S*', re.I)

# ── Voice ────────────────────────────────────────────────────────────────────

# Scraped venue blurbs arrive full of AI-marketing filler, and it renders on the
# website cards under William's name. Readers told him the site "reads like AI"
# (2026-07-31), so the same phrases preflight_post.py BLOCKS on a slide are also
# rewritten here, where the website copy is built. Grammar-preserving swaps only.
_VOICE_SUBS = [
    (re.compile(r"\bwhether you're\b", re.I), "if you're"),
    (re.compile(r"\bwhether you are\b", re.I), "if you are"),
    (re.compile(r"\bvibrant community\b", re.I), "community"),
    (re.compile(r"\bsomething for everyone\b", re.I), "plenty going on"),
    (re.compile(r"\bnestled\b", re.I), "tucked"),
    (re.compile(r"\bdon'?t miss out\b", re.I), "come through"),
    (re.compile(r"\bcome one,? come all\b", re.I), "everybody's welcome"),
    (re.compile(r"\bfun for all ages\b", re.I), "all ages"),
    (re.compile(r"\blook no further\b", re.I), "this is it"),
    (re.compile(r"\bhidden gem\b(?![^.]{0,20}Hangout)", re.I), "under-the-radar spot"),
]


def scrub_voice(text: Optional[str]) -> str:
    """Swap AI-marketing filler for plain phrasing. Safe on empty input.

    Keeps the original capitalization, so a phrase that opened the sentence does
    not come back lowercase ("Whether you're new" -> "If you're new").
    """
    t = text or ""
    for rx, rep in _VOICE_SUBS:
        t = rx.sub(lambda m, r=rep: r[0].upper() + r[1:] if m.group(0)[:1].isupper() else r, t)
    return t


def scrub_copy(text: Optional[str], max_token: int = 40) -> str:
    """Clean generated/scraped prose for display.

    Removes relative-date leakage, URLs and tracking params, converts em/en
    dashes (house rule), drops unwrappable long tokens that overflow a slide,
    and tidies the whitespace and punctuation left behind.
    """
    t = (text or "").strip()
    if not t:
        return ""
    t = URL_RE.sub('', t)
    t = REL_DATE_PHRASE_RE.sub('', t)
    t = REL_DATE_BARE_RE.sub('', t)
    t = t.replace('—', ',').replace('–', '-')
    t = scrub_voice(t)
    t = " ".join(tok for tok in t.split() if len(tok) <= max_token)
    t = re.sub(r'\s+([.,!?])', r'\1', t)      # space before punctuation
    t = re.sub(r'\(\s*\)|\[\s*\]', '', t)     # emptied brackets
    t = re.sub(r'\s{2,}', ' ', t).strip()
    t = re.sub(r'[,\s]+([.!?])', r'\1', t)
    t = re.sub(r'(?:\s*\.){2,}$', '.', t)     # ".. " left by a removed clause
    t = t.strip(' ,;')
    # Removing a trailing clause can take the sentence's period with it. Put one
    # back so the copy does not just stop mid-air.
    if t and t[-1] not in '.!?:"\'':
        t += '.'
    return t


# ── Selftest ─────────────────────────────────────────────────────────────────

def _selftest() -> int:
    ok = True

    def chk(cond, msg):
        nonlocal ok
        print(("  ok  " if cond else "  FAIL") + "  " + msg)
        ok = ok and bool(cond)

    print("textclean selftest")

    chk(clean_time("6:00 PM8:30 PM18:0020:30") == "6:00 PM - 8:30 PM",
        "concatenated range with narrow spaces repaired")
    chk(clean_time("2:00 PM5:00 PM") == "2:00 PM - 5:00 PM",
        "double 12-hour range repaired")
    chk(clean_time("9:45 PM") == "9:45 PM", "single time preserved")
    chk(clean_time("7:00 PM - 11:00 PM") == "7:00 PM - 11:00 PM", "clean range preserved")
    chk(clean_time("") == "", "empty time stays empty")

    chk(is_junk_venue("in 5 days") and is_junk_venue("Tomorrow")
        and is_junk_venue("TBD") and is_junk_venue("Obtener entradas"),
        "junk venues detected")
    chk(not is_junk_venue("Club Majestic")
        and not is_junk_venue("Cain's Ballroom, 423 N Main St"),
        "real venues preserved")

    chk(scrub_copy("Summer Meltdown at in 5 days. Getting out there.")
        == "Summer Meltdown. Getting out there.", "'at in N days' clause removed")
    chk("http" not in scrub_copy("Head over to https://x.com/y?fbclid=abc for info"),
        "URL removed")
    chk(scrub_copy("A line that trails off in 6...") == "A line that trails off.",
        "truncated relative-date tail removed")
    chk("—" not in scrub_copy("A line — with a dash"), "em dash converted")
    chk(scrub_copy("Whether you're new or a regular, stop in.")
        == "If you're new or a regular, stop in.", "AI filler phrase rewritten")
    chk("nestled" not in scrub_copy("A bar nestled on Cherry Street."),
        "stock adjective rewritten")
    chk("x" * 45 not in scrub_copy("Tickets " + "x" * 45), "unwrappable token dropped")
    chk(scrub_copy("Claim your corner, sugar, and settle in.")
        == "Claim your corner, sugar, and settle in.", "clean copy untouched")
    chk(scrub_copy("") == "", "empty copy stays empty")

    print("\nSELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
