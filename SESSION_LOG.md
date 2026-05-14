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
