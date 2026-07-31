## [2026-07-31 10:30] Rebuild the weekend post as a novelty-ranked carousel + fix live site copy

William: "The Tulsa gays weekend post is really kind of lame... only a few events, and they are weekly events." He was right, and the diagnosis went deeper than presentation. (1) CAROUSEL: built tools/weekend_carousel.py + tools/post_weekend.py to replace the single reused background image. Friday night is now IN the window (the post fires Friday 8am and had been skipping Friday entirely, throwing away the biggest night of the week); novelty ranking against 6 weeks of history demotes anything that ran 3+ recent weekends into one "Running like always" line, with themed editions rescued as news; queer events sort first per day by name/venue/source; one slot per multi-night booking. 12 events vs 4. Published to FB + IG, deleted the 8am post on both (William approved). (2) THE REAL FINDING - venue dig proved the problem was SUPPLY, not ranking: the two best queer events of the weekend (STARPOWER, a five-queen drag show at Majestic, and Ho You Think You Can Dance, a hosted $100 dance comp) were completely absent from our scraped data because they exist only as IG image flyers. Added 4 finds; also learned Tulsa Eagle is low-yield (daily drink specials, not events) so the dig budget belongs on Majestic + YBR. (3) "remove the error": "in 5 days" was rendering as the VENUE on 85 live event cards and inside the schema.org location.name, so Google was indexing it as a Tulsa venue. Fixed at source (generator no longer interpolates a junk venue) plus a data-level scrub. (4) "fix the issues": audited all 182 events, found 6 issue classes across 116. The catch-all description opener was ONE hardcoded sentence on the repo's own banned-phrase list, shipping on 92 of 182 (51%, past the 40% carousel hard-block threshold) - the website had been shipping copy the slide preflight would refuse. Also caught two things no automated check would: a health clinic being told to "put on real clothes and get off your couch, darling", and "at Tulsa, OK" rendering a city as a venue. Consolidated time/venue/copy scrubbing into content/textclean.py (one implementation, selftested) so the website, slides and carousel stop drifting - with a deliberate asymmetry: the website scrubs and keeps the sentence, the carousel drops the line, because a slide cannot carry a half-removed sentence.

**Main artifact:** tulsagays commits 7747ee9 (carousel) + ff5072e (venue leakage) + 1045339 (copy sweep), all pushed and live-verified; tools/weekend_carousel.py, tools/post_weekend.py, content/textclean.py; scheduled-tasks/tulsagays-saturday-preview/SKILL.md rewritten for the carousel path
**Open items:** None blocking. Next Friday 8am (2026-08-07) is the first unattended carousel run - worth eyeballing the result. The 3 remaining raw-data artifact classes (mangled time, URL in description, unwrappable token) are intentionally left in the scrape record and cleaned at render; if they ever need to be clean at rest, fix the scrapers. Self-inflicted note: two --ig-only reruns re-rendered without the voice pass and put weaker copy on IG than FB had, and one render leaked a raw ?fbclid= URL off the slide edge - all three now impossible (--ig-only reuses the rendered deck + saved caption; sanitizer is selftested), but it cost 3 throwaway IG posts that had to be deleted by hand.

---

## [2026-07-11 14:30] Voice enforcement platform-wide + autonomous venue flyer dig (project-saver)

Marathon session. (1) VOICE: found the carousel was dry because the LLM was force-disabled on weekly runs and the _VOICE_BANK had 1-2 variants/category. Built an automatic featured/EOTW LLM voice pass (tools/voice_pass.py), expanded the bank 4-6x, added a refusal guard + dupe heal, and made preflight HARD-BLOCK generic slide copy. Then a 4-agent audit found the em-dash scrubber only guarded the IG caption - fixed it at every generator (newsletter, DM auto-reply [live em dash removed], Wed/Thu runners, website descriptions, website RENDERER via esc()+data-level strip, group poster). Fixed 3 pre-existing bugs (blog no-op, raw-HTML-abstract shipping, Joan-Crawford voice divergence). (2) SYNC: propagated everything to lexingtongays (full 37-file catch-up) + fixed 3 bugs in sync_from_tulsa.py (stale OneDrive paths, missing voice files in SHARED_FILES, false-target guard). (3) MONETIZATION (Rung 1 of /ceiling on Path A): real GA4 media kit, 20 verified sponsor prospects, outreach templates, runbook; sent 2 real anonymous outreach emails (il seme + Diversity Family Health) from events@tulsagays.com; added tulsagays to send_gmail.py CLI choices. (4) THE BIG ONE - AUTONOMOUS VENUE DIG: William was right that we never grabbed venues' flyer events. I wrongly said it "can't be automated"; then TESTED it and it works - instagram_web.py now grabs post IMAGE URLs (headless authed profile), tools/venue_flyer_dig.py reads events off the flyer images via claude vision, captured 7 real YBR one-offs zero-hands, promotes future ones to manual_events.json, wired to run Sunday 5pm unattended (task tulsagays-venue-dig). This is what makes the platform scale to OKC/Lexington/nationwide.

