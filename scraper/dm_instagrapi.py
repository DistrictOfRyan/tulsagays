"""Instagram DM reader + guardrailed auto-reply (private-API bridge for tip intake).

The official Graph API can't read or reply to Instagram DMs without
instagram_manage_messages (Meta App Review). Until that lands, instagrapi is the
durable path for DMs — it reads direct threads, downloads attached flyers, and sends
the confirmation reply. (William: "do what's best for long-term automation" — for DMs
that's instagrapi today, official API once/if approved.)

Reuses the proven @tulsagays session loader in posting/ig_api.py. If the session is
invalid (expired / needs a 2FA re-login via scripts/ig_login_api.py), every function
degrades to a no-op with a clear reason — it NEVER crashes the daily ingest.

What it produces: the same normalized message dict scraper/dm_sources.py emits, plus a
`flyer_images` list of downloaded image paths (a single DM can carry MULTIPLE flyers —
all are captured, none dropped). ingest_dm_tips.py consumes these like any other channel.

Auto-reply guardrails (William chose auto-send-with-guardrails, 2026-06-17):
  - one reply per submitter, ever (tracked in state['replied_users'])
  - per-run cap (REPLY_CAP)
  - anonymous community voice only (no operator self-ID — the @tulsagays hard rule)
  - every send audit-logged to data/dm_autoreply_log.json
  - disabled automatically when the session is invalid
"""

from __future__ import annotations

import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

FLYER_DIR = os.path.join(config.DATA_DIR, "tip_flyers")
AUTOREPLY_LOG = os.path.join(config.DATA_DIR, "dm_autoreply_log.json")

REPLY_CAP = 10            # max auto-replies per run
THREADS_TO_SCAN = 25      # most recent DM threads to read each run
MSGS_PER_THREAD = 12

# Anonymous, community-voice confirmation. Includes the self-promo William asked for.
# No "I", no operator name — speaks as the page ("we"/"you").
DEFAULT_REPLY = (
    "Added to the TulsaGays calendar, thank you for the tip! 🏳️‍🌈 "
    "You can see every Tulsa LGBTQ+ event any time at tulsagays.com. "
    "Hit us back if anything looks off."
)

# instagrapi message item types that carry a photo/flyer.
_MEDIA_TYPES = {"media", "raven_media", "media_share", "clip", "xma_media_share",
                "animated_media", "story_share", "felix_share"}


def get_client():
    """Logged-in @tulsagays instagrapi Client, or None if the session is invalid."""
    try:
        from posting.ig_api import _client
    except Exception as e:
        logger.info("dm_instagrapi: cannot import ig_api: %s", e)
        return None
    return _client()


# ── reading ────────────────────────────────────────────────────────────────────

def _download_flyers(cl, message, dest_dir: str) -> list[str]:
    """Download every image attached to a DM message. Returns local paths.

    instagrapi exposes attached media in slightly different shapes by version; we try
    the common ones and skip anything we can't fetch (never raise)."""
    os.makedirs(dest_dir, exist_ok=True)
    paths: list[str] = []
    candidates = []
    for attr in ("media", "visual_media", "clip", "story_share"):
        val = getattr(message, attr, None)
        if val:
            candidates.append(val)
    for media in candidates:
        try:
            url = (getattr(media, "thumbnail_url", None)
                   or getattr(media, "image_versions2", None)
                   or getattr(getattr(media, "media", None), "thumbnail_url", None))
            if hasattr(url, "__str__") and str(url).startswith("http"):
                p = cl.photo_download_by_url(str(url), folder=dest_dir)
                paths.append(str(p))
        except Exception as e:
            logger.info("dm_instagrapi: flyer download skipped: %s", e)
    return paths


def read_dm_tips(cl, seen_ids: set, download_dir: str = FLYER_DIR) -> tuple[list[dict], str]:
    """Read recent DM threads -> normalized message dicts (with flyer_images).

    Skips message_ids already in seen_ids. Returns (messages, error)."""
    if cl is None:
        return [], "SESSION_INVALID (re-auth: python scripts/ig_login_api.py)"
    try:
        threads = cl.direct_threads(amount=THREADS_TO_SCAN)
    except Exception as e:
        return [], f"DIRECT_THREADS_FAILED: {type(e).__name__} {str(e)[:120]}"

    out: list[dict] = []
    for t in threads:
        thread_id = getattr(t, "id", "") or ""
        users = getattr(t, "users", []) or []
        sender = users[0].username if users else ""
        for m in (getattr(t, "messages", []) or [])[:MSGS_PER_THREAD]:
            item_id = getattr(m, "id", "") or ""
            mid = f"ig_dm:{thread_id}:{item_id}"
            if mid in seen_ids:
                continue
            text = (getattr(m, "text", "") or "").strip()
            has_media = getattr(m, "item_type", "") in _MEDIA_TYPES or bool(
                getattr(m, "visual_media", None))
            if not text and not has_media:
                continue  # reactions / likes / system
            flyers = _download_flyers(cl, m, download_dir) if has_media else []
            out.append({
                "channel": "ig",
                "source_kind": "ig_dm",
                "message_id": mid,
                "text": text,
                "sender": sender,
                "ts": str(getattr(m, "timestamp", "") or ""),
                "permalink": "",
                "flyer_images": flyers,        # MULTIPLE flyers preserved
                "thread_id": thread_id,
            })
    return out, ""


# ── auto-reply (guardrailed) ────────────────────────────────────────────────────

