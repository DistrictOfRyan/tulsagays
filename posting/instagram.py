"""
Instagram posting module via Meta Graph API.

Handles image, carousel, and reel publishing with built-in
anti-detection strategies (humanized delays, caption jitter, rate limiting).
"""

import sys
import os
import json
import time
import random
import string
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Import project config from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
POSTING_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "posting_log.json"

# Rate limiting: track last post time
_last_post_time: Optional[datetime] = None
MIN_POST_INTERVAL_HOURS = 4


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def _log_api_call(endpoint: str, payload: dict, response: dict) -> None:
    """Append an API call record to the posting log JSON file."""
    POSTING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "endpoint": endpoint,
        "payload": {k: v for k, v in payload.items() if k != "access_token"},
        "response": response,
    }

    log_data: list = []
    if POSTING_LOG_PATH.exists():
        try:
            log_data = json.loads(POSTING_LOG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log_data = []

    log_data.append(entry)
    POSTING_LOG_PATH.write_text(json.dumps(log_data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Anti-detection helpers
# ---------------------------------------------------------------------------

def _random_delay(min_sec: float = 2.0, max_sec: float = 8.0) -> None:
    """Sleep for a random duration between API calls."""
    delay = random.uniform(min_sec, max_sec)
    logger.debug("Sleeping %.1f seconds (inter-call jitter)", delay)
    time.sleep(delay)


def _humanize_pre_post_delay() -> None:
    """Wait 1-5 minutes before posting to simulate human behavior."""
    delay = random.uniform(60, 300)
    logger.info("Pre-post humanization delay: %.0f seconds", delay)
    time.sleep(delay)


def _enforce_rate_limit() -> None:
    """Ensure at least MIN_POST_INTERVAL_HOURS between posts."""
    global _last_post_time

    # Also check the log file for the most recent post
    if _last_post_time is None and POSTING_LOG_PATH.exists():
        try:
            log_data = json.loads(POSTING_LOG_PATH.read_text(encoding="utf-8"))
            if log_data:
                last_ts = log_data[-1].get("timestamp")
                if last_ts:
                    _last_post_time = datetime.fromisoformat(last_ts)
        except (json.JSONDecodeError, OSError, ValueError):
            pass

    if _last_post_time is not None:
        elapsed = datetime.utcnow() - _last_post_time
        minimum = timedelta(hours=MIN_POST_INTERVAL_HOURS)
        if elapsed < minimum:
            wait = (minimum - elapsed).total_seconds()
            logger.warning(
                "Rate limit: last post was %.0f min ago. Waiting %.0f min.",
                elapsed.total_seconds() / 60,
                wait / 60,
            )
            time.sleep(wait)


def humanize_caption(caption: str) -> str:
    """Apply subtle random variations to a caption to avoid fingerprinting.

    - Occasionally add/remove a space before punctuation
    - Sometimes change capitalization of the first word
    - Add subtle line-break variations
    """
    if not caption:
        return caption

    # 20% chance: add or remove a space before a period or exclamation
    if random.random() < 0.2:
        for punct in [".", "!", "?"]:
            if f" {punct}" in caption:
                caption = caption.replace(f" {punct}", punct, 1)
                break
            elif punct in caption and f" {punct}" not in caption:
                caption = caption.replace(punct, f" {punct}", 1)
                break

    # 15% chance: toggle case of first character
    if random.random() < 0.15 and caption[0].isalpha():
        first = caption[0]
        caption = (first.lower() if first.isupper() else first.upper()) + caption[1:]

    # 10% chance: add an extra blank line somewhere between existing lines
    lines = caption.split("\n")
    if len(lines) > 1 and random.random() < 0.10:
        idx = random.randint(1, len(lines) - 1)
        lines.insert(idx, "")
        caption = "\n".join(lines)

    return caption


def vary_schedule_time(base_hour: int, base_minute: int = 0,
                       jitter_minutes: int = 30) -> tuple[int, int]:
    """Return a (hour, minute) tuple jittered +/- *jitter_minutes* from base.

    Useful for scheduling posts that don't land at exact intervals.
    """
    offset = random.randint(-jitter_minutes, jitter_minutes)
    total_minutes = base_hour * 60 + base_minute + offset
    total_minutes = max(0, min(total_minutes, 23 * 60 + 59))
    return divmod(total_minutes, 60)


# ---------------------------------------------------------------------------
# Image hosting helper
# ---------------------------------------------------------------------------

class ImageHosting:
    """Upload images to a public URL so the Meta Graph API can fetch them."""

    @staticmethod
    def upload_to_imgbb(image_path: str, api_key: Optional[str] = None) -> str:
        """Upload an image to imgbb.com and return the public URL.

        Args:
            image_path: Local file path to the image.
            api_key: imgbb API key. Falls back to config.IMGBB_API_KEY.

        Returns:
            Public URL of the uploaded image.
        """
        api_key = api_key or getattr(config, "IMGBB_API_KEY", None)
        if not api_key:
            raise ValueError("No imgbb API key provided. Set config.IMGBB_API_KEY.")

        import base64

        with open(image_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")

        resp = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": api_key, "image": encoded},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"imgbb upload failed: {data}")
        return data["data"]["url"]

    @staticmethod
    def upload_to_github(image_path: str, repo: str, token: str,
                         branch: str = "main",
                         folder: str = "uploads") -> str:
        """Upload an image to a GitHub repo and return the raw URL.

        Args:
            image_path: Local file path.
            repo: 'owner/repo' string.
            token: GitHub personal access token.
            branch: Target branch.
            folder: Folder inside the repo.

        Returns:
            Raw githubusercontent URL.
        """
        import base64

        filename = os.path.basename(image_path)
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        path_in_repo = f"{folder}/{ts}_{filename}"

        with open(image_path, "rb") as f:
            content_b64 = base64.b64encode(f.read()).decode("utf-8")

        url = f"https://api.github.com/repos/{repo}/contents/{path_in_repo}"
        resp = requests.put(
            url,
            json={
                "message": f"Upload {filename}",
                "content": content_b64,
                "branch": branch,
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        resp.raise_for_status()
        return f"https://raw.githubusercontent.com/{repo}/{branch}/{path_in_repo}"

    @staticmethod
    def from_public_url(url: str) -> str:
        """Pass-through for images already hosted at a public URL."""
        return url


# ---------------------------------------------------------------------------
# Graph API helpers
# ---------------------------------------------------------------------------

def _graph_post(endpoint: str, params: dict, access_token: str) -> dict:
    """POST to the Meta Graph API with logging and error handling."""
    url = f"{GRAPH_API_BASE}/{endpoint}"
    params["access_token"] = access_token

    resp = requests.post(url, data=params, timeout=120)
    data = resp.json()

    _log_api_call(url, params, data)

    if "error" in data:
        error = data["error"]
        code = error.get("code", 0)
        msg = error.get("message", "Unknown error")

        if code == 190:
            raise PermissionError(f"Access token expired or invalid: {msg}")
        elif code in (4, 17, 32):
            raise RuntimeError(f"Rate limit hit (code {code}): {msg}")
        else:
            raise RuntimeError(f"Graph API error (code {code}): {msg}")

    return data


def _graph_get(endpoint: str, params: dict, access_token: str) -> dict:
    """GET from the Meta Graph API with logging and error handling."""
    url = f"{GRAPH_API_BASE}/{endpoint}"
    params["access_token"] = access_token

    resp = requests.get(url, params=params, timeout=60)
    data = resp.json()

    _log_api_call(url, params, data)

    if "error" in data:
        error = data["error"]
        code = error.get("code", 0)
        msg = error.get("message", "Unknown error")

        if code == 190:
            raise PermissionError(f"Access token expired or invalid: {msg}")
        elif code in (4, 17, 32):
            raise RuntimeError(f"Rate limit hit (code {code}): {msg}")
        else:
            raise RuntimeError(f"Graph API error (code {code}): {msg}")

    return data


# ---------------------------------------------------------------------------
# Posting functions
# ---------------------------------------------------------------------------

def post_carousel(
    image_paths: list[str],
    caption: str,
    access_token: Optional[str] = None,
    ig_user_id: Optional[str] = None,
) -> dict:
    """Post a carousel (multiple images) to Instagram.

    Args:
        image_paths: List of public image URLs (or local paths that will be
            uploaded via ImageHosting first).
        caption: Post caption text.
        access_token: Meta access token. Defaults to config.META_ACCESS_TOKEN.
        ig_user_id: Instagram user ID. Defaults to config.META_IG_USER_ID.

    Returns:
        Dict with 'id' of the published media.
    """
    global _last_post_time
    access_token = access_token or config.META_ACCESS_TOKEN
    ig_user_id = ig_user_id or config.META_IG_USER_ID

    if len(image_paths) < 2:
        raise ValueError("Carousel requires at least 2 images.")
    if len(image_paths) > 10:
        raise ValueError("Carousel supports a maximum of 10 images.")

    _enforce_rate_limit()
    _humanize_pre_post_delay()

    caption = humanize_caption(caption)

    # Step 1: Create individual media containers
    container_ids = []
    for img_url in image_paths:
        _random_delay()
        result = _graph_post(
            f"{ig_user_id}/media",
            {"image_url": img_url, "is_carousel_item": "true"},
            access_token,
        )
        container_ids.append(result["id"])
        logger.info("Created carousel item container: %s", result["id"])

    # Step 2: Create the carousel container
    _random_delay()
    carousel = _graph_post(
        f"{ig_user_id}/media",
        {
            "media_type": "CAROUSEL",
            "caption": caption,
            "children": ",".join(container_ids),
        },
        access_token,
    )
    carousel_id = carousel["id"]
    logger.info("Created carousel container: %s", carousel_id)

    # Step 3: Publish
    _random_delay()
    publish_result = _graph_post(
        f"{ig_user_id}/media_publish",
        {"creation_id": carousel_id},
        access_token,
    )
    logger.info("Published carousel: %s", publish_result.get("id"))

    _last_post_time = datetime.utcnow()
    return publish_result


def post_single_image(
    image_path: str,
    caption: str,
    access_token: Optional[str] = None,
    ig_user_id: Optional[str] = None,
) -> dict:
    """Post a single image to Instagram.

    Args:
        image_path: Public URL of the image.
        caption: Post caption text.
        access_token: Meta access token. Defaults to config.META_ACCESS_TOKEN.
        ig_user_id: Instagram user ID. Defaults to config.META_IG_USER_ID.

    Returns:
        Dict with 'id' of the published media.
    """
    global _last_post_time
    access_token = access_token or config.META_ACCESS_TOKEN
    ig_user_id = ig_user_id or config.META_IG_USER_ID

    _enforce_rate_limit()
    _humanize_pre_post_delay()

    caption = humanize_caption(caption)

    # Step 1: Create media container
    _random_delay()
    container = _graph_post(
        f"{ig_user_id}/media",
        {"image_url": image_path, "caption": caption},
        access_token,
    )
    container_id = container["id"]
    logger.info("Created image container: %s", container_id)

    # Step 2: Publish
    _random_delay()
    publish_result = _graph_post(
        f"{ig_user_id}/media_publish",
        {"creation_id": container_id},
        access_token,
    )
    logger.info("Published image: %s", publish_result.get("id"))

    _last_post_time = datetime.utcnow()
    return publish_result


def post_reel(
    video_path: str,
    caption: str,
    access_token: Optional[str] = None,
    ig_user_id: Optional[str] = None,
) -> dict:
    """Post a Reel (video) to Instagram.

    Args:
        video_path: Public URL of the video file.
        caption: Post caption text.
        access_token: Meta access token. Defaults to config.META_ACCESS_TOKEN.
        ig_user_id: Instagram user ID. Defaults to config.META_IG_USER_ID.

    Returns:
        Dict with 'id' of the published media.
    """
    global _last_post_time
    access_token = access_token or config.META_ACCESS_TOKEN
    ig_user_id = ig_user_id or config.META_IG_USER_ID

    _enforce_rate_limit()
    _humanize_pre_post_delay()

    caption = humanize_caption(caption)

    # Step 1: Create reel container
    _random_delay()
    container = _graph_post(
        f"{ig_user_id}/media",
        {
            "media_type": "REELS",
            "video_url": video_path,
            "caption": caption,
        },
        access_token,
    )
    container_id = container["id"]
    logger.info("Created reel container: %s", container_id)

    # Step 2: Wait for video processing (poll status)
    for attempt in range(30):
        _random_delay(5, 10)
        status = _graph_get(
            container_id,
            {"fields": "status_code"},
            access_token,
        )
        status_code = status.get("status_code", "UNKNOWN")
        logger.debug("Reel processing status: %s (attempt %d)", status_code, attempt + 1)

        if status_code == "FINISHED":
            break
        elif status_code == "ERROR":
            raise RuntimeError(f"Reel processing failed: {status}")
    else:
        raise TimeoutError("Reel processing did not finish in time.")

    # Step 3: Publish
    _random_delay()
    publish_result = _graph_post(
        f"{ig_user_id}/media_publish",
        {"creation_id": container_id},
        access_token,
    )
    logger.info("Published reel: %s", publish_result.get("id"))

    _last_post_time = datetime.utcnow()
    return publish_result


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------

def get_insights(media_id: str, access_token: Optional[str] = None) -> dict:
    """Get engagement metrics for a specific post.

    Returns dict with keys: impressions, reach, likes, comments, saves, shares.
    """
    access_token = access_token or config.META_ACCESS_TOKEN

    metrics = "impressions,reach,likes,comments,saved,shares"
    result = _graph_get(
        f"{media_id}/insights",
        {"metric": metrics},
        access_token,
    )

    parsed = {}
    for item in result.get("data", []):
        name = item.get("name", "")
        values = item.get("values", [{}])
        parsed[name] = values[0].get("value", 0) if values else 0

    return parsed


def get_account_insights(
    ig_user_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Get account-level insights (follower count, engagement rate).

    Returns dict with follower_count, media_count, and recent engagement data.
    """
    access_token = access_token or config.META_ACCESS_TOKEN
    ig_user_id = ig_user_id or config.META_IG_USER_ID

    # Basic account info
    account = _graph_get(
        ig_user_id,
        {"fields": "followers_count,media_count,username"},
        access_token,
    )

    # Account-level engagement insights (last 28 days)
    try:
        insights = _graph_get(
            f"{ig_user_id}/insights",
            {
                "metric": "impressions,reach,follower_count",
                "period": "day",
                "since": int((datetime.utcnow() - timedelta(days=28)).timestamp()),
                "until": int(datetime.utcnow().timestamp()),
            },
            access_token,
        )
    except RuntimeError:
        insights = {"data": []}

    account["insights"] = insights.get("data", [])
    return account
