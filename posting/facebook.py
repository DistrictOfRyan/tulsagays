"""Facebook Page posting via Meta Graph API.

Posts a text caption (optionally with one or more photos) to a configured
Facebook Page. Works for any Page whose ID and access token are provided,
so the same module drives both the Tulsa Gays Page and the HHHH Page.

This is a pure server-to-server flow: no Instagram involvement, no
"cross-post" toggle. The IG to FB share button in the IG app is bypassed
entirely, which is what avoids posts landing on a personal profile.

Facebook Groups are not supported by Meta's Graph API for third-party
apps (publish_to_groups was deprecated in April 2024). To get a post into
a group, post to the Page here, then share the Page post into the group
manually from the Facebook app.
"""

import logging
from pathlib import Path
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


class FacebookPostError(RuntimeError):
    pass


def _require(value: str, name: str) -> str:
    if not value:
        raise FacebookPostError(
            f"Missing {name}. Set it in .env or pass it explicitly."
        )
    return value


def _upload_photo(
    page_id: str,
    access_token: str,
    image_path: Path,
    published: bool,
) -> str:
    url = f"{GRAPH_API_BASE}/{page_id}/photos"
    with image_path.open("rb") as fh:
        resp = requests.post(
            url,
            data={"published": "true" if published else "false", "access_token": access_token},
            files={"source": fh},
            timeout=60,
        )
    if not resp.ok:
        raise FacebookPostError(f"photo upload failed ({image_path.name}): {resp.status_code} {resp.text}")
    body = resp.json()
    photo_id = body.get("id")
    if not photo_id:
        raise FacebookPostError(f"photo upload returned no id: {body}")
    return photo_id


def post_to_page(
    message: str,
    image_paths: Optional[list] = None,
    page_id: Optional[str] = None,
    access_token: Optional[str] = None,
) -> dict:
    """Publish a post to a Facebook Page.

    - Text only: image_paths is None or empty.
    - Single photo: image_paths has one entry; photo is published with the caption.
    - Carousel (multi-photo): image_paths has 2+ entries; each is uploaded
      unpublished, then attached to a single feed post.
    """
    page_id = _require(page_id or "", "page_id")
    access_token = _require(access_token or "", "access_token")
    message = _require(message, "message")

    paths = [Path(p) for p in (image_paths or [])]
    for p in paths:
        if not p.exists():
            raise FacebookPostError(f"image not found: {p}")

    if not paths:
        url = f"{GRAPH_API_BASE}/{page_id}/feed"
        resp = requests.post(
            url,
            data={"message": message, "access_token": access_token},
            timeout=30,
        )
        if not resp.ok:
            raise FacebookPostError(f"feed post failed: {resp.status_code} {resp.text}")
        return resp.json()

    if len(paths) == 1:
        url = f"{GRAPH_API_BASE}/{page_id}/photos"
        with paths[0].open("rb") as fh:
            resp = requests.post(
                url,
                data={"caption": message, "access_token": access_token},
                files={"source": fh},
                timeout=60,
            )
        if not resp.ok:
            raise FacebookPostError(f"photo post failed: {resp.status_code} {resp.text}")
        return resp.json()

    photo_ids = [_upload_photo(page_id, access_token, p, published=False) for p in paths]
    attached = {f"attached_media[{i}]": '{"media_fbid":"' + pid + '"}' for i, pid in enumerate(photo_ids)}
    url = f"{GRAPH_API_BASE}/{page_id}/feed"
    payload = {"message": message, "access_token": access_token, **attached}
    resp = requests.post(url, data=payload, timeout=60)
    if not resp.ok:
        raise FacebookPostError(f"carousel feed post failed: {resp.status_code} {resp.text}")
    body = resp.json()
    body["photo_ids"] = photo_ids
    return body


def post_to_hhhh(message: str, image_paths: Optional[list] = None) -> dict:
    return post_to_page(
        message,
        image_paths=image_paths,
        page_id=config.HHHH_PAGE_ID,
        access_token=config.HHHH_PAGE_ACCESS_TOKEN,
    )


def post_to_tulsagays(message: str, image_paths: Optional[list] = None) -> dict:
    return post_to_page(
        message,
        image_paths=image_paths,
        page_id=config.TULSAGAYS_PAGE_ID,
        access_token=config.TULSAGAYS_PAGE_ACCESS_TOKEN or config.META_ACCESS_TOKEN,
    )
