"""Graph API collectors for inbound event tips (DMs, comments) -> tip intake.

People send TulsaGays great event tips in Instagram DMs and Facebook messages, and
they also drop them in comments. This module reads those inbound messages through the
OFFICIAL Meta Graph API (William's choice 2026-06-17: the durable, ToS-clean path, not
the private instagrapi API) and hands raw messages to tools/ingest_dm_tips.py, which
parses, drafts site-voice copy, and queues them review-first (never auto-publish).

PERMISSION REALITY (verified live 2026-06-17 against the @tulsagays page token):
  channel            endpoint                                   permission needed              status
  ig_comments        /{ig_id}/media  -> /{media}/comments        instagram_basic (own media)    LIVE NOW (no review)
  fb_page_comments   /{page_id}/posts -> /{post}/comments        pages_read_user_content / PPCA  needs App Review (code 10)
  fb_messages        /{page_id}/conversations (messenger)        pages_messaging                 needs App Review (code 200)
  ig_messages        /{page_id}/conversations (instagram)        instagram_manage_messages       needs App Review (code 230)

Surprise from verification: comments on the page's OWN Instagram media read fine with the
existing instagram_basic scope — so IG comment tips work TODAY. FB page comments, by
contrast, need pages_read_user_content + Page Public Content Access (Meta gates other
users' content on FB harder than on IG). DMs on both platforms need App Review.

Every collector degrades to [] (never crashes) when its permission is missing — the
Graph error is logged as PERMISSION_PENDING so a dry-run clearly shows what is still
gated behind App Review. The moment Meta approves the scopes and the page token is
re-minted, the same code starts returning messages with no edits.

Run standalone (shows what each channel returns right now):
    python scraper/dm_sources.py --dry-run
"""

from __future__ import annotations

import os
import sys
import json
import time
import logging
from pathlib import Path
from typing import Any, Optional

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)

API_BASE = "https://graph.facebook.com/v19.0"
CONFIG_PATH = Path(__file__).resolve().parents[1] / "meta_api_config.json"
STATE_FILE = os.path.join(config.DATA_DIR, "dm_intake_state.json")

# Channels in scope. ig_comments is the only one live on the current token (verified
# 2026-06-17); the other three await Meta App Review.
ALL_CHANNELS = ("ig_messages", "fb_messages", "ig_comments", "fb_page_comments")
LIVE_NOW = ("ig_comments",)

# Graph error subcodes/codes that mean "the token lacks this permission" rather than
# "something broke" — these are EXPECTED until App Review lands, so we log softly.
# 10 = PPCA/pages_read_user_content, 200 = pages_messaging, 230 = instagram_manage_messages.
_PERMISSION_ERROR_CODES = {10, 200, 230, 803, 3, 100}

# How many recent FB posts to scan for new comments each run.
POSTS_TO_SCAN = 15
# Cap the seen-id ledger so the state file can't grow forever.
SEEN_CAP = 5000


# ── token ────────────────────────────────────────────────────────────────────

def _page_token() -> str:
    """Page access token: env var first (the committed value was rotated), then the
    config file if it still holds a real token rather than the moved-to-env placeholder."""
    env = os.environ.get("TULSAGAYS_PAGE_ACCESS_TOKEN", "").strip()
    if env:
        return env
    try:
        with CONFIG_PATH.open(encoding="utf-8") as f:
            cfg = json.load(f)
        tok = (cfg.get("page_access_token") or "").strip()
        if tok and not tok.startswith("MOVED_TO_ENV"):
            return tok
    except (OSError, json.JSONDecodeError):
        pass
    return ""


def load_cfg() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


# ── graph wrapper ──────────────────────────────────────────────────────────────

