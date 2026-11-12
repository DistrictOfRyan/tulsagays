#!/usr/bin/env python3
"""
post_weekend.py — publish the weekend CAROUSEL to Facebook + Instagram.

Replaces the old single-image weekend post. Builds the deck with
tools/weekend_carousel.py, then reuses the exact publish path that Monday's
carousel already uses (tools/post_weekly.py helpers) so there is one
implementation of FB multi-photo upload, GitHub Pages hosting, and the IG
carousel container dance.

Idempotent: records data/posts/{week}/weekend_post_results.json and refuses to
double-post the same weekend unless --force is passed.

    python tools/post_weekend.py --dry-run    # build + show, publish nothing
    python tools/post_weekend.py              # build, publish, verify
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import config  # noqa: E402
import weekend_carousel as wc  # noqa: E402


def _results_path(week: str) -> Path:
    return Path(config.DATA_DIR) / "posts" / week / "weekend_post_results.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="build the deck and print the caption, publish nothing")
    ap.add_argument("--force", action="store_true",
                    help="publish even if this weekend was already posted")
    ap.add_argument("--no-voice", action="store_true")
    ap.add_argument("--voice-budget", type=int, default=180)
    ap.add_argument("--fb-only", action="store_true")
    ap.add_argument("--ig-only", action="store_true",
                    help="publish only to Instagram (recovery when FB is live "
                         "but the IG leg failed). Implies --force.")
    args = ap.parse_args()

    week = config.current_week_key()
    results_file = _results_path(week)

    if args.ig_only:
        args.force = True

    if results_file.exists() and not args.force and not args.dry_run:
        prev = json.loads(results_file.read_text(encoding="utf-8"))
        print(f"[SKIP] Weekend already posted for {week}: {prev.get('fb_post_id')}")
        print("       Pass --force to publish anyway.")
        return 0

    # ── Build ────────────────────────────────────────────────────────────
    events = wc.load_events()
    sel = wc.select(events)

    shown = sum(len(v) for v in sel["headlines"].values())
    if shown < 2:
        print(f"[SKIP] Only {shown} weekend events after filtering. Not posting.")
        return 0

    if not args.no_voice:
        stats = wc.voice_pass(sel, budget_s=args.voice_budget)
        print(f"[voice] {stats.get('llm', 0)} LLM / {stats.get('rule', 0)} rule "
              f"of {stats.get('total', 0)}")

    caption = wc.build_caption(sel)
    if not caption:
        print("[SKIP] Empty caption, nothing to post.")
        return 0
    # Facebook takes the full caption; Instagram hard-rejects anything over
    # 2200 chars, which a 12-event weekend with pitches clears easily.
    ig_caption = wc.build_caption(sel, max_chars=wc.IG_CAPTION_LIMIT)
    if len(ig_caption) < len(caption):
        print(f"[IG] caption trimmed {len(caption)} -> {len(ig_caption)} chars "
              f"for the 2200 limit")

    # --ig-only is a RECOVERY path: Facebook already has specific image bytes,
    # so re-rendering here would publish a different deck to Instagram than the
    # one on Facebook. Reuse the slides on disk instead. (Learned the hard way
    # 2026-07-31: an --ig-only rerun re-rendered without the voice pass and put
    # weaker copy on IG than FB had.)
    weekend_dir = Path(config.DATA_DIR) / "posts" / week / "weekend"
    existing = sorted(weekend_dir.glob("weekend_*.png"))
    if args.ig_only and existing:
        slide_paths = existing
        print(f"[render] reusing {len(slide_paths)} existing slides "
              f"(--ig-only never re-renders)")
        # Reuse the saved caption too. Recomputing it would re-run the voice
        # pass and produce copy that no longer matches the slides on disk.
        saved_caption = weekend_dir / "caption.txt"
        if saved_caption.exists():
            caption = saved_caption.read_text(encoding="utf-8")
            ig_caption = wc.build_caption(sel, max_chars=wc.IG_CAPTION_LIMIT)
            if len(caption) <= wc.IG_CAPTION_LIMIT:
                ig_caption = caption
            print(f"[render] reusing saved caption ({len(caption)} chars)")
    else:
        slide_paths = [Path(p) for p in wc.render(sel)]
    wc._print_selection(sel)
    print("\n--- CAPTION ---\n")
    print(caption)
    print(f"\n{len(slide_paths)} slides built.")

    if sel["thin"]:
        print(f"\n[THIN WEEKEND] {sel['fresh_count']} genuinely new events "
              f"(target {wc.MIN_FRESH_TARGET}). Supply problem, not a posting problem: "
              f"run the venue dig and read the bar IG flyers.")

    if args.dry_run:
        print("\n[DRY RUN] Nothing published.")
        return 0

    # ── Publish (reuses Monday's proven carousel path) ────────────────────
    import post_weekly as pw

    fb_post_id = None
    ig_post_id = None
    ig_error = ""

    def _write(outcome: str, channels: dict) -> None:
        # Written after EVERY publish, not only at the end (2026-10-07). The
        # W39 weekend went out on Instagram twice (17926646985185978 at
        # 14:08:41Z and 17980033644088809 at 14:11:46Z, same caption): a run
        # that dies between a publish and the final write leaves no record, and
        # the rerun posts again. The Instagram leg can now wait minutes for
        # GitHub Pages, which widens that window, so record as we go.
        results_file.parent.mkdir(parents=True, exist_ok=True)
        results_file.write_text(json.dumps({
            "week": week,
            "posted_at": datetime.now().isoformat(),
            "friday": sel["friday"], "sunday": sel["sunday"],
            "fb_post_id": fb_post_id,
            "ig_post_id": ig_post_id,
            "ig_error": ig_error or None,
            "outcome": outcome,
            "channels": channels,
            "slides": [p.name for p in slide_paths],
            "events_shown": shown,
            "fresh_count": sel["fresh_count"],
            "thin": sel["thin"],
        }, indent=2), encoding="utf-8")

    if args.ig_only:
        prev = json.loads(results_file.read_text(encoding="utf-8")) \
            if results_file.exists() else {}
        fb_post_id = prev.get("fb_post_id")
        prev_ig = str(prev.get("ig_post_id") or "")
        if prev_ig and prev_ig != "None" and not prev_ig.startswith(("FAILED", "dry_run")):
            print(f"[STOP] Instagram is already live for {week}: {prev_ig}. Not posting again.")
            return 1
        print(f"[FB] skipped (--ig-only); existing post: {fb_post_id}")
    else:
        fb_result = pw.post_fb_carousel(slide_paths, caption)
        fb_post_id = fb_result.get("post_id")
        print(f"[FB] posted: {fb_post_id}")
        _write("IN_PROGRESS", {"facebook": {"status": "ok", "id": fb_post_id}})

    if not args.fb_only:
        try:
            # host_slides_for_ig validates every slide (ig_media_guard) and only
            # returns URLs proven to serve the exact JPEG bytes.
            urls = pw.host_slides_for_ig(slide_paths)
            ig_post_id = pw.post_ig_carousel(urls, ig_caption)
            print(f"[IG] posted: {ig_post_id}")
        except Exception as exc:
            # FB already went out; an IG failure must not stop the results
            # being written, but it must not read as a clean run either.
            ig_error = str(exc)
            print(f"[IG] FAILED (FB post is live): {exc}")

    channels = {}
    if not args.ig_only or fb_post_id:
        channels["facebook"] = ({"status": "ok", "id": fb_post_id} if fb_post_id
                                else {"status": "failed", "error": "no post id"})
    if not args.fb_only:
        channels["instagram"] = ({"status": "ok", "id": ig_post_id} if ig_post_id
                                 else {"status": "failed", "error": ig_error or "no post id"})
    outcome = pw.channel_outcome(channels)
    _write(outcome, channels)
    print(f"\n[OK] Results written to {results_file}")
    print(pw._outcome_line(outcome, channels).replace(
        "python tools/post_weekly.py --ig-only", "python tools/post_weekend.py --ig-only"))
    return pw.outcome_exit_code(outcome)


if __name__ == "__main__":
    raise SystemExit(main())
