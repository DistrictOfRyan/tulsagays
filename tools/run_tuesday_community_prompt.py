"""Tuesday 12pm CT: branded image asking the community for missing venues, hidden
gems, new additions, or last-minute event intel.

Designed for GitHub Actions or any cron runner. Image-only on social. Never
calls Graph API /feed.

Usage:
  python tools/run_tuesday_community_prompt.py            # live post
  python tools/run_tuesday_community_prompt.py --dry-run  # generate image, skip social posts and git push
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from content.image_maker import make_engagement_slide  # noqa: E402
from tools.social_lib import (  # noqa: E402
    load_meta_config,
    log_engagement_event,
    post_facebook_photo,
    post_instagram_photo,
    public_url_for,
    wait_for_public_url,
)

PROMPTS = {
    0: {
        "headline": "Who are we missing?",
        "subhead": "Drop a venue, a host, or a recurring night below.",
        "body": (
            "We scrape every queer corner of Tulsa each week. "
            "If you know a spot we never list, comment it. We'll add it."
        ),
        "caption": (
            "Who do we keep missing? Drop the venue, host, or weekly night "
            "in the comments. We add real ones every Monday."
        ),
    },
    1: {
        "headline": "Hidden gems only",
        "subhead": "The spot you never want to leave.",
        "body": (
            "The little bar, the back-patio happy hour, the side-room karaoke. "
            "Comment the place locals know and tourists don't."
        ),
        "caption": (
            "Hidden gems only. What's the queer-friendly Tulsa spot you guard "
            "like a secret? Comment below, we'll feature it."
        ),
    },
    2: {
        "headline": "New in Tulsa?",
        "subhead": "Just opened, just moved, just queer-owned.",
        "body": (
            "If a new bar, cafe, salon, or shop opened in the last 90 days "
            "and the LGBTQ+ crowd should know, drop it."
        ),
        "caption": (
            "What just opened that we should know about? New venues, new "
            "businesses, new queer-owned spots. Comment them below."
        ),
    },
    3: {
        "headline": "Last-minute intel",
        "subhead": "Pop-ups, surprise drag, secret afters.",
        "body": (
            "Got intel on something happening this week that isn't on the "
            "website yet? Drop it and we'll cross-post by Wednesday."
        ),
        "caption": (
            "Last-minute intel? Pop-ups, surprise drag, secret afters. "
            "Comment what's happening this week and we'll cross-post Wed."
        ),
    },
}


def pick_prompt(week_key: str) -> tuple[int, dict[str, str]]:
    week_num = int(week_key.split("-W")[1])
    slot = week_num % len(PROMPTS)
    return slot, PROMPTS[slot]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    week_key = config.current_week_key()
    slot, chosen = pick_prompt(week_key)
    print(f"week={week_key}  slot={slot}  headline={chosen['headline']!r}")

    out_rel = Path("docs") / "posts" / week_key
    out_abs = ROOT / out_rel
    out_abs.mkdir(parents=True, exist_ok=True)
    img_name = "tuesday-community-prompt.png"
    img_path = out_abs / img_name

    img = make_engagement_slide(
        headline=chosen["headline"],
        body=chosen["body"],
        post_type="community",
        subhead=chosen["subhead"],
    )
    img.save(img_path, "PNG", optimize=True)
    size = img_path.stat().st_size
    print(f"image={img_path}  bytes={size}")
    if size < 30_000:
        raise RuntimeError(f"Generated image is too small ({size}B); aborting.")

    public_url = public_url_for(str(out_rel / img_name))
    print(f"public_url={public_url}")

    fb_result: dict = {"id": "skipped", "dry_run": args.dry_run}
    ig_result: dict = {"id": "skipped", "dry_run": args.dry_run}

    if args.dry_run:
        print("DRY RUN: skipping git push and social posts")
    else:
        import subprocess

        subprocess.run(["git", "add", str(out_rel / img_name)], cwd=ROOT, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"tulsagays-tuesday-community-prompt: {week_key}"],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(["git", "push", "origin", "HEAD"], cwd=ROOT, check=True)

        wait_for_public_url(public_url)

        cfg = load_meta_config()
        fb_result = post_facebook_photo(cfg, public_url, chosen["caption"], dry_run=False)
        print(f"facebook_post_id={fb_result.get('id')}")

        try:
            ig_result = post_instagram_photo(cfg, public_url, chosen["caption"], dry_run=False)
            print(f"instagram_post_id={ig_result.get('id')}")
        except RuntimeError as e:
            print(f"WARN: Instagram post failed (keeping FB): {e}")
            ig_result = {"id": "failed", "error": str(e)}

    log_engagement_event(
        week_key,
        {
            "task": "tulsagays-tuesday-community-prompt",
            "fired_at": datetime.now().isoformat(timespec="seconds"),
            "week": week_key,
            "slot": slot,
            "headline": chosen["headline"],
            "image_url": public_url,
            "fb_post_id": fb_result.get("id"),
            "ig_post_id": ig_result.get("id"),
            "dry_run": args.dry_run,
        },
        config.DATA_DIR if isinstance(config.DATA_DIR, Path) else Path(config.DATA_DIR),
    )
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
