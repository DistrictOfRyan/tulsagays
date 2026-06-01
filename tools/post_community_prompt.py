"""Monday 9am CT: branded image asking followers to share weekend photos and reactions.

Turns followers into contributors. Posted Monday morning, it creates a feedback loop
and signals to the algorithm that the page builds real community (comments, tags, UGC).

Usage:
  python tools/post_community_prompt.py            # live post
  python tools/post_community_prompt.py --dry-run  # generate image + caption, skip social posts
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta
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

COMMUNITY_PROMPTS = [
    "Who made it out this weekend? Drop your pics and stories below 📸👇",
    "Did you catch any of this weekend's events? We want to see! Drop your photos 📸",
    "Weekend recap time 🎉 Who went out? What was the vibe? Tell us in the comments!",
    "We love seeing YOUR faces at these events 📸 Tag yourself or a friend from this weekend!",
    "Monday check-in ✅ Who had the best weekend? Drop a photo or just tell us what you did 👇",
]


def make_community_image(output_path: str) -> str:
    """1080x1080 branded image using brand colors and fonts from image_maker.py.

    Uses make_engagement_slide (community type — lavender accent) so the image
    matches the established brand without duplicating Pillow layout code. Warm
    and human — not a formal event promo.

    Returns output_path.
    """
    img = make_engagement_slide(
        headline="How was your weekend?",
        body="Drop your pics and stories in the comments below!",
        post_type="community",
        subhead="We want to see YOUR faces at these events",
    )
    img.save(output_path, "PNG", optimize=True)
    return output_path


def _last_week_key() -> str:
    """Return the ISO week key for last week, e.g. '2026-W21'."""
    now = datetime.now()
    last_monday = now - timedelta(days=now.weekday() + 7)
    return f"{last_monday.year}-W{last_monday.isocalendar()[1]:02d}"


def _load_last_week_events() -> list[dict]:
    """Load last week's events from data/events/{week_key}_all.json.

    Returns empty list if the file doesn't exist — post degrades gracefully
    without the event shoutout line.
    """
    week_key = _last_week_key()
    events_file = ROOT / "data" / "events" / f"{week_key}_all.json"
    if not events_file.exists():
        return []
    try:
        with open(events_file, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else data.get("events", [])
    except Exception:
        return []


def make_community_caption(last_week_events: list) -> str:
    """Build the post caption.

    Format:
      [random COMMUNITY_PROMPTS entry]

      Shoutout to everyone who came out to [top 1-2 event names from last week]!

      Tag a friend you spotted out this weekend 👯

      #TulsaGays #TulsaOK #TulsaLGBTQ #TulsaPride #WeekendRecap
    """
    prompt = random.choice(COMMUNITY_PROMPTS)
    lines = [prompt, ""]

    top_events = [
        e for e in last_week_events
        if e.get("name") and len(e["name"].strip()) > 3
    ][:2]

    if top_events:
        names = " and ".join(e["name"].strip() for e in top_events)
        lines.append(f"Shoutout to everyone who came out to {names}!")
        lines.append("")

    lines.append("Tag a friend you spotted out this weekend \U0001f93f")
    lines.append("")
    lines.append("#TulsaGays #TulsaOK #TulsaLGBTQ #TulsaPride #WeekendRecap")

    return "\n".join(lines)


def post_community_prompt(last_week_events: list, dry_run: bool = False) -> bool:
    """Generate image + caption and post to Instagram and Facebook.

    Returns True on success. Raises on unrecoverable errors.
    """
    week_key = config.current_week_key()

    out_rel = Path("docs") / "posts" / week_key
    out_abs = ROOT / out_rel
    out_abs.mkdir(parents=True, exist_ok=True)
    img_name = "monday-community-prompt.png"
    img_path = out_abs / img_name

    make_community_image(str(img_path))
    size = img_path.stat().st_size
    print(f"image={img_path}  bytes={size}")
    if size < 30_000:
        raise RuntimeError(f"Generated image is too small ({size}B); aborting.")

    caption = make_community_caption(last_week_events)
    print(f"\ncaption ({len(caption)} chars):\n{caption}\n")

    public_url = public_url_for(str(out_rel / img_name))
    print(f"public_url={public_url}")

    fb_result: dict = {"id": "skipped", "dry_run": dry_run}
    ig_result: dict = {"id": "skipped", "dry_run": dry_run}

    if dry_run:
        print("DRY RUN: skipping git push and social posts")
    else:
        import subprocess

        subprocess.run(["git", "add", str(out_rel / img_name)], cwd=ROOT, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"tulsagays-monday-community-prompt: {week_key} image"],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(["git", "push", "origin", "HEAD"], cwd=ROOT, check=True)

        wait_for_public_url(public_url)

        cfg = load_meta_config()
        fb_result = post_facebook_photo(cfg, public_url, caption, dry_run=False)
        print(f"facebook_post_id={fb_result.get('id')}")

        try:
            ig_result = post_instagram_photo(cfg, public_url, caption, dry_run=False)
            print(f"instagram_post_id={ig_result.get('id')}")
        except RuntimeError as e:
            print(f"WARN: Instagram post failed (keeping FB): {e}")
            ig_result = {"id": "failed", "error": str(e)}

    log_path = log_engagement_event(
        week_key,
        {
            "task": "tulsagays-monday-community-prompt",
            "fired_at": datetime.now().isoformat(timespec="seconds"),
            "week": week_key,
            "last_week": _last_week_key(),
            "last_week_events_count": len(last_week_events),
            "image_url": public_url,
            "fb_post_id": fb_result.get("id"),
            "ig_post_id": ig_result.get("id"),
            "dry_run": dry_run,
        },
        ROOT,
    )

    if not dry_run:
        import subprocess

        subprocess.run(["git", "add", str(log_path.relative_to(ROOT))], cwd=ROOT, check=True)
        subprocess.run(
            [
                "git", "commit", "-m",
                f"tulsagays-monday-community-prompt: {week_key} engagement log",
            ],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(["git", "push", "origin", "HEAD"], cwd=ROOT, check=True)

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Post Monday community content prompt to Instagram and Facebook."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Generate image and caption without posting to social or pushing to git",
    )
    args = parser.parse_args()

    events = _load_last_week_events()
    last_week = _last_week_key()
    if events:
        print(f"Loaded {len(events)} events from {last_week}")
    else:
        print(f"No events found for {last_week} — posting without event shoutout")

    try:
        success = post_community_prompt(events, dry_run=args.dry_run)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
