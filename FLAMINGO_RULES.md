# Tulsa Gays — Flamingo Scoring Rules

The flamingo score (1–5) reflects how gay/LGBTQ+ an event is. It's displayed on the website
and used to sort slides. These rules are the source of truth — do not re-litigate them each week.

---

## Score Tiers

### 5 Flamingos — Super Gay
Awarded automatically to any event at a **true gay bar** OR matching a **super-gay keyword**.

**True gay bar venues (always 5, regardless of event type):**
- Club Majestic / Majestic Tulsa (`124 N Boston`)
- Tulsa Eagle (`1338 E 3rd` or `1330 E 3rd`)
- Yellow Brick Road
- The Vanguard
- Pump Bar (`602 S Lewis`)

**Keywords that trigger 5 (in event name or description):**
- Any drag: `drag show`, `drag bingo`, `drag brunch`, `drag queen`, `drag king`, `drag race`,
  `drag sing`, `drag along`, `drag perform`, `drag night`, `dragnificent`
- Pride events: `pride show`, `pride party`, `pride dance`, `pride night`
- Community identifiers: `queer night`, `gay night`, `lgbtq+ night`, `rainbow night`,
  `twisted arts`, `queer cabaret`, `homo hotel`, `hhhh`
- Support/identity: `queer support group`, `lgbtq support group`, `gender outreach support`,
  `queer women`, `sapphic social`, `queer social`, `trans support group`,
  `osu tulsa queer`, `pflag tulsa`, `queer support`, `pflag`, `lambda unity`, `lambda bowling`
- Crawls: `bar crawl`, `pub crawl`, `pride crawl`
- Recurring drag-hosted shows: `gabbin with gabbi`
- Production companies (always gay): `pride nation entertainment`, `brad lee` (Brad Lee Ent)
- Dedicated lesbian events: `lesbian attachment`

---

### 4 Flamingos — Very Queer
**Queer-friendly venues that aren't exclusively gay bars:**
- DVL Club & Lounge (`302 S Frankfort`)
- Elote (`any Elote location`)

**Keywords that trigger 4:**
- Identity terms: `lgbtq`, `lgbt`, `queer`, `lesbian`, `bisexual`, `sapphic`,
  `transgender`, `nonbinary`, `non-binary`, `gender outreach`
- Organizations: `equality center`, `okeq`, `pflag`, `hrc`, `gay bar`, `gay club`
- Event types: `queer collective`, `queer crafters`, `support group`, `trans support`,
  `queer women's`, `council oak`
- Arts: `musical`, `the musical`, `opera`, `broadway`
- Pride (generic): `pride`, `pride month`, `rainbow pride`

**Source-based 4s:**
- Events from `homo_hotel` or `okeq` sources are 4 minimum (unless already 5 by keyword/venue)

---

### 3 Flamingos — LGBTQ-Friendly
Awarded when the event comes from a trusted LGBTQ community source AND matches a community keyword,
OR the event name matches a specific 3-tier phrase.

**Community sources:** `homo_hotel`, `okeq`, `recurring`, `manual`

**Community keywords that lift to 3:**
`support`, `group`, `meeting`, `collective`, `social`, `community`, `bowling`, `yoga`,
`meditation`, `sound bath`, `seniors`, `testing`, `coffee`

**Specific phrases that are always 3 (regardless of source):**
- `first friday art crawl`, `art crawl` — welcoming community crawl, known LGBTQ turnout
- All performing arts keywords: `ballet`, `symphony`, `orchestra`, `choir`, `chorale`, `choral`, `performing arts`, `theatre`, `theater`, `cabaret`, `live performance`, `stage production`, `dance performance`, `recital`, `repertory`, `philharmonic`
- LGBTQ-affirming venues/orgs (not exclusively gay but always 3+): `all souls` (All Souls Unitarian)

---

### 2 Flamingos — Gay-Friendly (DEFAULT)
Anything that doesn't hit a higher tier. The baseline. Includes:
- Concerts, art shows, trivia nights, coffee shops, comedy shows, film screenings
- General Tulsa cultural events worth knowing about

**Keywords that lock an event to 2:**
`art`, `music`, `concert`, `gallery`, `theater`, `comedy`, `poetry`, `film`, `cinema`,
`festival`, `dance`, `live music`, `brunch`, `karaoke`, `trivia`, `open mic`, `rooftop`,
`bingo`, `scavenger`, `sketch`, `craft`, `workshop`, `coffee`

---

### 1 Flamingo — Mostly Straight
**Reserved for truly exclusionary or corporate-only events.** Effectively retired — almost
nothing should score 1. If you're tempted to assign 1, ask if it belongs on the site at all.

---

## Deduplication Rules

- Events with the same name (substring match) on the same day are collapsed to one record
- Source priority when deduping: `homo_hotel` > `okeq` > `recurring` > `manual` > everything else
- HHHH variants all collapse: "Homo Hotel Happy Hour", "4H: Homo Hotel Happy Hour", etc.
- Short names (under 7 chars) must be exact matches to trigger dedup

---

## Venue Name Map

When an event only has a street address, display the business name instead:

| Address fragment      | Display name            |
|-----------------------|-------------------------|
| 302 S Frankfort       | DVL Club & Lounge       |
| 1338 E 3rd / 1330 E 3rd | Tulsa Eagle          |
| 602 S Lewis           | Pump Bar                |
| 6808 S Memorial       | Loony Bin Comedy Club   |
| 1124 S Lewis          | WEL Bar                 |
| 1301 S Boston         | Boston Ave UMC          |
| 2224 W 51st           | Zarrow Library          |

---

## Garbage Event Filter

These are scraper artifacts and should never appear on the website or in slides:

- `(map)` — link artifact
- `stay connected!` — newsletter prompt scraped as event
- `our parTners` — sidebar content scraped as event
- `Event Application` — form link from OKEQ
- `Event Calendar` — nav link from OKEQ
- `Bruce Goff Event Center` — venue name scraped as event
- Any event name under 4 characters

**Daily health/clinical services** (scraped from OKEQ but not community events — filtered at runner level):
- `OKEQ Health Clinic` — daily medical clinic, repeats every weekday
- `HOPE Testing` (Health Outreach, Prevention & Education) — daily STI testing
- `Free Drop-In Therapy Sessions` — daily therapy availability notice
- Any variant of the above

---

## Slide Sorting Priority

Events within a day are ranked for slides in this order:

| Tier | Category |
|------|----------|
| T1 | LGBTQ, non-bar, non-recurring (always leads) |
| T2 | Drag/performance at a bar |
| T3 | LGBTQ bar event, one-off |
| T4 | Non-LGBTQ cultural (concerts, film, art) |
| T5 | LGBTQ recurring (bowling leagues, support groups — never lead) |
| T6 | Regular bar programming |
| T7 | Generic catch-all |

Within each tier, events sort by start time (AM before PM, untimed events last).

**Always deprioritized (T6 minimum):** mix-and-mingle networking, AA meetings,
generic book clubs, "shut up & write", self-help seminars, health clinics,
drop-in therapy sessions, STI testing services.

**NEVER featured as Event of the Day or in top 3 events:** anything matching the
daily health services list above, AA meetings, bowling leagues, recurring support groups.

---

## Schedule Constraints

- **No Tulsa Gays tasks on Fridays or Thursday nights**
- Full scrape must complete and be verified before generating slides or posting
- Week always runs Monday–Sunday; cover card shows current week (not next week)
