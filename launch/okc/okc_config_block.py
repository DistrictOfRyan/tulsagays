# OKCGays — ready-to-paste city config block (drop into config.py at launch).
# Populated from data/okc_launch/okc_sources.md (15 verified sources, 2026-06-15).
# Pairs with the shared, now-portable code: eotw_selector reads GAY_VENUE_SIGNATURES
# from config, so once these are in place the gay-first featuring works for OKC
# with zero code changes. Re-verify the 3 flagged items before launch.
#
# IRREDUCIBLE LAUNCH BLOCKERS (need William): pick + buy a domain (e.g. okcgays.com),
# create the Meta Page + Instagram + OAuth (his login/2FA), wire analytics/Search Console.

# Gay bars / queer venues / LGBTQ org center — ANY event here counts as LGBTQ.
GAY_VENUE_SIGNATURES = (
    "the boom", "2218 nw 39th",
    "tramps", "2201 nw 39th",
    "the park", "2125 nw 39th",
    "angles", "2117 nw 39th",
    "phoenix rising",                      # FB/IG active; re-verify current address
    "district hotel", "habana", "2200 nw 40th",
    "diversity center of oklahoma",        # OKC LGBTQ community center
)

TRUE_GAY_BAR_VENUES = {
    "the boom", "tramps", "the park", "angles", "phoenix rising",
    "district hotel", "habana",
}

QUEER_FRIENDLY_VENUES = {
    "39th street district", "nw 39th",
}

# OKC has TWO real Pride events — Pride on 39th (in the bar district) is the
# community/bar-centered one; recommended as the signature slot.
SIGNATURE_EVENT = {
    "name": "Pride on 39th",
    "name_keywords": ["pride on 39th", "okc pride", "39th street pride"],
    "source_key": "okc_pride",
    "schedule": "June (OKC Pride Inc.)",
    "is_priority_one": True,
}

# Cultural anchor: Canterbury Voices is the verified pick (Oklahoma's oldest
# community choir, not queer-specific). Sing Out! OKC Gay Men's Chorus would be
# the true analog but could NOT be confirmed active in 2026 — re-verify; if live,
# swap it in here as the better anchor.
ANCHOR_CULTURAL_EVENT = {
    "name": "Canterbury Voices",
    "name_keywords": ["canterbury voices", "sing out okc"],
    "source_key": "canterbury_voices",
    "is_priority_two": True,
}

AFFIRMING_VENUE_KEYWORDS_CITY = ["mayflower", "joy mcc", "church of the open arms"]  # re-verify OKC affirming congregations

# Org event sources to add to the scraper registry (verified unless noted):
#   okc_pride            https://www.okcprideinc.org/                  (Pride on 39th)
#   oklahoma_pride_all   Oklahoma Pride Alliance (PrideFest, Scissortail Park)
#   freedom_oklahoma     https://freedomoklahoma.org/                  (statewide advocacy)
#   diversity_center     https://www.diversitycenterofoklahoma.org/events.html
#   pflag_okc            https://pflagoklahomacity.org/events
#   visit_okc_lgbtq      https://www.visitokc.com/lgbtq/
#   district_39th        https://www.39thstreetdistrict.com/
#   ok_gazette_events    https://community.okgazette.com/oklahoma/EventSearch
#   metro_library        https://www.metrolibrary.org/events/upcoming
# EXCLUDE: Oklahomans for Equality / Dennis R. Neill Equality Center (that is TULSA).
