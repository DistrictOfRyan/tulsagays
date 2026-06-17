# Meta App Review — unlock DM + FB comment tip ingestion

The DM tip auto-ingest pipeline (`tools/ingest_dm_tips.py` + `scraper/dm_sources.py`) is
built and runs daily. Today it pulls from the one channel that needs no review. To turn on
the rest, the @tulsagays Meta app (`1468075241636760`) needs these permissions approved.

## What works TODAY (no review)

| Channel | Permission used | Notes |
|---|---|---|
| `ig_comments` | `instagram_basic` (already on token) | Comments on the page's OWN Instagram media. **Live now** — verified 2026-06-17, returned 11 real comments. The daily task `tulsagays-dm-tip-ingest` already uses this. |

## What needs App Review

| Channel | Permission to request | Graph error today | Unlocks |
|---|---|---|---|
| `ig_messages` | `instagram_manage_messages` | code 230 | @tulsagays Instagram DMs (the main ask) |
| `fb_messages` | `pages_messaging` | code 200 | Facebook Page Messenger inbox |
| `fb_page_comments` | `pages_read_user_content` + **Page Public Content Access** feature | code 10 | Comments other users leave on FB Page posts |

## Submission steps (developers.facebook.com → App `1468075241636760` → App Review)

1. **Business Verification first.** Messaging + page-content permissions require a verified
   business. Settings → Business Verification. Have an EIN / business doc ready. This is the
   slowest gate (days to a couple weeks). Start here.
2. **Add the permissions** under App Review → Permissions and Features. Request:
   `instagram_manage_messages`, `pages_messaging`, `pages_read_user_content`, and the
   `Page Public Content Access` feature.
3. **Use-case write-up** (paste, adjust to taste):
   > TulsaGays is a community events directory for LGBTQ+ events in Tulsa, OK. Community
   > members send event tips to our Instagram and Facebook via DMs and comments. The app
   > reads those inbound messages so an operator can review and publish legitimate event
   > tips to the public events calendar. No message content is shared with third parties;
   > messages are only parsed for event details (name, date, venue) and held in a private
   > review queue.
4. **Screencast** (each requested permission needs one). Record this flow:
   - Show a tester DM/comment arriving at @tulsagays with an event tip.
   - Run `python tools/ingest_dm_tips.py --channels ig_messages` (or the relevant channel).
   - Show the tip appearing in the review queue (`python tools/add_tip.py list`).
   - Show the operator approving it and it landing on tulsagays.com.
   This demonstrates the permission is used for the stated purpose.
5. **App must be in Live mode** with a Privacy Policy URL (tulsagays.com/privacy) and the
   business use clearly described.

## After approval

1. Re-mint the page token so the new scopes are attached (token refresh procedure in the
   tulsagays-domain-expertise skill — the OAuth `scope=` must now also list the approved
   permissions). Write it to `TULSAGAYS_PAGE_ACCESS_TOKEN`.
2. Verify each channel: `python scraper/dm_sources.py --dry-run` — channels should flip
   from `PERMISSION_PENDING` to `ok`.
3. Turn the channels on in the daily task: edit `CHANNELS` in
   `task-runner/tasks/tulsagays_dm_tips.py` (add `ig_messages`, `fb_messages`,
   `fb_page_comments`) or drop the `--channels` flag to pull everything.

## Dev-mode shortcut (optional, for testing before full approval)

Because William is the app admin, permissions work in **Development Mode** for users with a
role on the app (admin/developer/tester). If you add yourself/testers under App Roles, you
can exercise `ig_messages`/`fb_messages` against the @tulsagays account for testing without
waiting for full review — but it will NOT work for the general public until the app is Live
and the permissions are approved. (This is why `ig_comments` already works: own-media
comments don't need any of the gated scopes.)
