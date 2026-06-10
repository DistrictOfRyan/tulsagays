# W22 FB Group Posting — Handoff for Next Session

## Status: BLOCKED — Tulsa Gays Page not navigable from Ryan's FB web session

The Tulsa Gays Page (page_id `1086906044497675`) is reachable via Graph API
(both IG and FB Page posts published successfully tonight) but does not
appear in FB search from Ryan's personal account, and the post permalink
returns "content not available." Either the Page is hidden, the handle
isn't set, or the web session isn't currently linked as admin (the API
token still works because it's a page_access_token from a prior auth).

## Decision Tree for Next Session

### Option A — Post AS Tulsa Gays Page in groups that allow Page-posting
1. Open Chrome, log in to FB as Ryan
2. Top-right profile dropdown → Switch profile → Tulsa Gays Page
3. Navigate to each target group below
4. If group shows "Post as Page" — post caption + slides
5. If group shows "Pages cannot post here" — skip (preserves anonymity)

### Option B — Page requests to join groups, then posts (1-7 day wait)
1. Switch to Tulsa Gays Page profile
2. For each group → click "Join group" (as Page)
3. Admin approves
4. Once approved, batch post

### Option C — Create a separate brand persona (not Ryan)
1. Create a fresh FB account for "Tulsa Gays" (or use existing alt)
2. Join all target LGBTQ groups manually
3. Post as that persona — preserves Ryan's anonymity, gives the brand
   a real identity for community engagement

## Target Groups (need 8+)

| Group                          | Privacy | Members | URL                                                       |
|--------------------------------|---------|---------|-----------------------------------------------------------|
| Okie Gays                      | Public  | 6.0K    | https://www.facebook.com/groups/2612250565491228          |
| Gay men of Tulsa               | Private | 1.3K    | (FB search "Gay men of Tulsa")                            |
| Gay Tulsa                      | Public  | 423     | (FB search "Gay Tulsa" — Discrete Group)                  |
| Tulsa LGBTQ+ Scene             | ?       | ?       | (recover URL from FB activity log of prior session)       |
| Tulsa's LGBT Nightlife         | ?       | ?       | https://www.facebook.com/groups/220878821301627           |
| pansexual/Graysexual LGBTQ+ OKC| ?       | ?       | https://www.facebook.com/groups/1097808421083168          |

Find 2-3 more via FB search → Groups filter → "tulsa", "oklahoma lgbtq",
"queer oklahoma".

## Ready Assets

**Caption:** `data/posts/2026-W22/all_post.json` → field `caption`

**Slide PNGs (local):**
- `C:\Users\willi\tulsagays\data\posts\2026-W22\all__01.png` through `all__09.png`

**Slide PNGs (GitHub public URLs):**
- https://raw.githubusercontent.com/DistrictOfRyan/tulsagays/main/data/posts/2026-W22/all__01.png
- ... through `all__09.png`

## What's Already Posted (do NOT re-post these)
- IG @tulsagays: `17979829625852759` ✅
- Tulsa Gays FB Page: `1086906044497675_122114354504853065` ✅
- Website tulsagays.com EOTW banner ✅
