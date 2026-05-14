"""Wednesday 5pm CT: image-only mid-week post, but only when something new has
appeared between Monday's snapshot and now. Silent skip is the correct outcome
when nothing's new.

Image-only. Never calls Graph API /feed.

Usage:
  python tools/run_wednesday_lastminute.py
  python tools/run_wednesday_lastminute.py --dry-run
"""

from __future__ import annotations

import argparse
import json
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

GAY_BAR_VENUES = {
    "club majestic",
    "majestic tulsa",
    "tulsa eagle",
    "yellow brick road",
    "the vanguard",
    "pump bar",
}
SUPER_GAY_KW = (
    "drag ",
    "hhhh",
    "homo hotel",
    "queer ",
    "pride ",
    "twisted arts",
    "lesbian",
    "sapphic",
    "dragnificent",
)
SKIP_KW = (
    "bowling league",
    "aa meeting",
    "support group",
    "happy hour!",
    "touchtunes",
    "ttrpg",
)
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _event_key(e: dict) -> str:
    return (
        f"{e.get('date','')}"
        f"|{(e.get('name','') or '').strip().lower()}"
        f"|{(e.get('venue','') or '').strip().lower()}"
    )


def _score(e: dict) -> int:
    venue = (e.get("venue", "") or "").lower()
    name = (e.get("name", "") or "").lower()
    if any(b in venue for b in GAY_BAR_VENUES):
        return 5
    if any(k in name for k in SUPER_GAY_KW):
        return 5
    return 3


def _should_skip(e: dict) -> bool:
    name = (e.get("name", "") or "").lower()
    return any(k in name for k in SKIP_KW)


def _short_day(d: str) -> str:
    try:
        return DAYS[datetime.strptime(d, "%Y-%m-%d").weekday()]
    except Exception:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    week_key = config.current_week_key()
    events_dir = Path(config.EVENTS_DIR)
    snap_path = events_dir / f"{week_key}_monday_snapshot.json"
    live_path = events_dir / f"{week_key}_all.json"

    if not snap_path.exists() or not live_path.exists():
        print(
            f"Missing inputs (snap={snap_path.exists()} live={live_path.exists()}); "
            "silent skip."
        )
        return 0

    with snap_path.open(encoding="utf-8") as f:
        snap = json.load(f)
    with live_path.open(encoding="utf-8") as f:
        payload = json.load(f)
    live_events = payload.get("events", payload) if isinstance(payload, dict) else payload
    if not isinstance(live_events, list):
        live_events = []

    today = datetime.now().date()
    week_monday = today - timedelta(days=today.weekday())
    thu = week_monday + timedelta(days=3)
    sun = week_monday + timedelta(days=6)

    snap_keys = set(snap.get("event_keys", []))
    new_events = [
        e
        for e in live_events
        if isinstance(e, dict)
        and _event_key(e) not in snap_keys
        and not _should_skip(e)
        and _in_window(e, thu, sun)
    ]
    print(f"new_events={len(new_events)}")

    if not new_events:
        log_engagement_event(
            week_key,
            {
                "task": "tulsagays-wednesday-lastminute",
                "fired_at": datetime.now().isoformat(timespec="seconds"),
                "week": week_key,
                "new_count": 0,
                "skipped": True,
                "dry_run": args.dry_run,
            },
            Path(config.DATA_DIR),
        )
        print("silent skip (no new events)")
        return 0

    ranked = sorted(new_events, key=_score, reverse=True)
    featured = ranked[0]
    print(f"featured={featured.get('name')} ({featured.get('date')})")

    body_lines = []
    for e in ranked[:3]:
        when = f"{_short_day(e.get('date',''))} {e.get('time','') or ''}".strip()
        body_lines.append(f"{e.get('name','')}, {when} at {e.get('venue','') or ''}")
    body = "\n".join(body_lines)

    caption_lines = ["Just added since Monday. Mid-week intel only."]
    for e in ranked[:3]:
        caption_lines.append(
            f"• {e.get('name','')}, {_short_day(e.get('date',''))} "
            f"{e.get('time','') or ''} at {e.get('venue','') or ''}"
        )
    caption_lines += ["", "Full week at tulsagays.com.", "#TulsaGays #QueerTulsa #LGBTQTulsa"]
    caption = "\n".join(caption_lines).strip()

    out_rel = Path("docs") / "posts" / week_key
    out_abs = ROOT / out_rel
    out_abs.mkdir(parents=True, exist_ok=True)
    img_name = "wednesday-lastminute.png"
    img_path = out_abs / img_name

    img = make_engagement_slide(
        headline="Just added",
        body=body,
        post_type="lastminute",
        subhead="Mid-week intel for the rest of the week",
    )
    img.save(img_path, "PNG", optimize=True)
    if img_path.stat().st_size < 30_000:
        raise RuntimeError("Generated image too small; aborting.")

    public_url = public_url_for(str(out_rel / img_name))
    print(f"public_url={public_url}")

    fb_result = {"id": "skipped"}
    ig_result = {"id": "skipped"}
    if args.dry_run:
        print("DRY RUN: skipping git push and social posts")
    else:
        import subprocess

        subprocess.run(["git", "add", str(out_rel / img_name)], cwd=ROOT, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"tulsagays-wednesday-lastminute: {week_key}"],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(["git", "push", "origin", "HEAD"], cwd=ROOT, check=True)

        wait_for_public_url(public_url)

        cfg = load_meta_config()
        fb_result = post_facebook_photo(cfg, public_url, caption)
        print(f"facebook_post_id={fb_result.get('id')}")

        try:
            ig_result = post_instagram_photo(cfg, public_url, caption)
            print(f"instagram_post_id={ig_result.get('id')}")
        except RuntimeError as e:
            print(f"WARN: IG post failed (keeping FB): {e}")
            ig_result = {"id": "failed", "error": str(e)}

    log_engagement_event(
        week_key,
        {
            "task": "tulsagays-wednesday-lastminute",
            "fired_at": datetime.now().isoformat(timespec="seconds"),
            "week": week_key,
            "new_count": len(new_events),
            "skipped": False,
            "featured": {
                "name": featured.get("name"),
                "date": featured.get("date"),
                "venue": featured.get("venue"),
            },
            "image_url": public_url,
            "fb_post_id": fb_result.get("id"),
            "ig_post_id": ig_result.get("id"),
            "dry_run": args.dry_run,
        },
        Path(config.DATA_DIR),
    )
    return 0


def _in_window(e: dict, thu_date, sun_date) -> bool:
    try:
        d = datetime.strptime(e.get("date", ""), "%Y-%m-%d").date()
    except Exception:
        return False
    return thu_date <= d <= sun_date


if __name__ == "__main__":
    raise SystemExit(main())