def _graph_get(path: str, params: dict, token: str) -> tuple[bool, Any, str]:
    """GET a Graph endpoint. Returns (ok, json_or_None, human_error).

    A permission error (the channel awaits App Review) returns ok=False with a
    'PERMISSION_PENDING' prefix so callers can degrade quietly instead of alarming.
    """
    q = dict(params)
    q["access_token"] = token
    try:
        r = requests.get(f"{API_BASE}/{path}", params=q, timeout=20)
    except requests.RequestException as e:
        return False, None, f"NETWORK: {e}"
    try:
        data = r.json()
    except ValueError:
        return False, None, f"NON_JSON ({r.status_code})"
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        code = err.get("code")
        sub = err.get("error_subcode")
        msg = err.get("message", "")
        if code in _PERMISSION_ERROR_CODES or "permission" in msg.lower():
            return False, None, f"PERMISSION_PENDING (code {code}/{sub}): {msg}"
        if code in (190, 460, 463):
            return False, None, f"TOKEN_EXPIRED (code {code}): {msg}"
        return False, None, f"GRAPH_ERROR (code {code}/{sub}): {msg}"
    return True, data, ""


def _msg(channel: str, kind: str, mid: str, text: str, sender: str,
         ts: str, permalink: str = "") -> dict:
    """Normalized raw inbound message — the only shape ingest_dm_tips.py consumes."""
    return {
        "channel": channel,           # ig | fb (maps to add_tip --channel)
        "source_kind": kind,          # ig_messages | fb_messages | ig_comments | fb_page_comments
        "message_id": mid,
        "text": (text or "").strip(),
        "sender": sender or "",
        "ts": ts or "",
        "permalink": permalink or "",
    }


# ── collectors ───────────────────────────────────────────────────────────────

def collect_fb_page_comments(cfg: dict, token: str) -> tuple[list[dict], str]:
    """LIVE NOW (pages_read_engagement). Recent Page-post comments as tips."""
    page_id = cfg["page_id"]
    ok, posts, err = _graph_get(
        f"{page_id}/posts",
        {"fields": "id,permalink_url", "limit": POSTS_TO_SCAN}, token)
    if not ok:
        return [], err
    out: list[dict] = []
    for post in (posts.get("data") or []):
        pid = post.get("id")
        permalink = post.get("permalink_url", "")
        ok2, comments, err2 = _graph_get(
            f"{pid}/comments",
            {"fields": "id,message,from,created_time", "limit": 50}, token)
        if not ok2:
            # A permission gate is channel-wide — bail once instead of logging it
            # per post. Any other error on a single post: skip just that post.
            if err2.startswith(("PERMISSION_PENDING", "TOKEN_EXPIRED")):
                return out, err2
            logger.info("fb comments on %s: %s", pid, err2)
            continue
        for c in (comments.get("data") or []):
            frm = (c.get("from") or {})
            out.append(_msg(
                "fb", "fb_page_comments", c.get("id", ""),
                c.get("message", ""), frm.get("name", ""),
                c.get("created_time", ""), permalink))
    return out, ""


def collect_ig_comments(cfg: dict, token: str) -> tuple[list[dict], str]:
    """Needs instagram_manage_comments (App Review). Comments on @tulsagays media."""
    ig_id = cfg["instagram_business_account_id"]
    ok, media, err = _graph_get(
        f"{ig_id}/media", {"fields": "id,permalink", "limit": POSTS_TO_SCAN}, token)
    if not ok:
        return [], err
    out: list[dict] = []
    for m in (media.get("data") or []):
        mid = m.get("id")
        permalink = m.get("permalink", "")
        ok2, comments, err2 = _graph_get(
            f"{mid}/comments",
            {"fields": "id,text,username,timestamp", "limit": 50}, token)
        if not ok2:
            return out, err2  # likely the permission gate — surface it
        for c in (comments.get("data") or []):
            out.append(_msg(
                "ig", "ig_comments", c.get("id", ""),
                c.get("text", ""), c.get("username", ""),
                c.get("timestamp", ""), permalink))
    return out, ""


def collect_fb_messages(cfg: dict, token: str) -> tuple[list[dict], str]:
    """Needs pages_messaging (App Review). Messenger inbox for the Page."""
    page_id = cfg["page_id"]
    ok, convos, err = _graph_get(
        f"{page_id}/conversations",
        {"platform": "messenger",
         "fields": "messages.limit(10){message,from,created_time,id}",
         "limit": 25}, token)
    if not ok:
        return [], err
    return _messages_from_conversations(convos, "fb", "fb_messages"), ""