**Main artifact:** tulsagays commits pushed 131a80c..1c8580b (voice + sync + Rung 1 + venue dig); tools/venue_flyer_dig.py + scraper/instagram_web.py (image extraction); plans/nextlevel-citygays.md + plans/ceiling-runs/citygays.json
**Open items:** WILLIAM-ONLY: create Ko-fi/Stripe payment link + send 3 bar IG DMs (drafts/tulsagays/bar_outreach_dms.txt) - both in pending-william-actions.md. Watch first scheduled venue-dig run (Sun 7/13) + first Friday weekend-preview (7/17, watcher armed). Build a session-death health check for the fb_auto_profile IG login (not yet done). OKC as city #2 gated on venue-dig proving out on schedule.

---

## [2026-07-10 17:30] AEO/SEO audit + fixes + Profound baseline + live citations

Ran the full aeo-operating-system Mode A assessment on tulsagays.com (both halves). Scored 71/100 (top-decile AEO build - robots AI-bot allowlist, llms.txt, rich schema all already present) held down by stale/junk machine feeds. Root cause found + fixed: elevate_blog.write_events_current_json took the first 8 events with NO relevance filter, so FAFSA workshops, kids art classes, and "Obtener entradas" geo-junk leaked into events-current.json + /api/feed.json + /api/events.json - the exact files llms.txt points AI crawlers at. Added lgbtq_relevant/never_feature/junk-venue filtering (reusing runner helpers), regenerated all three feeds clean (8 real LGBTQ events, 0 junk, live-verified), wired the feed refresh + a new tools/refresh_sitemap_freshness.py (weekly lastmod stamp + dead-URL self-heal + --check guard) into the weekly prep pipeline. Removed 2 dead 404 sitemap URLs, fixed the frozen 2026-04-28 homepage lastmod, added a citable top-of-page direct-answer summary. Commit 131a80c pushed + live-verified. Then set up Profound: created the "Tulsa Gays" pitch workspace (agency plan) via browser, 24 prompts running across ChatGPT/Perplexity/Google AI Overviews (added 3 informational prompts to fix Profound's transactional auto-skew). Seeded 4 community citations LIVE (A11 fix) from William's personal accounts: 3 Quora answers (Ryan Hunt) + 1 Reddit comment on the r/tulsa Moving/Visiting megathread (u/Rumian4), all with tulsagays.com citations, logged in data/citation_log.json. Beat a nasty Claude-in-Chrome renderer freeze (long type times out but text lands; reopen auto-saved draft in a fresh tab; Post button disabled until dirtied with space+backspace; JS-click by button text).

**Main artifact:** skills/aeo-operating-system/tulsagays-aeo-run.md (filled scorecard) + tulsagays commit 131a80c + Profound workspace cf151e28 + data/citation_log.json (4 live posts)
**Open items:** Profound baseline populates in hours - William to send the Answer Engine Insights screenshot so the estimated 2-3/10 category-citation baseline becomes a measured number. Next AEO re-scan measures citation movement vs the ledger.

---

## [2026-07-10 15:00] IG/Messenger DM auto-reply + intake canary health check

Closed the Instagram DM gap in the event-intake pipeline. IG DMs can't be read via API (App Review pending) and the instagrapi session is dead, so instead of parsing DMs, set a native Meta Business Suite "Auto reply" on the Tulsa Gays page (automation_id 1243553908832887, ON, Messenger + Instagram) that redirects every first DM to events@tulsagays.com with the "send it before the Sunday your event's week starts" instruction. Fought a finicky Meta SPA: the enable switch ignores CDP synthetic clicks (enables only when Save creates the automation) and channel checkboxes need real coordinate clicks (JS .click() flips the DOM but not React state, silently dropping a channel) - verified the saved state via a fresh backend reload, not list-view icons. Then built + armed a canary health checker (tools/check_intake_health.py + handler tasks/tulsagays_intake_health.py, task tulsagays-intake-health, Sun+Wed 9am, 0 9 * * 0,3) that sends a tagged email via Brevo -> events@ Namecheap forward -> William's Gmail IMAP and confirms round-trip, plus verifies IMAP auth + config + intake-task freshness; FAILs + files a high gap on any breakage so a silently-broken forward can't look like a quiet week. Verified end-to-end: live canary confirmed in-run, handler returns success via the runner import path, schtask armed/Ready, registry clean (350 tasks). Also cleaned the tip queue (rejected a Brevo system email + undated chatter; 1 real pending = PFLAG Jul 23).

**Main artifact:** tulsagays/tools/check_intake_health.py (new) + task-runner/tasks/tulsagays_intake_health.py (new) + registry entry tulsagays-intake-health + Meta auto-reply (automation_id 1243553908832887)
**Open items:** None blocking. Monthly manual spot-check that the Meta auto-reply stays ON (no API to verify it). Optional: Gmail filter to auto-archive events@ mail after ingestion (offered, William did not request).

---

## [2026-07-09] Carousel dedup/cancelled fixes + final deck review + CLI auth failover

William caught W28's Saturday slide featuring the Elote drag brunch TWICE (two titles from two sources; name-only dedup missed it) plus "(Cancelled) Clothing Swap!" as the third highlight. Day 1 (commit 6a04531): runner._same_event_by_venue (same date + venue + >=2 distinctive shared name words, venue-word and generic-word leaks excluded) wired into deduplicate/_dedup_day/top-3 fill; _is_cancelled detector; preflight + selection recompute never_feature LIVE (stale scrape-time flags were the shipped hole); dedup merge keeps the live-scraped special instance over source=recurring (recurring winning silently demoted the EOTW) with venue/desc/time/URL backfill; W28 _all.json deduped 276->274; website regenerated, pushed, live-verified (one Elote card, EOTW banner intact); 11 regression locks. Day 2 (commit 9911dc8): NEW tools/final_deck_review.py per William - last-eyes pass auto-run at end of generate-all: deterministic layer (cancelled/never-feature in featured+EOTW, dup pairs in featured AND all_shown, recurring-over-one-off warnings w/ drag-perf exemption) + LLM editor per day (haiku, judges picks vs alternates, swap suggestions); persists final_review.json; preflight runs its rule layer inline as the single implementation + carries [final-llm] findings. Proof: preflight on the shipped W28 manifest BLOCKS with 6 errors; LLM caught Thursday's corrupted "Obtener entradas" pick. Also found+fixed the ROOT CAUSE of weeks of templated filler: claude -p default auth 401s since early July, silently degrading ALL CLI LLM layers - _call_claude_cli now strips nested-session env vars and fails over across claude_tokens.env (gaps G45, G46 logged).

**Main artifact:** tools/final_deck_review.py (new) + scraper/runner.py + main.py + tools/preflight_post.py + content/generator.py - commits 6a04531 + 9911dc8, pushed
**Open items:** William decision queued in action inbox: leave the posted W28 carousel up (recommended) vs delete+repost corrected. Watch Monday W29 generate-all for enriched (non-templated) descriptions now that the LLM path is back.

---

## [2026-07-07] Circle Cinema scraper rebuild + word-boundary filters + source rot

Three related scraper fixes on the TulsaGays repo. (1) CircleCinemaScraper was yielding 0 - circlecinema.org is a Wix shell whose /movies route 404s. Sniffed the network and found the real schedule on the Easy-Ware Blazor ticketing portal (circlecinema.easy-ware-ticketing.com, SignalR WebSocket, no JSON XHR - the rendered DOM IS the API). Rebuilt to read the #eventGrid cards, follow "More..." to /eventsByMovie/<id> for full showtimes + synopsis, and read the Blazored.Modal for the rest. One event per film per date; 40 films -> 4-5 in-week dated events (commit 8a3830d). (2) Fixed the substring-matching false positives across all 6 per-scraper LGBTQ pre-filters (bi in bingo/billion, drag in dragon, market in supermarket) via a new shared scraper/relevance.py word-boundary matcher; keyword lists stay per-module, only the matcher is shared. Kept "Girls Like Girls" (whose Fandango synopsis has zero identity keywords) via SYNOPSIS_LGBTQ_PHRASES (commit 953e5c0). (3) Extended word boundaries to runner._is_community_keeper, and cleaned community_calendars source rot - retired Public Radio Tulsa (calendar removed, all paths 404) and dropped AllEvents.in's dead /api endpoint to go straight to the HTML JSON-LD that works (commit a0bb5fa). All verified: relevance selftest 24/0, cross-module filter suite 107/0, keeper coverage 122 keywords + 10 cases 0 failures, community_calendars now logs zero ERRORs (was 2).

**Main artifact:** scraper/relevance.py (new) + scraper/playwright_scrapers.py + scraper/{community_calendars,extended_calendars,eventbrite_meetup,facebook_events,specific_orgs,runner}.py - commits 8a3830d, 953e5c0, a0bb5fa (committed, not pushed)
**Open items:** None. Not run through the full posting pipeline (scraping verification only, per request).

---

## [2026-06-30] Recurring-event venue + existence verification

William flagged this week's post putting "Queer Women's Collective" (voice-to-text "Queer as a Lamentations Collective") at the wrong venue - it rotates monthly and was frozen at the Equality Center instead of The Hunt Club. Built the durable, generalized fix (commit d6b344b): (1) data/venue_overrides.json + scraper/venue_overrides.py - month-scoped venue corrections that win over any stale scraped/hardcoded/ledger venue (runner step 5d); QWC venue blanked + venue_varies in recurring.py; preflight hard-blocks featuring a venue_varies event with no override for the month. (2) Generalized to ALL recurring events per William: scraper/recurring_verify.py + data/recurring_confirmations.json (runner step 1a) drops dead/paused events, auto-confirms ones a live scrape corroborates (name + AGREEING venue only - loose name matches were mis-adopting wrong venues like Trivia->Good Cause, Lambda Bowling->Equality Center, so those become human-confirm conflicts instead), tiered preflight (warn >60d stale, block featuring >180d). tools/verify_recurring.py = on-demand report. Decisions: tiered enforcement, 60-day freshness, auto-confirm+adopt (made venue-safe). Did NOT touch this week's live post (William: going forward only). All selftests green; verified on real W27 data.

**Main artifact:** scraper/recurring_verify.py + scraper/venue_overrides.py + data/{venue_overrides,recurring_confirmations}.json (commit d6b344b, pushed)
**Open items:** Optional mid-week scheduled task to push stale/conflict confirmations to the action inbox before Monday - offered, William chose save-for-now. Ledger auto-populates on next Monday scrape.

---

## [2026-06-24] W26 recovery + bingo->Elote correction + YBR fix

Three threads. (1) Recovered the crashed W26 Monday post (IG + FB page + website live; hardened the caption CLI-error guard). (2) William flagged the Event of the Week "Drag Bingo Bongo at Saturn Room" as fabricated/not-happening - it came from a recurring rule that invented the "drag" framing and auto-dated it with no check, and "drag" tier beat the real Pride events for EOTW. Full redo: EOTW -> Elote's first-ever Pride Fest (verified on elotetulsa.com), bingo removed from IG + FB page + website + data + 16-group re-blast, Gala venue corrected to Arvest Convention Center. Durable fix: recurring auto-events barred from EOTW (eotw_selector), fabricated Saturn Room rule removed, FB group-blast re-auth path fixed (point at real-Chrome fb_profile_login.py not the Google-blocked capture_group_auth.py; fixed _switch_to_page false-negative). Corrected Elote post now in 15/17 groups (2 holdouts block page posting at group-settings level). Old bingo deleted from IG + FB page + website; the ~10 bingo DUPLICATES buried in group feeds could NOT be auto-deleted (graphics-only, no permalinks, FB hides a page's buried group posts from automation) - left as a harmless William-only cleanup. (3) YBR (lesbian bar) events weren't surfacing because the IG-only scraper depends on a session that keeps dying (429 + no fallback + no keepalive). Workaround: read @tulsaybr's schedule live via the logged-in personal Chrome (cleared a "This Was Me" IG challenge from the PV login), then transcribed YBR's verified recurring lineup into recurring.py (+ added "last weekday" frequency support) so YBR shows EVERY week with zero IG-session dependency; injected this week's 3 events + rebuilt site. Added @imvalpal as a fallback IG handle.

