"""
Tulsa Gays Facebook posting targets (curated registry).

This is the allowlist the automated group blaster (posting/group_blast.py)
posts the weekly carousel into, AS the Tulsa Gays Page (never a personal
account). The Page is a member of ~37 groups; this registry curates which
ones are worth posting to and records what we know about each.

Update this file when joining new groups. To re-sync the full joined list,
open facebook.com/groups/joins/ while acting as the Tulsa Gays Page and run
the DOM extractor in posting/group_blast.py --list.

Field reference
---------------
  name      : display name (logging / reports)
  id        : numeric group id OR vanity slug (both work in /groups/<id>)
  members   : approx member count (update quarterly)
  type      : "lgbtq"      Tulsa/OK LGBTQ groups (top priority)
              "lgbtq_okc"  OKC-area LGBTQ (statewide / big Pride events)
              "general"    non-LGBTQ Tulsa events audiences (still on-topic)
  post      : True  -> include in the weekly blast
              False -> skip (marketplace / singles / business / our own page)
  moderated : True  -> posts land in "pending admin approval"
              False -> posts go live immediately
              None  -> unknown / not yet observed
  notes     : freeform

`post`/`moderated` reflect direct observation on 2026-06-01 (first full
manual blast). Live = went live; pending = moderated.
"""

# ── Tulsa Gays Page ────────────────────────────────────────────────────────
# Classic page id (Graph API) and the new-experience profile id (web UI).
FB_PAGE_ID         = "1086906044497675"
FB_PAGE_PROFILE_ID = "61575591958277"
FB_PAGE_URL        = "https://www.facebook.com/profile.php?id=61575591958277"

# ── Facebook Groups ────────────────────────────────────────────────────────
FB_GROUPS = [
    # ---- Tulsa LGBTQ (top priority) ----
    {"name": "Okie Gays", "id": "2612250565491228", "members": 6000,
     "type": "lgbtq", "post": True, "moderated": False,
     "notes": "Largest statewide LGBTQ group. High reach. Posted 2026-06-01."},
    {"name": "Tulsa's LGBT Nightlife", "id": "220878821301627", "members": 2000,
     "type": "lgbtq", "post": True, "moderated": False,
     "notes": "Nightlife focus. Went LIVE 2026-06-01."},
    {"name": "Gay Tulsa", "id": "GayTulsa", "members": 428,
     "type": "lgbtq", "post": True, "moderated": False,
     "notes": "Discrete Tulsa group. Went LIVE 2026-06-01."},
    {"name": "Gay men of Tulsa", "id": "161646500587551", "members": 1400,
     "type": "lgbtq", "post": True, "moderated": False,
     "notes": "Men-focused, broadly relevant. Went LIVE 2026-06-01."},
    {"name": "Tulsa LGBTQ+ Scene", "id": "715281449025002", "members": 3100,
     "type": "lgbtq", "post": True, "moderated": True,
     "notes": "Moderated; admin slow to approve (May post still pending 4wk). "
              "Pending 2026-06-01."},
    {"name": "Rainbow Rebel Society", "id": "rainbowrebelsociety", "members": 375,
     "type": "lgbtq", "post": True, "moderated": True,
     "notes": "Private, moderated. Pending 2026-06-01."},
    {"name": "Tulsa Two Spirit", "id": "tulsa2s", "members": 181,
     "type": "lgbtq", "post": True, "moderated": True,
     "notes": "Queer Indigenous space, Dennis R. Neill Equality Center. "
              "Pending 2026-06-01."},
    {"name": "The Oklahoma Gay-Straight-Trans Alliance Network",
     "id": "182923275119534", "members": 382,
     "type": "lgbtq", "post": True, "moderated": True,
     "notes": "Public but moderated. Pending 2026-06-01."},
    {"name": "Gay, Lesbian and Bisexual 21+ Tulsa Oklahoma",
     "id": "1466742430286583", "members": 1000,
     "type": "lgbtq", "post": True, "moderated": True,
     "notes": "Private, moderated. Pending 2026-06-01."},

    # ---- Oklahoma / statewide LGBTQ ----
    {"name": "GAY OKLAHOMA", "id": "gayoklahoma", "members": 5000,
     "type": "lgbtq", "post": True, "moderated": True,
     "notes": "Large statewide. Private, moderated. Pending 2026-06-01."},
    {"name": "Oklahoma LGBT Event Group", "id": "193672804619496", "members": 2100,
     "type": "lgbtq", "post": True, "moderated": True,
     "notes": "Perfect-fit events group. Moderated. Pending 2026-06-01."},
    {"name": "pansexual/Graysexual LGBTQ+ in OKC", "id": "1097808421083168",
     "members": 1100, "type": "lgbtq_okc", "post": True, "moderated": None,
     "notes": "OKC; post statewide/Pride events."},

    # ---- General Tulsa events audiences (on-topic for an events roundup) ----
    {"name": "What's Up Tulsa?", "id": "WhatsHappeningTulsa", "members": 8400,
     "type": "general", "post": True, "moderated": False,
     "notes": "Huge general Tulsa events group. Went LIVE 2026-06-01."},

    # ---- Legacy-rotation groups, validated live 2026-06-01 ----
    {"name": "Oklahoma House of Drag", "id": "418182474119895", "members": 852,
     "type": "lgbtq", "post": True, "moderated": False,
     "notes": "Public; Page posts go LIVE without joining. Went LIVE 2026-06-01."},
    {"name": "Interesting Things To Do In Tulsa", "id": "InterestingThingsToDoInTulsa",
     "members": 73200, "type": "general", "post": True, "moderated": True,
     "notes": "73K, huge reach. Moderated. Pending 2026-06-01."},
    {"name": "Tulsa Events", "id": "114530202225051", "members": 6500,
     "type": "general", "post": True, "moderated": True,
     "notes": "6.5K general Tulsa. Moderated. Pending 2026-06-01."},

    # ---- Skipped: BLOCK Page accounts entirely (would need a personal
    #      profile -> forbidden by the anonymity rule). Verified 2026-06-01. ----
    {"name": "Black Queer (Tulsa)", "id": "436526440885847", "members": 368,
     "type": "lgbtq", "post": False, "moderated": None,
     "notes": "'This group doesn't allow Pages to join.' Cannot post as the Page."},
    {"name": "Oklahoma Lesbian Friends", "id": "649753022551343", "members": 441,
     "type": "lgbtq", "post": False, "moderated": None,
     "notes": "'This group doesn't allow Pages to join.' Cannot post as the Page."},

    # ---- Skipped: low relevance / wrong format / our own channel ----
    {"name": "Homo(sexual) Hotel Happy Hour (4H)", "id": "homohotelhappyhour",
     "members": None, "type": "lgbtq", "post": False, "moderated": None,
     "notes": "Our own HHHH community group; content originates here. Skip blast."},
    {"name": "LGBT Things for Sale Gay World Tulsa Ok", "id": "609390832473854",
     "members": None, "type": "lgbtq", "post": False, "moderated": None,
     "notes": "Marketplace / for-sale group. Not an events audience."},
    {"name": "OKLAHOMA GAY SINGLES ADMIN ONLY!", "id": "1008350802570027",
     "members": None, "type": "lgbtq", "post": False, "moderated": True,
     "notes": "Admin-only posting + singles focus. Skip."},
    {"name": "Tulsans for Tulsa - Supporting Local Business", "id": "tulsans4tulsa",
     "members": None, "type": "general", "post": False, "moderated": None,
     "notes": "Business-support group, tangential."},
    {"name": "Tulsa Entrepreneurs", "id": "tulsaentrepreneurs",
     "members": None, "type": "general", "post": False, "moderated": None,
     "notes": "Off-topic (business)."},
    {"name": "Gay and Gay Friendly Businesses and Destinations",
     "id": "26575921418", "members": None,
     "type": "general", "post": False, "moderated": None,
     "notes": "Business directory, tangential."},
]


