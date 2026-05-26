# W22 — FB Group Page-Posting Permission Requests

**Goal:** Get the **Tulsa Gays Page** approved to post in 8+ Tulsa/OK LGBTQ groups so weekly automation can include them.

**Rule:** Tulsa Gays operator is anonymous. Posts originate from the Page, never from Ryan Hunt's personal account.

**Method:** From the Tulsa Gays Page profile, request to join each group. For groups that don't allow Page-as-member, message admins directly with the template below.

---

## Target groups (Tulsa + Oklahoma LGBTQ)

| # | Group | Members | URL | Status |
|---|---|---|---|---|
| 1 | Okie Gays | 6.0K, 9 posts/day | https://www.facebook.com/groups/2612250565491228 | Public — request join as Page |
| 2 | Gay men of Tulsa | 1.3K | (search "Gay men of Tulsa") | Private — request join, may need admin DM |
| 3 | Gay Tulsa | 423 | (search "Gay Tulsa") | Public discrete — request join |
| 4 | Oklahoma's Gay men's social | 2.7K | (search "Oklahoma's Gay men's social") | Public — request join |
| 5 | Gay Men of the Midwest | 42K, 50+ posts/day | (search "Gay Men of the Midwest") | Public — request join (large group, may need admin DM) |
| 6 | Bi or gays in tulsa party and play | 207 | (search "Bi or gays in tulsa party and play") | Public — request join |
| 7 | Tulsa LGBTQ+ Scene | (verify in search) | facebook.com/groups/tulsalgbtqscene (verify) | Verify slug |
| 8 | Tulsa's LGBT Nightlife | (verify) | facebook.com/groups/220878821301627 | From earlier session |
| 9 | pansexual/Graysexual LGBTQ+ in OKC | (verify) | facebook.com/groups/1097808421083168 | From earlier session — OKC, not Tulsa |
| 10 | Tulsa Pride (Page, not group) | — | — | Follow as Page; not for group post |

---

## Per-group request workflow (do once per group, from Tulsa Gays Page)

1. Navigate to group URL while signed in AS Tulsa Gays Page.
2. Click **Join Group** (some groups ask membership questions — fill out per the template below).
3. If "Join" button is greyed out / says "Pages can't join this group":
   - Click **About** to find admin list.
   - Click an admin's name to open their profile.
   - Click **Message** → use the admin-DM template below.
4. Log the result in `data/posts/2026-W22/group_request_log.json`.

---

## Membership question answers (when prompted)

> **Are you in/near Tulsa, OK?**
> Yes — we cover LGBTQIA+ events across the Tulsa metro.

> **Why do you want to join?**
> We run TulsaGays.com — a weekly carousel of every LGBTQIA+ event in town. We'd love to share the weekly roundup with this community so more folks know what's happening.

> **Do you agree to the group rules?**
> Yes. We're a community resource, not promotional spam. We post one weekly roundup, never solicit, and welcome feedback.

> **How did you find us?**
> Through the Tulsa LGBTQIA+ community network.

---

## Admin DM template (for groups that don't allow Page membership)

> Hi [Admin Name],
>
> I help run **TulsaGays.com**, a community resource that publishes every LGBTQIA+ event in Tulsa each week. We're trying to get the weekly roundup in front of more queer folks in town so people stop missing things.
>
> Would you be open to enabling Page posts in [Group Name], or adding the Tulsa Gays Page (facebook.com/tulsagays) as a member? We'd post one weekly carousel on Sunday or Monday — never promotional, never multiple times a week, and we always link directly to the original event organizers.
>
> If a member-only-no-Page rule is the policy, totally understand. Just wanted to ask before assuming.
>
> Thanks for what you do for the community.
> — Tulsa Gays

---

## Tracking

After each request, append to `data/posts/2026-W22/group_request_log.json`:
```json
{
  "group_id": "2612250565491228",
  "group_name": "Okie Gays",
  "requested_at": "2026-05-26T17:30:00",
  "method": "join_as_page" | "admin_dm",
  "admin_messaged": "David Atauvich" (if applicable),
  "result": "pending" | "approved" | "denied" | "blocked_pages_disallowed",
  "approval_note": "..."
}
```

When 8+ are approved, the weekly post automation can include them programmatically.

---

## Why this can't be fully automated tonight

1. **FB blocks Page-as-poster by default in most groups.** Each group admin must explicitly enable Page posts OR approve the Page as a member.
2. **The request UI is per-group and dynamic** — different groups ask different membership questions, different admin DM widgets.
3. **No Graph API endpoint exists** for "join group as Page" or "request Page-post permission" (Meta deprecated all group write APIs in 2024).

Doing it properly = ~5 min per group × 8 groups = ~40 min of attended browser work, ideally with William at the keyboard for any captcha / admin question variations. Then 1-7 day wait for admin approvals.

---

## Next session plan (when William is at the machine for 30+ min)

1. Confirm Chrome signed in as Ryan Hunt → switched to Tulsa Gays Page.
2. Open each group URL above in sequence.
3. Drive join request OR admin DM per the workflow.
4. Log each result in `group_request_log.json`.
5. Schedule a 7-day follow-up to check which were approved.
6. Add approved groups to `posting/facebook.py` so they're included in the weekly automation.
