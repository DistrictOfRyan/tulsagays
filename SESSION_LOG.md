## [2026-06-17 10:15] TulsaGays community-tip pipeline + voice engine + ceiling climb

Built end-to-end community event-tip ingestion (official Graph API collectors + instagrapi DM bridge, flyer/link site enrichment, guardrailed auto-reply, spotlight self-promo footer), rebuilt the description voice engine (Dolly/RuPaul variant bank + banned-filler guards across generator/preflight/editor), rewrote the 5 live queued tips in voice, and ran /ceiling on both nextlevel ladders to the wall (sponsor page + rate card, public events API, OKC replication scaffold, editorial policy/calendar, membership concept).

**Main artifact:** tools/ingest_dm_tips.py + scraper/dm_sources.py + scraper/dm_instagrapi.py + tools/enrich_tip_links.py; docs/sponsor.html; docs/api/events.json
**Open items:** instagrapi re-auth (2FA), Meta App Review submit, sign sponsors, OKC domain+OAuth, billing processor - all in pending-william-actions.md

---

## [2026-06-15 14:30] W24 quality overhaul - sanity checker, time fix, Majestic unban, bar IG sources, voice reliability

Fixed everything William flagged in the W24 site review. Built tools/sanity_check_events.py (rules + chunked-haiku LLM verdicts) wired into scrape (pre-save), generate, and preflight - quarantines civic/chamber meetings (Owasso city council class), kids programming, sports games, cert courses, junk names; flags implausible times + truncated/mojibake names; manual + LGBTQ-source events can never be LLM-dropped. Fixed unicode thin-space time ranges ("6 - 10 PM" rendered END as start - that is why soda-bottle conv showed 10pm) in scraper normalizer + website format_time/_parse_minutes + slide sorter. Reworked relevance: word-boundary LGBTQ matching ("bi" no longer fires in "bingo"), generic cultural words mark community_event not lgbtq_relevant, civic/kids/sports off-topic drops. Removed Majestic/Eagle venue bans (William reversed policy) so one-off bar specials like Lil Shop of Horrors are featurable/EOTW-eligible; recurring weeklies sort last in tiers. Added IG scrapers for @tulsaeagle, @clubmajestictulsa, @tulsaybr (sites DNS-dead). Voice: enrichment CLI timeout 120->300s (every W23/W24 batch had timed out -> 165 templated pool fillers); preflight now hard-blocks >40% templated website copy. This week's data/docs untouched per William; all changes take effect next run.

**Main artifact:** commit 9c8d586 - tools/sanity_check_events.py + scraper/runner.py + eotw_selector.py + content/generator.py + tools/preflight_post.py + gen_website_html.py + scraper/instagram_orgs.py + config.py + main.py
**Open items:** none - all 6 tasks verified (filter replay, time tests, EOTW eligibility, live IG fetch, sanity dry-run, enrichment batch, preflight block all confirmed). W25 Monday run already picked up the new code.

---

## [2026-06-09 14:18] Add Laura Bellis June 11 event + DM tip intake tool

Added the Re-Elect Laura Bellis Pride-season event (Thu Jun 11 2026, 6-7:30pm, ActBlue RSVP) to manual_events.json in site voice - confirmed it made this week's W24 deck and posted (FB id 1086906044497675_122116428344853065). Then built tools/add_tip.py: a paste-in DM tip intake (William chose paste-in + review-first over Meta auto-read). Parses IG/FB DM text into a pending queue, reviewer writes voice copy, approve promotes into manual_events.json. Never auto-publishes; requires name+date+description, blocks em dashes, dedups. Selftest + live end-to-end verified. Documented in tulsagays-domain-expertise skill.

**Main artifact:** tools/add_tip.py (commit 9c10630), data/manual_events.json
**Open items:** none - Bellis confirmed posted; auto-read of DMs (Meta App Review path) deferred unless William wants it later

---

## [2026-06-04] Tulsa Winds/YBR/QWC scrape + source-growth engine + 3 ceiling climbs

