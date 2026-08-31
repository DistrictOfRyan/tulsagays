# Mid-Week Event Spotlight

**File:** `tools/post_midweek_spotlight.py`

## What it does

Posts individual event spotlights on **Tuesday** and **Thursday** to keep the
Tulsa Gays Instagram and Facebook pages active mid-week (current cadence is one
weekly carousel on Monday; this adds 2–4 more posts per week).

Each run selects the **top 2 eligible events** from the current week's event
data and posts a branded 1080×1080 spotlight image with a caption to both
Facebook and Instagram.

- **Tuesday 10am CT** — spotlights events happening **Thursday–Saturday** of
  the same week (gives followers 2–4 days lead time to plan).
- **Thursday 10am CT** — spotlights events happening **Friday–Sunday** of the
  same week (weekend preview with 1–3 days lead time).

### Image layout

```
┌──────────────────────────────────────────────┐
│  Top 40% (432 px)                            │
│  • Event photo if event.image_url/image_path │
│    is available (aspect-fill crop)           │
│  • OR: solid day-accent color block with     │
│    "TULSA GAYS" branding (dark text on       │
│    lavender/rose depending on day)           │
├──────────────────────────────────────────────┤  ← 4 px neon-pink bar
│  Bottom 60% (648 px)  dark bg #0a0a0a        │
│  Event name   (large Poiret One, white)      │
│  @ Venue      (medium segoe-semi, #FF1493)   │
│  Date · Time  (medium segoe-semi, gray)      │
│                          tulsagays.com       │
└──────────────────────────────────────────────┘
```

### Caption format

```
✨ This [Weekday]: [Event Name]

📍 [Venue]
🕐 [Time]
[First sentence of description, if any]

[Random engagement CTA]
Save this for your weekend plans 🔖

#TulsaGays #TulsaOK #TulsaLGBTQ #TulsaEvents
```

### Event selection scoring

Events are ranked by a four-key sort (all ascending, so lower = higher
priority):

| Key | 0 (preferred) | 1 (lower) |
|-----|---------------|-----------|
| `preferred_window` | Event falls in preferred date window | Outside window |
| `has_specific_time` | Event has a time string | No time |
| `is_lgbtq` | Passes `_is_lgbtq()` from `eotw_selector.py` | Does not |
| `name` | Alphabetical tiebreak | — |

Events are filtered out if they have no parseable date, are in the past, or
fail `_is_skip()` from `eotw_selector.py`.

## How to run

```bash
# Auto-detect day from today's weekday (Tuesday → tuesday, Thursday → thursday)
python tools/post_midweek_spotlight.py

# Force a specific day (useful for testing outside Tue/Thu)
python tools/post_midweek_spotlight.py --day tuesday
python tools/post_midweek_spotlight.py --day thursday

# Dry-run: generate images and print captions; no social posts, no git push
python tools/post_midweek_spotlight.py --dry-run
python tools/post_midweek_spotlight.py --day tuesday --dry-run
```

## Suggested cron schedule

GitHub Actions `schedule` (UTC):

```yaml
on:
  schedule:
    # Tuesday 10am CT = 15:00 UTC (standard time) / 16:00 UTC (daylight time)
    - cron: '0 15 * * 2'   # UTC; adjust to '0 16 * * 2' during CDT (Mar–Nov)
    # Thursday 10am CT = 15:00 UTC (standard time) / 16:00 UTC (daylight time)
    - cron: '0 15 * * 4'   # UTC; adjust to '0 16 * * 4' during CDT (Mar–Nov)
```

For year-round correctness during CDT (second Sunday of March through first
Sunday of November), use `16:00 UTC`; during CST use `15:00 UTC`. A single
`0 15 * * 2,4` cron covers CST; change to `0 16 * * 2,4` for CDT.

**Simple always-safe option** — run at 15:00 UTC year-round (posts at 9am CT
in summer, 10am CT in winter — both fine for mid-morning engagement):

```yaml
- cron: '0 15 * * 2'   # Tuesday
- cron: '0 15 * * 4'   # Thursday
```

## Dependencies

| Package | Used for |
|---------|----------|
| `Pillow` (PIL) | Image generation in `make_spotlight_image` |
| `requests` | Fetching remote event images (optional) |

Both are already present in the project's environment.

Internal imports (all within this repo):

- `content.image_maker` — brand colors, fonts, drawing helpers
- `tools.social_lib` — `post_facebook_photo`, `post_instagram_photo`,
  `load_meta_config`, `wait_for_public_url`, `log_engagement_event`
- `eotw_selector` — `_is_lgbtq`, `_is_skip` for event scoring/filtering
- `config` — `current_week_key()`, `EVENTS_DIR`

## Output files

Per run, for each event posted:

- `docs/posts/{week_key}/spotlight-{slug}-{YYYYMMDD}.png` — spotlight image
  (committed and pushed to GitHub Pages for the public URL the Graph API needs)
- `docs/posts/{week_key}/engagement_log.json` — append-only run log with
  FB/IG post IDs, committed after each post
