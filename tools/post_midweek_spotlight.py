"""
Tuesday/Thursday mid-week individual event spotlight posts for Tulsa Gays.

Tuesday  10am CT: spotlight top 2 events happening Thu–Sat this week.
Thursday 10am CT: spotlight top 2 events happening Fri–Sun this week.

Usage:
  python tools/post_midweek_spotlight.py
  python tools/post_midweek_spotlight.py --dry-run
  python tools/post_midweek_spotlight.py --day tuesday
  python tools/post_midweek_spotlight.py --day thursday
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
from content.image_maker import (
    BG, NEON_PINK, WHITE, GRAY, DAY_ACCENTS,
    W, H, PAD,
    _font, _draw_centered, _draw_wrapped, _pink_bar, _watermark,
    clean_text, clean_venue, format_date,
)
from tools.social_lib import (
    load_meta_config,
    log_engagement_event,
    post_facebook_photo,
    post_instagram_photo,
    public_url_for,
    wait_for_public_url,
)

SPOTLIGHT_PROMPTS = [
    "Drop your plans in the comments 👇",
    "Tag someone who needs to go to this! 👇",
    "Who's going? Comment below! 👇",
    "Save this for your weekend plans 🔖",
]

_SAVE_PROMPT = "Save this for your weekend plans 🔖"
_ENGAGEMENT_PROMPTS = [p for p in SPOTLIGHT_PROMPTS if p != _SAVE_PROMPT]


def select_spotlight_events(events: list, day: str, n: int = 2) -> list:
    """
    day = 'tuesday' or 'thursday'
    Tuesday:  prefer events happening Thu-Sat this week (weekday 3, 4, 5)
    Thursday: prefer events happening Fri-Sun this week (weekday 4, 5, 6)

    Sort key (all ascending, so lower = better rank):
      1. preferred window (0=yes, 1=no)
      2. has_specific_time (0=yes, 1=no)
      3. is_lgbtq (0=yes, 1=no)
      4. event name (alphabetical tiebreak)

    Filters: events must have a parseable YYYY-MM-DD date and not be in the past.
    Skip events that fail _is_skip from eotw_selector.
    Returns top n events.
    """
    try:
        from eotw_selector import _is_lgbtq, _is_skip
    except ImportError:
        def _is_lgbtq(e): return False  # noqa: E731
        def _is_skip(e): return False   # noqa: E731

    today = date.today()
    if day == "tuesday":
        preferred_weekdays = {3, 4, 5}  # Thu, Fri, Sat
    else:
        preferred_weekdays = {4, 5, 6}  # Fri, Sat, Sun

    eligible = []
    for e in events:
        date_str = (e.get("date") or "").strip()
        if not date_str:
            continue
        try:
            ev_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if ev_date < today:
            continue
        if _is_skip(e):
            continue
        eligible.append(e)

    def _sort_key(e: dict) -> tuple:
        date_str = e.get("date", "")
        try:
            ev_weekday = datetime.strptime(date_str, "%Y-%m-%d").weekday()
            preferred = ev_weekday in preferred_weekdays
        except Exception:
            preferred = False
        has_time = bool((e.get("time") or "").strip())
        lgbtq = _is_lgbtq(e)
        return (
            0 if preferred else 1,
            0 if has_time else 1,
            0 if lgbtq else 1,
            (e.get("name") or "").lower(),
        )

    eligible.sort(key=_sort_key)
    return eligible[:n]


def make_spotlight_image(event: dict, output_path: str) -> str:
    """
    Generate a 1080x1080 spotlight image using brand colors from image_maker.py.

    Layout:
      Top 40%  (432px): event image if available, else solid day-accent color block
                        with "TULSA GAYS" branding centered.
      Bottom 60% (648px): dark background, event name (large Poiret One, white),
                          venue (medium, neon pink), date·time (medium, gray),
                          tulsagays.com (small, gray footer).

    Returns output_path.
    """
    from PIL import Image, ImageDraw

    iW, iH = 1080, 1080
    TOP_H = int(iH * 0.40)   # 432 px

    img = Image.new("RGB", (iW, iH), BG)
    draw = ImageDraw.Draw(img)

    # Determine day accent from event date
    day_name = ""
    date_str = (event.get("date") or "").strip()
    if date_str:
        try:
            day_name = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A")
        except Exception:
            pass
    accent = DAY_ACCENTS.get(day_name, NEON_PINK)

    # ── Top block: event image or branded color ───────────────────────────
    img_placed = False
    for src_key in ("image_path", "image_url"):
        src = (event.get(src_key) or "").strip()
        if not src:
            continue
        try:
            if src_key == "image_path":
                if not os.path.exists(src):
                    continue
                ev_img = Image.open(src).convert("RGB")
            else:
                import requests as _req
                from io import BytesIO
                r = _req.get(src, timeout=10)
                r.raise_for_status()
                ev_img = Image.open(BytesIO(r.content)).convert("RGB")
            # Aspect-fill crop to iW × TOP_H
            ev_w, ev_h = ev_img.size
            target_r = iW / TOP_H
            if (ev_w / ev_h) > target_r:
                new_w = int(ev_h * target_r)
                left = (ev_w - new_w) // 2
                ev_img = ev_img.crop((left, 0, left + new_w, ev_h))
            else:
                new_h = int(ev_w / target_r)
                top_crop = (ev_h - new_h) // 2
                ev_img = ev_img.crop((0, top_crop, ev_w, top_crop + new_h))
            ev_img = ev_img.resize((iW, TOP_H), Image.LANCZOS)
            img.paste(ev_img, (0, 0))
            img_placed = True
            break
        except Exception:
            continue

    if not img_placed:
        # Solid accent color block with centered TULSA GAYS text
        draw.rectangle([0, 0, iW - 1, TOP_H - 1], fill=accent)
        f_brand_t = _font("poiret", 88)
        f_brand_g = _font("poiret", 88)
        brand_total_h = 88 + 8 + 88
        brand_y = (TOP_H - brand_total_h) // 2
        _draw_centered(draw, "TULSA", brand_y, f_brand_t, BG)
        _draw_centered(draw, "GAYS", brand_y + 96, f_brand_g, BG)

    # Pink separator bar
    _pink_bar(draw, TOP_H, height=4)

    # ── Bottom block: event info ──────────────────────────────────────────
    ev_name  = clean_text(event.get("name") or "Event")
    ev_venue = clean_venue(event.get("venue") or "")
    ev_time  = (event.get("time") or "").strip()
    ev_date  = format_date(date_str)

    f_name = _font("poiret", 72 if len(ev_name) <= 28 else 54)
    f_det  = _font("segoe-semi", 30)
    f_foot = _font("poiret", 26)

    y = TOP_H + 24

    # Event name (white, large)
    y = _draw_wrapped(draw, ev_name, y, f_name, WHITE,
                      max_px=iW - PAD * 2, max_lines=3, line_gap=8)
    y += 20

    # Venue (neon pink)
    if ev_venue:
        y = _draw_wrapped(draw, f"@ {ev_venue}", y, f_det, NEON_PINK,
                          max_px=iW - PAD * 2, max_lines=2, line_gap=6)
        y += 10

    # Date · Time (gray)
    dt_parts = [p for p in (ev_date, ev_time) if p]
    if dt_parts:
        y = _draw_centered(draw, "  ·  ".join(dt_parts), y, f_det, GRAY)

    # Footer
    _draw_centered(draw, "tulsagays.com", iH - 52, f_foot, GRAY)
    _pink_bar(draw, iH - 4, height=4)
    _watermark(draw)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG", optimize=True)
    return output_path


def make_spotlight_caption(event: dict) -> str:
    """
    Format:
      ✨ This [Weekday]: [Event Name]

      📍 [Venue]
      🕐 [Time]
      [One sentence description if available]

      [random engagement prompt]
      Save this for your weekend plans 🔖

      #TulsaGays #TulsaOK #TulsaLGBTQ #TulsaEvents
    """
    date_str = (event.get("date") or "").strip()
    weekday = ""
    if date_str:
        try:
            weekday = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A")
        except Exception:
            pass

    name  = clean_text(event.get("name") or "")
    venue = clean_venue(event.get("venue") or "")
    time_ = (event.get("time") or "").strip()
    desc  = (event.get("description") or "").strip()

    lines: list[str] = []

    # Hook line
    hook = f"✨ This {weekday}: {name}" if weekday else f"✨ {name}"
    lines.append(hook)
    lines.append("")

    if venue:
        lines.append(f"📍 {venue}")
    if time_:
        lines.append(f"🕐 {time_}")

    # One-sentence description: take first sentence only
    if desc:
        first_sentence = re.split(r"(?<=[.!?])\s", desc, maxsplit=1)[0].strip()
        if first_sentence:
            lines.append(first_sentence)

    lines.append("")

    # Engagement CTAs
    lines.append(random.choice(_ENGAGEMENT_PROMPTS))
    lines.append(_SAVE_PROMPT)
    lines.append("")

    lines.append("#TulsaGays #TulsaOK #TulsaLGBTQ #TulsaEvents")

    return "\n".join(lines)


def post_spotlight(event: dict, dry_run: bool = False) -> bool:
    """Generate image + caption and post to Instagram and Facebook. Returns True on success."""
    week_key = config.current_week_key()
    slug = re.sub(r"[^a-z0-9]+", "-", (event.get("name") or "spotlight").lower())[:40].strip("-")
    img_name = f"spotlight-{slug}-{datetime.now().strftime('%Y%m%d')}.png"

    out_rel = Path("docs") / "posts" / week_key
    out_abs = ROOT / out_rel
    img_path = str(out_abs / img_name)

    make_spotlight_image(event, img_path)
    size = Path(img_path).stat().st_size
    if size < 30_000:
        raise RuntimeError(f"Generated spotlight image too small ({size}B); aborting.")
    print(f"[image] {img_path}  ({size // 1024}KB)")

    caption = make_spotlight_caption(event)
    public_url = public_url_for(str(out_rel / img_name))

    if dry_run:
        print(f"[DRY RUN] would post to: {public_url}")
        print(f"[DRY RUN] caption:\n{caption}")
        return True

    # Push image to GitHub Pages so the Graph API can fetch a public URL
    subprocess.run(["git", "add", str(Path(img_path).relative_to(ROOT))],
                   cwd=ROOT, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"tulsagays-midweek-spotlight: {slug}"],
        cwd=ROOT, check=True,
    )
    subprocess.run(["git", "push", "origin", "HEAD"], cwd=ROOT, check=True)

    wait_for_public_url(public_url)

    cfg = load_meta_config()
    fb_result = post_facebook_photo(cfg, public_url, caption)
    print(f"[FB] post_id={fb_result.get('id')}")

    ig_result: dict = {"id": "skipped"}
    success = True
    try:
        ig_result = post_instagram_photo(cfg, public_url, caption)
        print(f"[IG] post_id={ig_result.get('id')}")
    except RuntimeError as e:
        print(f"WARN: IG post failed (FB is live): {e}")
        ig_result = {"id": "failed", "error": str(e)}
        success = False

    log_engagement_event(
        week_key,
        {
            "task": "midweek-spotlight",
            "fired_at": datetime.now().isoformat(timespec="seconds"),
            "week": week_key,
            "event_name": event.get("name"),
            "event_date": event.get("date"),
            "image_url": public_url,
            "fb_post_id": fb_result.get("id"),
            "ig_post_id": ig_result.get("id"),
        },
        ROOT,
    )

    # Commit the engagement log
    log_rel = Path("docs") / "posts" / week_key / "engagement_log.json"
    subprocess.run(["git", "add", str(log_rel)], cwd=ROOT, check=True)
    result = subprocess.run(
        ["git", "commit", "-m", f"tulsagays-midweek-spotlight: {slug} log"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if result.returncode == 0:
        subprocess.run(["git", "push", "origin", "HEAD"], cwd=ROOT, check=True)

    return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Post Tuesday/Thursday mid-week event spotlight to FB + IG."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate images and print captions; skip social posts and git push.")
    parser.add_argument("--day", choices=["tuesday", "thursday"],
                        help="Override day detection (default: inferred from today's weekday).")
    args = parser.parse_args()

    # Determine which day mode to run
    if args.day:
        day = args.day
    else:
        weekday_num = datetime.now().weekday()
        if weekday_num == 1:
            day = "tuesday"
        elif weekday_num == 3:
            day = "thursday"
        else:
            day_names = ["Monday", "Tuesday", "Wednesday", "Thursday",
                         "Friday", "Saturday", "Sunday"]
            print(
                f"Today is {day_names[weekday_num]}, not Tuesday or Thursday. "
                "Use --day tuesday or --day thursday to force a run."
            )
            sys.exit(0)

    week_key = config.current_week_key()
    print(f"[midweek-spotlight] day={day}  week={week_key}  dry_run={args.dry_run}")

    # Load this week's events (same candidate paths as run_thursday_spotlight.py)
    candidates = [
        ROOT / "docs" / "data" / "events" / f"{week_key}_all.json",
        Path(config.EVENTS_DIR) / f"{week_key}_all.json",
    ]
    events_path = next((p for p in candidates if p.exists()), None)
    if not events_path:
        print(f"No events file found for {week_key}; skipping silently.")
        sys.exit(0)

    with events_path.open(encoding="utf-8") as f:
        payload = json.load(f)
    events: list = payload.get("events", payload) if isinstance(payload, dict) else payload
    if not isinstance(events, list):
        events = []
    print(f"[midweek-spotlight] loaded {len(events)} events from {events_path.name}")

    selected = select_spotlight_events(events, day, n=2)
    if not selected:
        print(f"No eligible spotlight events for {day}; skipping silently.")
        sys.exit(0)

    print(f"[midweek-spotlight] selected {len(selected)} event(s):")
    for ev in selected:
        print(f"  - {ev.get('name')}  ({ev.get('date')} {ev.get('time', '')})")

    for ev in selected:
        success = post_spotlight(ev, dry_run=args.dry_run)
        status = "OK" if success else "PARTIAL (FB ok, IG failed)"
        print(f"  [{status}] {ev.get('name')}")

    print("[midweek-spotlight] done")