**Main artifact:** commits be2c6d3, 6153e23, e24b6f8, 0c2a69d, 9929139, 28dc9e7, 7eb11f1 - eotw_selector.py, scraper/recurring.py, posting/group_blast.py, tools/group_auth_keepalive.py, scraper/instagram_orgs.py, data/manual_eotw.json, docs/
**Open items:** ~10 old bingo duplicate group posts (William-only, harmless); IG-only sources (Eagle/Majestic/DVL) still dark without an IG session/keepalive; 2 groups block page posting.

---

## [2026-06-18 13:10] TulsaGays feed audit - fix 3 silently-broken scrapers + systemic Brotli bug

Audited every scraper module by actually running it (URL-reachability checks miss silent failures). Fixed TimeTree (dead .ics -> JSON API + CSRF + RRULE recurrence expansion, 0->19), qlist (guessed CSS selectors matched nothing -> real .cluster-event parser, 0->11 LGBTQ events), and a SYSTEMIC bug in base.py: the session advertised Accept-Encoding br with no Brotli decoder installed, so any Brotli-serving site returned undecodable bytes -> 0 events, no error (qlist got 29KB junk vs 191KB real). Dropped br; it revived qlist and Tulsa Arts District's HTML path. Rewrote TAD to the Events Calendar REST API (1683 events on cold call) but burned the IP into a WAF block via testing - live verify deferred to Monday scrape, logged in pending-actions.

**Main artifact:** scraper/base.py, scraper/timetree_scraper.py, scraper/qlist.py, scraper/tulsa_arts_district.py
**Open items:** Confirm TAD on next clean Monday scrape (WAF block was self-inflicted). Optional: TICKETMASTER_API_KEY to enable ticketing feed.

---

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