def collect_ig_messages(cfg: dict, token: str) -> tuple[list[dict], str]:
    """Needs instagram_manage_messages (App Review). @tulsagays DM inbox."""
    page_id = cfg["page_id"]
    ok, convos, err = _graph_get(
        f"{page_id}/conversations",
        {"platform": "instagram",
         "fields": "messages.limit(10){message,from,created_time,id}",
         "limit": 25}, token)
    if not ok:
        return [], err
    return _messages_from_conversations(convos, "ig", "ig_messages"), ""


def _messages_from_conversations(convos: dict, channel: str, kind: str) -> list[dict]:
    out: list[dict] = []
    for conv in (convos.get("data") or []):
        msgs = ((conv.get("messages") or {}).get("data")) or []
        for m in msgs:
            frm = (m.get("from") or {})
            out.append(_msg(
                channel, kind, m.get("id", ""),
                m.get("message", ""),
                frm.get("username") or frm.get("name") or frm.get("id", ""),
                m.get("created_time", "")))
    return out


_COLLECTORS = {
    "fb_page_comments": collect_fb_page_comments,
    "ig_comments": collect_ig_comments,
    "fb_messages": collect_fb_messages,
    "ig_messages": collect_ig_messages,
}


# ── state (seen ids) ───────────────────────────────────────────────────────────

def _load_state(path: str = STATE_FILE) -> dict:
    if not os.path.exists(path):
        return {"seen_ids": [], "last_run": "", "last_status": {}}
    try:
        with open(path, encoding="utf-8") as f:
            s = json.load(f)
        s.setdefault("seen_ids", [])
        s.setdefault("last_status", {})
        return s
    except (OSError, json.JSONDecodeError):
        return {"seen_ids": [], "last_run": "", "last_status": {}}


def _save_state(state: dict, path: str = STATE_FILE) -> None:
    state["seen_ids"] = list(state.get("seen_ids", []))[-SEEN_CAP:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ── public entry ───────────────────────────────────────────────────────────────

def collect_all(channels: Optional[list[str]] = None, token: Optional[str] = None,
                cfg: Optional[dict] = None, state: Optional[dict] = None
                ) -> tuple[list[dict], dict]:
    """Run the requested collectors and return (new_messages, status_by_channel).

    new_messages excludes anything whose message_id is already in state['seen_ids'].
    Does NOT mutate or save state — the orchestrator decides when to commit seen-ids
    (only after a message is successfully queued), so a crash never loses a tip.
    """
    channels = channels or list(ALL_CHANNELS)
    token = token if token is not None else _page_token()
    cfg = cfg or load_cfg()
    state = state if state is not None else _load_state()
    seen = set(state.get("seen_ids", []))
    status: dict[str, str] = {}
    new: list[dict] = []

    if not token:
        for ch in channels:
            status[ch] = "NO_TOKEN (set TULSAGAYS_PAGE_ACCESS_TOKEN)"
        return [], status

    for ch in channels:
        fn = _COLLECTORS.get(ch)
        if not fn:
            status[ch] = "UNKNOWN_CHANNEL"
            continue
        msgs, err = fn(cfg, token)
        if err:
            status[ch] = err
        fresh = [m for m in msgs if m.get("message_id") and m["message_id"] not in seen]
        if not err:
            status[ch] = f"ok ({len(fresh)} new / {len(msgs)} seen-or-new)"
        new.extend(fresh)
    return new, status


def _cli(argv=None):
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Inspect inbound DM/comment collectors.")
    ap.add_argument("--dry-run", action="store_true",
                    help="collect and print, touch no state")
    ap.add_argument("--channels", nargs="*", default=None,
                    help=f"subset of {ALL_CHANNELS}")
    args = ap.parse_args(argv)
    msgs, status = collect_all(channels=args.channels)
    print("Channel status:")
    for ch, st in status.items():
        live = " [LIVE]" if ch in LIVE_NOW else " [awaits App Review]"
        print(f"  {ch}{live}: {st}")
    print(f"\n{len(msgs)} new message(s):")
    for m in msgs[:25]:
        print(f"  [{m['source_kind']}] {m['sender']}: {m['text'][:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
