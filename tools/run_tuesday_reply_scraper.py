"""Tuesday 9pm CT: read FB+IG comments on today's community-prompt post, auto-add
any URLs to sources.json, queue venue names/handles for human review.

Read-only on the social side. Never posts.

Usage:
  python tools/run_tuesday_reply_scraper.py
  python tools/run_tuesday_reply_scraper.py --dry-run   # fetch + parse, do not write files
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from tools.social_lib import (  # noqa: E402
    get_fb_post_comments,
    get_ig_post_comments,
    load_meta_config,
)

URL_RX = re.compile(r"https?://[^\s\)\]]+", re.I)
HANDLE_RX = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z0-9_.]{3,30})")


def _today_iso() -> str:
    return date.today().isoformat()


def _engagement_log(week_key: str) -> Path:
    data_dir = Path(config.DATA_DIR) if not isinstance(config.DATA_DIR, Path) else config.DATA_DIR
    return data_dir / "posts" / week_key / "engagement_log.json"


def _find_todays_prompt_post(week_key: str) -> dict | None:
    log_path = _engagement_log(week_key)
    if not log_path.exists():
        return None
    with log_path.open(encoding="utf-8") as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        rows = [rows]
    today = _today_iso()
    for row in reversed(rows):
        if (
            row.get("task") == "tulsagays-tuesday-community-prompt"
            and str(row.get("fired_at", "")).startswith(today)
            and not row.get("dry_run")
        ):
            return row
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    week_key = config.current_week_key()
    prompt_post = _find_todays_prompt_post(week_key)
    if not prompt_post:
        print("No live community-prompt post fired today. Nothing to scrape.")
        return 0
    fb_id = prompt_post.get("fb_post_id")
    ig_id = prompt_post.get("ig_post_id")
    print(f"FB post: {fb_id}  IG post: {ig_id}")

    cfg = load_meta_config()

    try:
        fb_comments = get_fb_post_comments(cfg, fb_id) if fb_id and fb_id != "skipped" else []
    except RuntimeError as e:
        print(f"WARN: FB comments fetch failed: {e}")
        fb_comments = []

    try:
        ig_comments = (
            get_ig_post_comments(cfg, ig_id) if ig_id and ig_id not in ("skipped", "failed") else []
        )
    except RuntimeError as e:
        print(f"WARN: IG comments fetch failed: {e}")
        ig_comments = []

    print(f"FB comments: {len(fb_comments)}  IG comments: {len(ig_comments)}")

    urls: set[str] = set()
    handles: set[str] = set()
    texts: list[str] = []
    for c in fb_comments:
        msg = (c.get("message") or "").strip()
        if msg:
            urls.update(URL_RX.findall(msg))
            handles.update(HANDLE_RX.findall(msg))
            texts.append(msg)
    for c in ig_comments:
        msg = (c.get("text") or "").strip()
        if msg:
            urls.update(URL_RX.findall(msg))
            handles.update(HANDLE_RX.findall(msg))
            texts.append(msg)

    print(f"Extracted: {len(urls)} URLs, {len(handles)} handles, {len(texts)} comments")

    sources_path = ROOT / "sources.json"
    review_path = ROOT / "data" / "community" / "pending_sources_review.json"
    review_path.parent.mkdir(parents=True, exist_ok=True)

    added_urls: list[str] = []
    if urls and not args.dry_run:
        if sources_path.exists():
            with sources_path.open(encoding="utf-8") as f:
                sources = json.load(f)
        else:
            sources = {"sources": []}
        existing = {s.get("url") for s in sources.get("sources", []) if isinstance(s, dict)}
        now_iso = datetime.now().isoformat(timespec="seconds")
        for url in sorted(urls):
            if url in existing:
                continue
            sources.setdefault("sources", []).append(
                {
                    "url": url,
                    "added_by": "tulsagays-tuesday-reply-scraper",
                    "added_at": now_iso,
                    "status": "pending_first_scrape",
                }
            )
            added_urls.append(url)
        if added_urls:
            with sources_path.open("w", encoding="utf-8") as f:
                json.dump(sources, f, indent=2, ensure_ascii=False)

    queue_changed = False
    if (texts or handles) and not args.dry_run:
        if review_path.exists():
            with review_path.open(encoding="utf-8") as f:
                queue = json.load(f)
        else:
            queue = []
        seen = {item.get("text") for item in queue if isinstance(item, dict)}
        now_iso = datetime.now().isoformat(timespec="seconds")
        for t in texts:
            if t in seen:
                continue
            queue.append(
                {
                    "text": t,
                    "captured_at": now_iso,
                    "week": week_key,
                    "status": "needs_review",
                }
            )
            queue_changed = True
        for h in sorted(handles):
            entry = f"@{h}"
            if entry in seen:
                continue
            queue.append(
                {
                    "text": entry,
                    "kind": "handle",
                    "captured_at": now_iso,
                    "week": week_key,
                    "status": "needs_review",
                }
            )
            queue_changed = True
        if queue_changed:
            with review_path.open("w", encoding="utf-8") as f:
                json.dump(queue, f, indent=2, ensure_ascii=False)

    print(
        f"Auto-added URLs: {len(added_urls)}  Queue grew: {queue_changed}  "
        f"dry_run={args.dry_run}"
    )

    if not args.dry_run and (added_urls or queue_changed):
        import subprocess

        paths_to_add: list[str] = []
        if added_urls:
            paths_to_add.append("sources.json")
        if queue_changed:
            paths_to_add.append("data/community/pending_sources_review.json")
        subprocess.run(["git", "add", *paths_to_add], cwd=ROOT, check=True)
        msg = (
            f"tulsagays-tuesday-reply-scraper: {week_key}, "
            f"{len(added_urls)} urls auto-added, "
            f"queue {'updated' if queue_changed else 'unchanged'}"
        )
        subprocess.run(["git", "commit", "-m", msg], cwd=ROOT, check=True)
        subprocess.run(["git", "push", "origin", "HEAD"], cwd=ROOT, check=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
