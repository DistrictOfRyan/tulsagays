"""Shared word-boundary keyword matching for the per-scraper LGBTQ pre-filters.

The per-scraper filters historically did plain substring matching
(`any(kw in combined for kw in LGBTQ_KEYWORDS)`), which admits false
positives: "bi" fires inside "bingo" and "billion", "drag" inside "dragon",
"market" inside "supermarket", "wiz" inside "wizard". scraper/runner.py's
downstream gate was fixed to word-boundary matching on 2026-06-12; this module
brings the upstream pre-filters in line so junk never enters the pipeline at
all (fixed 2026-07-07, prompted by Circle Cinema keeping an alien sci-fi film
because "bi" matched "eight billion people").

Matching rules, mirroring runner.py's _LGBTQ_IDENTITY_RX:
- Boundaries are (?<![a-z0-9]) ... (?![a-z0-9]), so punctuation counts as a
  boundary: "LGBTQ+" and "gay-bingo" slugs still match.
- An optional trailing "s" keeps plurals working ("screenings", "night
  markets", "drag queens") -- substring matching used to catch these for free.
- Word boundaries stop short stems from matching their long forms ("trans" no
  longer hits "transgender"), so IDENTITY_SUPPLEMENTS adds the long forms
  explicitly to every compiled pattern.
"""

import re
from typing import Iterable, Pattern

# Long-form identity terms the old substring stems used to catch implicitly
# ("bi" -> bisexual, "trans" -> transgender, "lgbtq" -> lgbtqia, "gender" ->
# genderqueer/genderfluid). Added to every compiled LGBTQ pattern so the move
# to word boundaries loses no coverage. "lgbt" and "pflag" match runner.py's
# identity list.
IDENTITY_SUPPLEMENTS = [
    "lgbt", "lgbtqia", "bisexual", "transgender", "genderqueer",
    "genderfluid", "pflag",
]


def compile_lgbtq_keywords(keywords: Iterable[str]) -> Pattern:
    """Compile an LGBTQ keyword list into a word-boundary regex.

    Longest-first alternation so multi-word phrases win over their own
    substrings; case-insensitive matching is handled by lowercasing here
    rather than callers pre-lowering their combined text (they still do,
    harmlessly)."""
    terms = list(dict.fromkeys(
        [k.strip().lower() for k in keywords if k and k.strip()] + IDENTITY_SUPPLEMENTS
    ))
    alts = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(r"(?<![a-z0-9])(?:" + alts + r")s?(?![a-z0-9])", re.IGNORECASE)


if __name__ == "__main__":
    # Selftest: python scraper/relevance.py
    rx = compile_lgbtq_keywords([
        "lgbtq", "queer", "gay", "lesbian", "bi", "trans", "drag", "pride",
        "gender", "market", "wiz", "screening", "night market",
    ])
    positives = [
        "LGBTQ+ Mixer", "Gay Bingo Night", "gay-bingo-tickets-tulsa",
        "Transgender Day of Remembrance", "Bisexual Visibility Panel",
        "Drag Queens of Tulsa", "Night Markets return", "The Wiz",
        "Free screenings all week", "Genderqueer meetup", "PFLAG Tulsa",
        "Pride Picnic", "trans rights rally", "Bi visibility",
    ]
    negatives = [
        "Family Bingo Night", "eight billion people", "Dragon Boat Festival",
        "Supermarket Tour", "Wizard of Oz", "Big Band Dance",
        "Gaylord Hotel Expo", "Transit Authority Meeting",
        "Binary Star Lecture at the Planetarium", "Gendarme history talk",
    ]
    failed = 0
    for p in positives:
        if not rx.search(p.lower()):
            print(f"FAIL positive: {p!r}")
            failed += 1
    for n in negatives:
        if rx.search(n.lower()):
            print(f"FAIL negative: {n!r} matched {rx.search(n.lower()).group(0)!r}")
            failed += 1
    print(f"selftest: {len(positives)} positives, {len(negatives)} negatives, {failed} failures")
    raise SystemExit(1 if failed else 0)
