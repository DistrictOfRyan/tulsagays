# Group Blaster — one-time setup (then Mondays are hands-off)

`posting/group_blast.py` posts the weekly carousel caption into the local
Facebook groups **as the Tulsa Gays Page** (never a personal account). It needs
a saved Facebook login once. After that, the Monday task runs it automatically.

## The one action only William can do (~2 minutes)

On the machine that runs the Monday task:

```
cd C:\Users\willi\tulsagays
python -m posting.group_blast --setup
```

A Chromium window opens. Log into Facebook as the account that **manages the
Tulsa Gays Page** (williamryanhunt@gmail.com). Once you're logged in, return to
the terminal and press Enter. Auth is saved to `data/fb_group_auth.json`
(gitignored). Re-run this only if the login expires (you'll see a "No auth" /
"could not confirm acting as Page" error in the weekly run).

## Weekly use (the Monday task does this for you)

```
python -m posting.group_blast --dry-run   # preview plan + caption, no FB
python -m posting.group_blast             # live blast
python -m posting.group_blast --list      # re-sync joined groups
```

## What it does / guarantees

- Switches to **acting as Tulsa Gays Page**; ABORTS rather than post as a
  personal account if it can't confirm (anonymity guard).
- Posts the clean caption (`tools/group_caption.py`) — no markers, no em dashes,
  guaranteed tulsagays.com link card.
- Targets the curated `tools/fb_groups.py` registry (16 post-targets; skips
  marketplace/singles/business/our-own and groups that block Pages).
- Verifies each post live-vs-pending; writes
  `data/posts/<week>/group_blast_results.json`.
- 5-day cooldown (never double-posts) + 25s pacing (spam-safe).

## Known
- Moderated groups (GAY OKLAHOMA, Interesting Things 73K, etc.) land in
  "pending admin approval" — normal, not a failure.
- Black Queer (Tulsa) and Oklahoma Lesbian Friends **block Page accounts** and
  are intentionally skipped (can't be posted anonymously).
- There may be a legacy "Tulsa Gays Auto Poster" integration still running; if
  you see double posts, disable it so this is the single source.