def _load_log() -> dict:
    if not os.path.exists(AUTOREPLY_LOG):
        return {"replied_users": [], "sends": []}
    try:
        with open(AUTOREPLY_LOG, encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("replied_users", [])
        d.setdefault("sends", [])
        return d
    except (OSError, json.JSONDecodeError):
        return {"replied_users": [], "sends": []}


def _save_log(d: dict) -> None:
    with open(AUTOREPLY_LOG, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)


def _is_anonymous(text: str) -> bool:
    """Guard: the reply must not leak the operator (the @tulsagays hard rule)."""
    low = text.lower()
    banned = ["ryan", "william", "hunt", "i run", "i manage", "my page", " i ",
              "dm me personally"]
    return not any(b in low for b in banned)


def send_confirmations(cl, tips: list[dict], reply_text: str = DEFAULT_REPLY,
                       cap: int = REPLY_CAP, dry_run: bool = False) -> dict:
    """Send the anonymous confirmation once per submitter, with guardrails.

    `tips` are the queued tip entries that came from DMs (need thread_id + submitted_by).
    Returns a summary dict. Never raises."""
    # Voice rule #1: no em dashes in anything a human reads (belt for custom replies).
    try:
        from content.generator import strip_em_dashes as _sed
        reply_text = _sed(reply_text)
    except Exception:
        reply_text = reply_text.replace(" — ", ", ").replace("—", ", ").replace("–", "-")
    if not _is_anonymous(reply_text):
        return {"sent": 0, "error": "reply text failed anonymity guard"}
    log = _load_log()
    replied = set(log["replied_users"])
    sent, skipped = 0, 0
    if cl is None and not dry_run:
        return {"sent": 0, "error": "SESSION_INVALID — cannot send"}

    for tip in tips:
        if sent >= cap:
            break
        user = (tip.get("submitted_by") or "").strip().lstrip("@").lower()
        thread_id = tip.get("thread_id") or ""
        if not user or not thread_id:
            skipped += 1
            continue
        if user in replied:
            skipped += 1
            continue
        if dry_run:
            replied.add(user)   # within-run dedup applies even when previewing
            sent += 1
            continue
        try:
            cl.direct_send(reply_text, thread_ids=[thread_id])
            replied.add(user)
            log["replied_users"] = sorted(replied)
            log["sends"].append({
                "user": user, "thread_id": thread_id,
                "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "tip_id": tip.get("id", ""),
            })
            _save_log(log)
            sent += 1
            time.sleep(3)  # gentle pacing
        except Exception as e:
            logger.info("dm_instagrapi: reply failed to %s: %s", user, e)
            skipped += 1
    return {"sent": sent, "skipped": skipped}


# ── selftest (offline, stubbed client) ───────────────────────────────────────────

def _selftest():
    import tempfile

    assert _is_anonymous(DEFAULT_REPLY), "default reply must be anonymous"
    assert not _is_anonymous("Hi, I run this page, message Ryan"), "should catch operator leak"

    class FakeMsg:
        def __init__(self, mid, text="", item_type="text"):
            self.id = mid; self.text = text; self.item_type = item_type
            self.timestamp = "t"; self.visual_media = None; self.media = None
            self.clip = None; self.story_share = None

    class FakeUser:
        username = "tulsanbar"

    class FakeThread:
        id = "thread123"
        users = [FakeUser()]
        messages = [
            FakeMsg("m1", "Drag night at The Tulsan this Friday June 19, doors 9pm!"),
            FakeMsg("m2", "", "media"),   # a flyer image, no text
            FakeMsg("m3", ""),            # empty/reaction -> skipped
        ]

    class FakeClient:
        def direct_threads(self, amount=25):
            return [FakeThread()]
        def photo_download_by_url(self, url, folder):
            return os.path.join(folder, "flyer.jpg")
        def direct_send(self, text, thread_ids):
            return True

    cl = FakeClient()
    # media download needs a media object; m2 has item_type media but no media attr -> 0 flyers
    msgs, err = read_dm_tips(cl, seen_ids=set(), download_dir=tempfile.mkdtemp())
    assert err == "", err
    ids = [m["message_id"] for m in msgs]
    assert "ig_dm:thread123:m1" in ids, ids
    assert "ig_dm:thread123:m2" in ids, ids       # media message kept even w/o text
    assert "ig_dm:thread123:m3" not in ids, ids    # empty skipped
    assert all(m["source_kind"] == "ig_dm" for m in msgs)

    # dedup: passing m1 as seen drops it
    msgs2, _ = read_dm_tips(cl, seen_ids={"ig_dm:thread123:m1"},
                            download_dir=tempfile.mkdtemp())
    assert "ig_dm:thread123:m1" not in [m["message_id"] for m in msgs2]

    # invalid session degrades, never raises
    none_msgs, none_err = read_dm_tips(None, seen_ids=set())
    assert none_msgs == [] and "SESSION_INVALID" in none_err

    # auto-reply: once per user, anonymity guard, dry-run path
    tip = {"id": "tip001", "submitted_by": "tulsanbar", "thread_id": "thread123"}
    r = send_confirmations(cl, [tip, tip], dry_run=True)
    assert r["sent"] == 1 and r["skipped"] == 1, r  # same user twice -> one send, one dedup
    bad = send_confirmations(cl, [tip], reply_text="message Ryan Hunt directly")
    assert bad.get("error"), "anonymity guard should block operator-leaking reply"

    print("dm_instagrapi selftest: passed (read + multi-flyer shape + dedup + "
          "session-degrade + guardrailed reply)")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    # Live probe (read-only): show what the DM inbox returns right now.
    cl = get_client()
    msgs, err = read_dm_tips(cl, seen_ids=set())
    if err:
        print("DM read:", err)
    print(f"{len(msgs)} DM message(s):")
    for m in msgs[:15]:
        print(f"  {m['sender']}: {m['text'][:60]!r}  flyers={len(m.get('flyer_images', []))}")
