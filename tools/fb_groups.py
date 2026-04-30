"""
Tulsa Gays Facebook posting targets.

Update this file when joining new groups or when IDs are confirmed.
IDs marked "TBD" require manual verification via Facebook Group URL
(facebook.com/groups/<id>) or the Graph API.

The page URL to use is FB_PAGE_URL — the /tulsagays vanity URL does not
resolve correctly. Always use the profile.php?id= form.
"""

# ── Tulsa Gays Page ────────────────────────────────────────────────────────
FB_PAGE_ID  = "1086906044497675"
FB_PAGE_URL = "https://www.facebook.com/profile.php?id=61575591958277"

# ── Facebook Groups ────────────────────────────────────────────────────────
# Each entry:
#   name    : display name for logging / posting scripts
#   id      : Facebook group ID (string) — "TBD" if not yet confirmed
#   members : approximate member count (update quarterly)
#   type    : "lgbtq" for Tulsa/OK LGBTQ groups, "lgbtq_okc" for OKC-area
#
# Posting priority: lgbtq (Tulsa) first, lgbtq_okc second.
# Groups marked TBD still need ID confirmation before automated posting.

FB_GROUPS = [
    {
        "name": "Okie Gays",
        "id": "2612250565491228",
        "members": 6000,
        "type": "lgbtq",
        "notes": "Largest statewide LGBTQ group. High reach.",
    },
    {
        "name": "Tulsa LGBTQ+ Scene",
        "id": "715281449025002",
        "members": 2900,
        "type": "lgbtq",
        "notes": "Tulsa-specific. Good local engagement.",
    },
    {
        "name": "Tulsa's LGBT Nightlife",
        "id": "220878821301627",
        "members": 1900,
        "type": "lgbtq",
        "notes": "Nightlife focus — good for bar/drag event posts.",
    },
    {
        "name": "Gay Men of Tulsa",
        "id": "161646500587551",
        "members": 1400,
        "type": "lgbtq",
        "notes": "Men-focused but broadly relevant for events.",
    },
    {
        "name": "pansexual/Graysexual LGBTQ+ in OKC",
        "id": "1097808421083168",
        "members": 1100,
        "type": "lgbtq_okc",
        "notes": "OKC-based but statewide reach. Post statewide/Pride events here.",
    },
    {
        "name": "Oklahoma LGBT Event Group",
        "id": "TBD",
        "members": 2000,
        "type": "lgbtq",
        "notes": "ID not yet confirmed. Check facebook.com/groups/oklahomalgbteventgroup",
    },
    {
        "name": "Gay Tulsa",
        "id": "TBD",
        "members": 409,
        "type": "lgbtq",
        "notes": "Smaller group. ID not confirmed.",
    },
    {
        "name": "Bi or gays in tulsa party and play",
        "id": "TBD",
        "members": 203,
        "type": "lgbtq",
        "notes": "Small group. ID not confirmed. Confirm before posting.",
    },
    {
        "name": "Tulsa Two Spirit",
        "id": "tulsa2s",
        "members": 177,
        "type": "lgbtq",
        "notes": "ID appears to be a username, not a numeric ID. Verify before posting.",
    },
    {
        "name": "OKC Area LGBTQ+ Events",
        "id": "TBD",
        "members": 14000,
        "type": "lgbtq_okc",
        "notes": "Largest OKC group. Post for big Tulsa events with statewide draw.",
    },
]


def get_confirmed_groups(group_type=None):
    """Return only groups with confirmed (numeric) IDs.

    group_type: None (all), "lgbtq", or "lgbtq_okc"
    """
    confirmed = [g for g in FB_GROUPS if g["id"] != "TBD" and g["id"].isdigit()]
    if group_type:
        confirmed = [g for g in confirmed if g["type"] == group_type]
    return confirmed


def get_tulsa_groups():
    """Return confirmed Tulsa LGBTQ groups only (excludes OKC)."""
    return get_confirmed_groups("lgbtq")


if __name__ == "__main__":
    print(f"Facebook Page: {FB_PAGE_URL}")
    print(f"Page ID:       {FB_PAGE_ID}\n")
    all_confirmed = get_confirmed_groups()
    print(f"Confirmed groups ({len(all_confirmed)} of {len(FB_GROUPS)}):")
    for g in all_confirmed:
        print(f"  [{g['type']:10}] {g['name']:<40} id={g['id']}  ({g['members']:,} members)")
    print()
    pending = [g for g in FB_GROUPS if g["id"] == "TBD" or not g["id"].isdigit()]
    if pending:
        print(f"Groups with TBD IDs ({len(pending)}) — confirm before automated posting:")
        for g in pending:
            print(f"  {g['name']} ({g['members']:,} members) — {g.get('notes','')}")
