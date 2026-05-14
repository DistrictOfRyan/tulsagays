"""Graph API helpers for the TulsaGays mid-week social pipeline.

Imported by the four GHA-driven scripts:
  - run_tuesday_community_prompt.py
  - run_tuesday_reply_scraper.py
  - run_wednesday_lastminute.py
  - run_thursday_spotlight.py

All Graph API calls go through this module. None of these helpers call
the /feed endpoint, which was the text-only bug in the retired
tulsagays-wednesday-social task. Image posts use /photos (FB) and
/media + /media_publish (IG).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

API_BASE = "https://graph.facebook.com/v19.0"
CONFIG_PATH = Path(__file__).resolve().parents[1] / "meta_api_config.json"
NETLIFY_BASE = "https://www.tulsagays.com"


def load_meta_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        cfg = json.load(f)
    for required in ("page_id", "instagram_business_account_id", "page_access_token"):
        if not cfg.get(required):
            raise RuntimeError(f"meta_api_config.json missing required field: {required}")
    return cfg


def public_url_for(rel_path: str) -> str:
    """Map a docs-relative path to its tulsagays.com URL."""
    rel = rel_path.lstrip("/")
    if rel.startswith("docs/"):
        rel = rel[len("docs/"):]
    return f"{NETLIFY_BASE}/{rel}"


def wait_for_public_url(url: str, timeout_s: int = 90, poll_s: int = 5) -> None:
    """Block until the URL returns HTTP 200 or timeout expires."""
    deadline = time.time() + timeout_s
    last_status = None
    while time.time() < deadline:
        try:
            r = requests.head(url, timeout=10, allow_redirects=True)
            last_status = r.status_code
            if r.status_code == 200:
                return
        except requests.RequestException as e:
            last_status = str(e)
        time.sleep(poll_s)
    raise RuntimeError(f"Public URL never became live: {url} (last status: {last_status})")


def post_facebook_photo(
    cfg: dict[str, Any], image_url: str, caption: str, dry_run: bool = False
) -> dict[str, Any]:
    """POST /{page_id}/photos with an image URL and caption.

    Never falls back to /feed. If this errors, callers should NOT post text-only.
    """
    if dry_run:
        return {"id": "dry_run_fb_id", "dry_run": True, "would_post": {"image_url": image_url}}
    resp = requests.post(
        f"{API_BASE}/{cfg['page_id']}/photos",
        data={
            "url": image_url,
            "caption": caption,
            "access_token": cfg["page_access_token"],
        },
        timeout=30,
    )
    result = resp.json()
    if "id" not in result:
        raise RuntimeError(f"Facebook photo post failed: {result}")
    return result


def post_instagram_photo(
    cfg: dict[str, Any], image_url: str, caption: str, dry_run: bool = False
) -> dict[str, Any]:
    """Two-step IG image post: create container, then publish."""
    if dry_run:
        return {"id": "dry_run_ig_id", "dry_run": True, "would_post": {"image_url": image_url}}
    ig_id = cfg["instagram_business_account_id"]

    container = requests.post(
        f"{API_BASE}/{ig_id}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": cfg["page_access_token"],
        },
        timeout=30,
    ).json()
    if "id" not in container:
        raise RuntimeError(f"IG container create failed: {container}")

    publish = requests.post(
        f"{API_BASE}/{ig_id}/media_publish",
        data={"creation_id": container["id"], "access_token": cfg["page_access_token"]},
        timeout=30,
    ).json()
    if "id" not in publish:
        raise RuntimeError(f"IG publish failed: {publish}")
    return publish


def get_fb_post_comments(cfg: dict[str, Any], fb_post_id: str) -> list[dict[str, Any]]:
    resp = requests.get(
        f"{API_BASE}/{fb_post_id}/comments",
        params={
            "fields": "id,from,message,created_time",
            "limit": 100,
            "access_token": cfg["page_access_token"],
        },
        timeout=20,
    ).json()
    if "error" in resp:
        raise RuntimeError(f"FB comments fetch failed: {resp['error']}")
    return resp.get("data", [])


def get_ig_post_comments(cfg: dict[str, Any], ig_post_id: str) -> list[dict[str, Any]]:
    resp = requests.get(
        f"{API_BASE}/{ig_post_id}/comments",
        params={
            "fields": "id,text,username,timestamp",
            "limit": 100,
            "access_token": cfg["page_access_token"],
        },
        timeout=20,
    ).json()
    if "error" in resp:
        raise RuntimeError(f"IG comments fetch failed: {resp['error']}")
    return resp.get("data", [])


def log_engagement_event(week_key: str, payload: dict[str, Any], data_dir: Path) -> Path:
    """Append a row to data/posts/{week}/engagement_log.json (creating the list if absent)."""
    log_dir = data_dir / "posts" / week_key
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "engagement_log.json"
    rows: list[dict[str, Any]] = []
    if log_path.exists():
        with log_path.open(encoding="utf-8") as f:
            existing = json.load(f)
        rows = existing if isinstance(existing, list) else [existing]
    rows.append(payload)
    with log_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    return log_path