def get_post_targets(include_okc=True, include_general=True):
    """Groups flagged for the weekly blast (post=True).

    include_okc / include_general let a caller restrict to Tulsa-LGBTQ only.
    Ordered: lgbtq (Tulsa) first, then okc, then general — and within each,
    larger / un-moderated first so live posts land before moderated queues.
    """
    targets = [g for g in FB_GROUPS if g.get("post")]
    if not include_okc:
        targets = [g for g in targets if g["type"] != "lgbtq_okc"]
    if not include_general:
        targets = [g for g in targets if g["type"] != "general"]

    type_rank = {"lgbtq": 0, "lgbtq_okc": 1, "general": 2}

    def sort_key(g):
        return (
            type_rank.get(g["type"], 9),
            0 if g.get("moderated") is False else 1,   # live groups first
            -(g.get("members") or 0),                  # bigger first
        )

    return sorted(targets, key=sort_key)


def get_group_url(group):
    return f"https://www.facebook.com/groups/{group['id']}"


if __name__ == "__main__":
    print(f"Tulsa Gays Page: {FB_PAGE_URL}")
    print(f"  classic id={FB_PAGE_ID}  profile id={FB_PAGE_PROFILE_ID}\n")
    targets = get_post_targets()
    skipped = [g for g in FB_GROUPS if not g.get("post")]
    print(f"BLAST TARGETS ({len(targets)} of {len(FB_GROUPS)}):")
    for g in targets:
        mod = {True: "moderated", False: "live", None: "unknown"}[g.get("moderated")]
        mem = f"{g['members']:,}" if g.get("members") else "?"
        print(f"  [{g['type']:9}] {g['name']:<48} {mem:>7}  ({mod})")
    print(f"\nSKIPPED ({len(skipped)}): " + ", ".join(g["name"] for g in skipped))
