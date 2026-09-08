# Monday Community Content Prompt

## What this does and why

Posts a branded 1080×1080 image every Monday morning asking followers to share
photos and reactions from the previous weekend's events.

**Why this matters:**

- Turns passive followers into active contributors (comments, tagged photos, UGC)
- Signals to Instagram and Facebook algorithms that the page builds real community,
  not just broadcasts — this boosts organic reach on the weekly carousel that
  went out right before it
- Creates a feedback loop: followers feel seen → more likely to attend future
  events → more likely to share the page with friends
- Monday morning is prime engagement time — people are catching up on the weekend

---

## How to run

```bash
python tools/post_community_prompt.py            # live post
python tools/post_community_prompt.py --dry-run  # generate image + caption, skip social
```

The `--dry-run` flag generates the PNG and prints the full caption but skips
git push, Facebook, and Instagram.

---

## Suggested schedule

**Monday 9am CT (14:00 UTC)** — post *after* the weekly carousel.

The carousel goes out first to remind people what events happened last week.
The community prompt follows right after, riding the same Monday morning content
wave and prompting people who just swiped through the carousel to engage.

GitHub Actions cron:

```yaml
- cron: '0 14 * * 1'   # Monday 9am CT = 14:00 UTC
```

Example job (add to `.github/workflows/`):

```yaml
- name: Monday community prompt
  run: python tools/post_community_prompt.py
  env:
    TULSAGAYS_PAGE_ACCESS_TOKEN: ${{ secrets.TULSAGAYS_PAGE_ACCESS_TOKEN }}
```

---

## Event data

The script automatically loads last week's events from:

```
data/events/{prev_week_key}_all.json
```

For example, if today is week 2026-W22, it looks for `data/events/2026-W21_all.json`.

If the file doesn't exist (or is unreadable), the shoutout line is silently
omitted and the post still goes out with a generic community prompt. **Events
are never required** — the post degrades gracefully.

To pass events in from another script instead of loading from disk:

```python
from tools.post_community_prompt import post_community_prompt, make_community_caption

events = [...]  # your list of last week's event dicts
post_community_prompt(events)
```

---

## Wiring into post_weekly.py

To auto-run the community prompt immediately after the weekly carousel, add
this block to the bottom of `main()` in `tools/post_weekly.py`:

```python
# Post Monday community prompt right after the carousel
try:
    from tools.post_community_prompt import post_community_prompt, _load_last_week_events
    last_week_events = _load_last_week_events()
    post_community_prompt(last_week_events, dry_run=DRY_RUN)
    print("[OK] Monday community prompt posted")
except Exception as _cp_err:
    print(f"[WARN] Community prompt skipped (carousel already live): {_cp_err}")
```

Running them as separate GitHub Actions steps is also fine — it lets you
dry-run the prompt independently and retry without re-running the full carousel.

---

## Caption template

```
[one of 5 rotating prompts — e.g. "Who made it out this weekend? Drop your pics below 📸"]

Shoutout to everyone who came out to [Event Name A] and [Event Name B]!

Tag a friend you spotted out this weekend 🤯

#TulsaGays #TulsaOK #TulsaLGBTQ #TulsaPride #WeekendRecap
```

The shoutout line only appears when last week's events file exists. The two
event names are taken from the top of the events list (first two entries with
a non-trivial name).
