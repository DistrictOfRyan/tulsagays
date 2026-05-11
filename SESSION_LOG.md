## [2026-05-08 18:00] Fix scraper filter - add WOMPA, expand community event keywords

Diagnosed 5 events missed from a @experience.tulsa "Top 5 Things To Do" Reel (May 8-10) and fixed the root causes: WOMPA had never been scraped despite being Priority 1 in config, Philbrook was over-filtering, and the LGBTQ keyword list was too strict to catch community events like The Wiz, Oddities & Curiosities, and Boots Riley screenings.

**Main artifact:** 5 files changed - `scraper/playwright_scrapers.py` (new WOMPAScraper + Philbrook filter removed), `config.py` (WOMPA in LGBTQ_SOURCES + 15 venue names in COMMUNITY_PARTNER_KEYWORDS + Greenwood Cultural Center), `scraper/runner.py` + `extended_calendars.py` + `community_calendars.py` (expanded keyword lists)
**Open items:** None - Flagship identified as Tulsa Artist Fellowship's public space at 112 N Boston Ave; TulsaArtistFellowshipScraper added and wired

---