Wired Tulsa Winds (event-based, moving venue), YBR, and QWC into the scraper (commit 6a75614). Built a weekly self-improving source-growth engine that mines recurring venues + web-discovers new queer groups and auto-promotes strong sources into the live scraper via data/dynamic_sources.json (never edits .py), Sunday 8am task (commits 8bc44ac, 9ce86a2). Then climbed three ladders with /ceiling: the source-growth engine (lifecycle/census/coverage/feed, true ceiling), the revenue ladder (sales infra: prospect list, pipeline tracker, reader-revenue kit; Rungs 5-6 blocked on LLC/capital, commit f92c24e), and - after William asked for an unblocked ladder - the Answer Engine: 6 schema-rich /guides/ pages + 21 /org/ entity-profile pages + GEO llms.txt + weekly refresh_seo + live IndexNow ping (HTTP 202), all autonomous, zero blockers (commit 4a59af1). Also caught + scrubbed a live anonymity leak (William's name in public llms.txt).

**Main artifact:** tools/gen_topic_pages.py, tools/gen_org_profiles.py, tools/refresh_seo.py, tools/indexnow_ping.py, tools/promote_sources.py, tools/coverage_report.py, scraper/dynamic_sources.py, tulsa_queer_org_census.json, docs/guides/, docs/org/, drafts/sponsor-prospect-list.md
**Open items:** Revenue ladder blocked on William (LLC, payment rails, hello@ email, Ko-fi, Kit API key refresh) - queued in pending-william-actions.md

---

## [2026-06-03] TulsaGays sharing fix + newsletter pipeline + monetization ceiling climb

Fixed two live bugs on tulsagays.com: event cards now show exactly 1 source link (was 0-2), and Facebook sharing now shows the actual event name/description instead of generic homepage (per-event /e/<slug>.html pages with real OG tags). Wired the newsletter pipeline end-to-end for the first time: signup form feeds Kit directly, 3 stranded signups imported (4 active), Pride week newsletter staged as broadcast 24416150, anonymity gate added to prevent sending from name-revealing Gmail address. Climbed the monetization ceiling (10 autonomous rungs): Featured Partner directory infrastructure, rate card + pitch templates + media kit, subscriber milestone alerts, weekly stats digest, newsletter archive page, homepage subscribe CTA, sitemap updated. Everything committed and deployed (commits 06a0ab3 through 48ea9fd).

**Main artifact:** docs/e/ (57 per-event share pages), newsletter.html (Kit-wired), Kit broadcast 24416150, tools/inject_featured_partners.py, tools/check_subscriber_milestones.py, tools/weekly_stats_digest.py, tools/gen_newsletter_archive.py, docs/issues/, plans/tulsagays-dns-unblock.md
**Open items:** William to do 10-min DNS setup at Namecheap + Kit (plans/tulsagays-dns-unblock.md), then send broadcast 24416150. Gmail IMAP token expired needs re-auth.

---

## [2026-06-02] TulsaGays full automation + HELM helmforclaude.com launch

Rebuilt the TulsaGays Monday pipeline end to end: fixed the SUPERVISOR_TASK_COMPLETE caption leak on IG (delete boost, edit, re-boost $9/3d) and FB (Graph API), built a self-driving FB group blast system (posting/group_blast.py + tools/fb_groups.py + tools/group_caption.py), posted to 17 groups as the Tulsa Gays Page (6 live, 11 pending), and saved browser auth for hands-off Monday automation. Also rewrote the WOMPA scraper from broken Wix selectors to the GoodBarber JSON API. Separately: set up helmforclaude.com (DNS + GitHub Pages custom domain + fixed stale links), posted HELM to Reddit r/SideProject, and left 3 IH comments to unlock the new account for posting.

**Main artifact:** posting/group_blast.py, tools/fb_groups.py, tools/group_caption.py, scraper/playwright_scrapers.py (WOMPA fix), tools/preflight_post.py + tools/post_weekly.py (harness-marker durable fix). helmforclaude.com live.
**Open items:** IH post pending account unlock (check 2026-06-04+)

---

## [2026-05-14] Finish mid-week migration: HHHH posting, token cleanup, GHA scheduler fallback

Original goal was to run register-new-tulsagays-tasks (the one-shot in claude-ops) and unregister tulsagays-wednesday-social. That step is blocked from this session because the scheduled-tasks MCP is not connected and the GitHub MCP scope is restricted to DistrictOfRyan/tulsagays, so claude-ops PR #23 cannot be merged and the SKILL.md contents cannot be read. Side fixes that could land in this repo did: added Graph API HHHH page posting (posting/facebook.py + post-hhhh CLI), added Playwright HHHH group posting (posting/group_post.py), moved the leaked Tulsa Gays page access token out of meta_api_config.json into TULSAGAYS_PAGE_ACCESS_TOKEN env var (rotate to invalidate the value still in git history), and scaffolded a GitHub Actions cron fallback for the four scheduled tasks (.github/workflows/scheduled-tulsagays-tasks.yml + tools/run_scheduled_task.py stubs).

**Main artifact:** posting/facebook.py, posting/group_post.py, .github/workflows/scheduled-tulsagays-tasks.yml, tools/run_scheduled_task.py, .env.example, pending-william-actions.md, draft PR #6
**Open items:** Rotate Tulsa Gays page token at Meta. Disarm tulsagays-wednesday-social in the cloud scheduler manually before next Wednesday. Run register-new-tulsagays-tasks from a session that has the scheduled-tasks MCP and claude-ops GitHub scope. Or, port the four SKILL.md handlers in tools/run_scheduled_task.py and configure GHA secrets to use the fallback scheduler. First-time Playwright setup on the posting machine: pip install playwright; playwright install chromium; python -m posting.group_post --setup.

---

## [2026-05-13 23:45] Elevate tulsagays.com/blog - images, maps, live events, SEO, cross-links

Added images (hero + 3 inline, mixed float layouts) to all 8 blog articles and thumbnails to blog index. All CC Wikimedia Commons with keyword-stuffed alt text. Then elevated every article with 7 upgrades: read time + verified badge, table of contents (long articles), Google Maps embeds (no API key), venue social callout boxes, live events widget (JS fetches /events-current.json updated every Monday), newsletter CTA, submit event CTA, related posts section. Created `tools/add_blog_images.py` and `tools/elevate_blog.py`. Monday SKILL now refreshes events-current.json after each post.

**Main artifact:** `tools/add_blog_images.py`, `tools/elevate_blog.py`, `docs/events-current.json`, all 8 blog articles updated, blog/index.html with thumbnails
**Open items:** Meta page token expired - blocks Wednesday Social + new mid-week tasks until refreshed (session 88440193 working on it)

---

## [2026-05-13 23:00] Build TulsaGays weekly content engine - 4 new tasks + blog automation

Built a full mid-week content loop: Tuesday community prompt (branded image + reply scraper that auto-adds sources), Wednesday last-minute drop (conditional, skips if nothing new), Thursday spotlight (flamingo-scored venue selection, 300-500 word blog article deployed to tulsagays.com, social image post). Added `make_engagement_slide()` to image_maker.py. Added Monday snapshot save to main.py. Retired tulsagays-wednesday-social. All 4 tasks scheduled and live.

**Main artifact:** 4 new SKILL.md files in .claude/scheduled-tasks/, main.py snapshot patch, image_maker.py engagement slide function
**Open items:** Reddit app registration blocked (rate-limited at developers.reddit.com) - resume when clear. Thursday spotlight fires at noon tomorrow - pre-approve tools via "Run now" in sidebar.

---

## [2026-05-08 18:00] Fix scraper filter - add WOMPA, expand community event keywords

Diagnosed 5 events missed from a @experience.tulsa "Top 5 Things To Do" Reel (May 8-10) and fixed the root causes: WOMPA had never been scraped despite being Priority 1 in config, Philbrook was over-filtering, and the LGBTQ keyword list was too strict to catch community events like The Wiz, Oddities & Curiosities, and Boots Riley screenings.

**Main artifact:** 5 files changed - `scraper/playwright_scrapers.py` (new WOMPAScraper + Philbrook filter removed), `config.py` (WOMPA in LGBTQ_SOURCES + 15 venue names in COMMUNITY_PARTNER_KEYWORDS + Greenwood Cultural Center), `scraper/runner.py` + `extended_calendars.py` + `community_calendars.py` (expanded keyword lists)
**Open items:** None - Flagship identified as Tulsa Artist Fellowship's public space at 112 N Boston Ave; TulsaArtistFellowshipScraper added and wired

---
