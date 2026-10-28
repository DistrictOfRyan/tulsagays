# TulsaGays Weekly Venue Dig — Playbook
*Why this exists: the key venues post their events as IMAGE FLYERS on their own Instagram/Facebook, not as text or FB Events. The automated scraper can't read pictures, and the IG scraping session keeps dying. So a human-in-the-loop (Claude + William's authed browser + vision) has to dig each venue's IG weekly and pull the events onto our calendar. William asked for this repeatedly; it must be a standing weekly step, not a one-time capture.*

## When
Weekly, before the Monday post prep (Sunday or Monday morning). Runs in a live session (needs the authed browser + vision — cannot be fully unattended).

## How (the loop)
0. **Read the @tulsagays Instagram DMs first** (added 2026-10-26). Nothing reads them automatically: the Graph token lacks `instagram_manage_messages` (code 230) and the instagrapi DM session is gone, so `tulsagays-dm-tip-ingest` only sees post comments. Open `https://business.facebook.com/latest/inbox/instagram_direct?asset_id=1086906044497675` in the personal Chrome and work every thread newer than the last dig:
   - **Event flyer or details** → `python tools/add_tip.py add --text "<what the flyer says>" --channel ig --submitted-by "@handle"`, then review/approve as usual. Open each image with vision; most submissions arrive as a flyer with no text.
   - **Correction to a listed event** → fix the row in `data/manual_events.json` / `venue_overrides.json` the same day.
   - **Directory request** (add/remove/edit a listing) → apply it and log it in `data/directory_log.md`.
   - **Spam** ("my roommate thinks you're cute", "text me on snap", "I'm messaging from my alt") → Move to spam. Never reply.
   - **Replies to people are messages** → draft them and get William's yes before sending (stage-never-send).
   The Business Suite auto-reply answers each person's first message by telling them to email events@tulsagays.com. Many people send the flyer here and never email, so this step is the only place those events get caught (2026-10-26: a weekly Thursday queer Bible study at College Hill Presbyterian, sent twice in August, never reached the calendar).
   - **The auto-reply is not an answer.** A thread whose last line is "You: Thanks for the message! Got an event?..." still has a person waiting if their real message above it never got a human reply. Open it and reply. The first 2026-10-28 review missed T's "Yes! Every Thursday!" this way, and William caught it.
   Cadence: every 3 days (William, 2026-10-28: "I need you to go through these every 3 or 4 days"). `python C:\Users\willi\.claude\scripts\tulsagays_ig_dm_due.py` says when it's due; log each review with its `log` subcommand.
1. In a session, resolve the personal Chrome with `python C:\Users\willi\.claude\scripts\browser_for.py personal` (it prints the live deviceId; 394a57e9, named here until 2026-10-28, is quarantined as a mixed-identity Chrome) and `select_browser` it. It's already logged into Facebook/Instagram. On instagram.com, check the account switcher says tulsagays before reading (the same Chrome is also signed in as districtofryan and homohotelhappyhour).
2. For each venue below, open their Instagram profile, screenshot the recent posts grid, and OPEN each event-looking flyer post. Read the flyer WITH VISION (dates, times, theme names, host). Their FB Events tabs are mostly empty — IG is the source.
3. Extract DATED one-off / themed events (skip the plain recurring baseline already in scraper/recurring.py, but DO capture the fun themed name when a recurring night has one — e.g. YBR's 2nd-Friday DJ Kylie night was themed "ZODIAC").
4. Add each to `data/manual_events.json` (source=manual, include name, date YYYY-MM-DD, time, venue, url=the IG post, a website_description). One object per date for multi-day.
5. Re-run generate/website so they land on the site + carousel. Log what was added.

## Venues to dig (verified handles, 2026-07-11)
| Venue | Instagram | Notes |
|---|---|---|
| Yellow Brick Road (YBR) | @tulsaybr | Lesbian bar. FB Events EMPTY, bio says "MUCH more active on Instagram." Recurring schedule already in recurring.py (verified vs their Monthly Events flyer). Dig for themed names (ZODIAC = 2nd-Fri DJ Kylie) + true one-offs. |
| Club Majestic | @clubmajestictulsa | Drag/DJ nights. DRAGNIFICENT + Sunday Showdown recurring. Dig for special drag shows, touring performers. |
| Tulsa Eagle | @tulsaeagle | Leather/levi bar. IG-only (site DNS-dead). Friday drag, Tuesday karaoke + specials. |
| Elote Cafe | @elotetulsa | Drag brunch ("Stars, Stripes & Sequins" etc.) + one-off queer nights. |
| Tulsa House of Drag | @tulsahouseofdrag | Drag productions, touring shows. |
| Studio 66 | @studio.66_ | Arts/community programming. |
| KLASSIC | @upflykai | Drag/nightlife. |
| Goff Center | @goff_fest | Queer arts/fest. |
| HotMess Sports Tulsa | @hotmesssportstulsa | LGBTQ+ rec sports (kickball/dodgeball seasons). |
| PFLAG Tulsa | @pflagtulsa | Community partner; special events (e.g. Transforming Insight into Impact). |

## Rules
- ANONYMOUS: only READ their pages. Never like/comment/DM/follow from this dig (no engagement that could out the operator or spam).
- No fabrication: only add events actually seen on a flyer, with the real date. If a date is ambiguous, skip or flag.
- Themed recurring nights: update the display name to the themed one for that week if it's clearly the same slot.
- After adding, the venue is better represented and you can honestly tell them "we've got you this week."
