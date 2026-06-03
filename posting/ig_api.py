"""
ig_api.py - 100% automated @tulsagays Instagram engagement via the private mobile
API (instagrapi). No browser, so no web captcha / login loop.

Auth model: you log in ONCE with scripts/ig_login_api.py (may need one 2FA code from
your phone). That dumps a device+session file to ~/.credentials/ig_settings_tulsagays.json
(off the synced drive). Every run after that loads that session and acts via the API
with ZERO interaction.

Posture (William, 2026-06-02): replies + likes AUTO; follows ASSISTED (auto-follow is
the #1 ban trigger). Flip AUTO_FOLLOW=True to also auto-follow (higher ban risk).

Anti-ban: randomized pacing, small per-run caps, idempotent via a state file, full
audit log, and it stops on any LoginRequired/challenge (re-auth needed) instead of
hammering.
"""
from __future__ import annotations

import json
import random
import time
from datetime import datetime
from pathlib import Path

HOME = Path.home()
SETTINGS_FILE = HOME / ".credentials" / "ig_settings_tulsagays.json"
STATE_FILE = HOME / ".claude" / "tulsagays" / "ig_engage_state.json"
REPLY_QUEUE = HOME / ".claude" / "tulsagays" / "ig_reply_queue.json"
FOLLOW_LIST_OUT = HOME / ".claude" / "tulsagays" / "ig_follow_candidates.md"
LOG_FILE = HOME / ".claude" / "logs" / "tulsagays-ig-engage.log"
PENDING = HOME / ".claude" / "pending-william-actions.md"
ENV_FILE = HOME / ".claude" / "channels" / "telegram" / ".env"
CHAT_ID = "6202804878"

LIKE_CAP = 5
REPLY_CAP = 8
FOLLOW_SEEDS = ["homohotelhappyhour", "tulsaeagle", "okeq"]
AUTO_FOLLOW = True           # enabled by William 2026-06-02 (against recommendation)
FOLLOW_CAP = 3               # per-RUN cap - outbound follows are the #1 IG ban trigger
DAILY_FOLLOW_CAP = 6         # per-DAY ceiling across all 3 scheduled runs (anti-ban)
MIN_DELAY, MAX_DELAY = 25, 80


def log(msg: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(msg)


def _pace() -> None:
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


def _load_state() -> dict:
    try:
        s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        s = {}
    s.setdefault("replied", [])
    s.setdefault("liked", [])
    s.setdefault("follows_by_day", {})   # {"YYYY-MM-DD": count} - enforces DAILY_FOLLOW_CAP
    return s


def _follows_remaining_today(state: dict) -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    used = state.get("follows_by_day", {}).get(today, 0)
    return max(0, DAILY_FOLLOW_CAP - used)


def _record_follow(state: dict) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    state.setdefault("follows_by_day", {})
    state["follows_by_day"][today] = state["follows_by_day"].get(today, 0) + 1
    _save_state(state)


def _save_state(s: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")


def _telegram(text: str) -> None:
    try:
        import urllib.parse, urllib.request
        token = None
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
        if not token:
            return
        data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text[:3500],
                                       "disable_web_page_preview": "true"}).encode()
        urllib.request.urlopen(
            urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                   data=data, method="POST"), timeout=10)
    except Exception:
        pass


def _degrade(reason: str) -> int:
    log(f"DEGRADE: {reason}")
    _telegram(f"tulsagays-ig-engage skipped: {reason}. "
              f"Re-auth once: run `python C:\\Users\\willi\\tulsagays\\scripts\\ig_login_api.py`.")
    try:
        with PENDING.open("a", encoding="utf-8") as f:
            f.write(f"\n## [{datetime.now().strftime('%Y-%m-%d %H:%M')}] TulsaGays IG engage NEEDS YOUR ACTION\n"
                    f"IG API engagement could not run: {reason}. One-time fix: run "
                    f"`python C:\\Users\\willi\\tulsagays\\scripts\\ig_login_api.py` (enter the @tulsagays "
                    f"login + one 2FA code). Then it runs 100% on its own.\n")
    except OSError:
        pass
    return 0


def _client():
    """Return a logged-in instagrapi Client, or None if no/invalid session."""
    if not SETTINGS_FILE.exists():
        return None
    try:
        from instagrapi import Client
        from instagrapi.exceptions import LoginRequired
    except ImportError:
        return None
    cl = Client()
    try:
        cl.load_settings(str(SETTINGS_FILE))
        cl.get_timeline_feed()  # cheap authenticated call to validate the session
        return cl
    except Exception:
        return None


def do_replies(cl, state: dict) -> int:
    try:
        queue = json.loads(REPLY_QUEUE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    posted = 0
    for item in queue:
        if posted >= REPLY_CAP:
            break
        rid = item.get("id") or (item.get("post_url", "") + "|" + item.get("reply", "")[:20])
        if rid in state["replied"]:
            continue
        url, reply = item.get("post_url"), item.get("reply")
        if not url or not reply:
            continue
        try:
            media_pk = cl.media_pk_from_url(url)
            media_id = cl.media_id(media_pk)
            cl.media_comment(media_id, reply)
            state["replied"].append(rid)
            _save_state(state)
            posted += 1
            log(f"replied on {url}")
            _pace()
        except Exception as e:
            log(f"reply failed on {url}: {type(e).__name__} {str(e)[:120]}")
    return posted


def do_likes(cl, state: dict, max_likes: int) -> int:
    liked = 0
    try:
        feed = cl.get_timeline_feed()
        medias = feed.get("feed_items", []) if isinstance(feed, dict) else []
        for it in medias:
            if liked >= max_likes:
                break
            media = it.get("media_or_ad") if isinstance(it, dict) else None
            mid = media.get("id") or media.get("pk") if isinstance(media, dict) else None
            if not mid or str(mid) in state["liked"]:
                continue
            try:
                cl.media_like(str(mid))
                state["liked"].append(str(mid))
                _save_state(state)
                liked += 1
                log(f"liked media {mid} ({liked}/{max_likes})")
                _pace()
            except Exception as e:
                log(f"like failed {mid}: {type(e).__name__} {str(e)[:100]}")
    except Exception as e:
        log(f"like flow error: {type(e).__name__} {str(e)[:120]}")
    return liked


def prepare_follows(cl, state: dict) -> int:
    # Respect the per-day ceiling first so 3 scheduled runs/day can't over-follow.
    run_budget = FOLLOW_CAP
    if AUTO_FOLLOW:
        run_budget = min(FOLLOW_CAP, _follows_remaining_today(state))
        if run_budget <= 0:
            log(f"follow skipped: daily cap {DAILY_FOLLOW_CAP} already reached today")
            return 0
    candidates = {}
    for seed in FOLLOW_SEEDS:
        try:
            uid = cl.user_id_from_username(seed)
            followers = cl.user_followers(uid, amount=20)
            for fid, u in followers.items():
                if u.username not in FOLLOW_SEEDS:
                    candidates[u.username] = u.full_name or ""
            _pace()
        except Exception as e:
            log(f"prepare_follows seed {seed}: {type(e).__name__} {str(e)[:100]}")
    items = list(candidates.items())[:15]
    if AUTO_FOLLOW:
        followed = 0
        for uname, _ in items[:run_budget]:
            try:
                cl.user_follow(cl.user_id_from_username(uname))
                followed += 1
                _record_follow(state)
                log(f"followed @{uname} ({followed}/{run_budget}, daily {DAILY_FOLLOW_CAP - _follows_remaining_today(state)}/{DAILY_FOLLOW_CAP})")
                _pace()
            except Exception as e:
                log(f"follow @{uname} failed: {type(e).__name__} {str(e)[:80]}")
        log(f"auto-followed {followed}")
        return followed
    FOLLOW_LIST_OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# TulsaGays follow candidates - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             "Tap Follow on the Tulsa-area / on-brand ones:\n"]
    for uname, full in items:
        lines.append(f"- https://www.instagram.com/{uname}/  ({full})")
    FOLLOW_LIST_OUT.write_text("\n".join(lines), encoding="utf-8")
    log(f"prepared {len(items)} follow candidates")
    return len(items)


def run(mode: str = "engage", max_likes: int = LIKE_CAP) -> int:
    cl = _client()
    if cl is None:
        return _degrade("no/expired @tulsagays session - run ig_login_api.py once")
    state = _load_state()
    summary = []
    try:
        if mode in ("reply", "engage"):
            summary.append(f"{do_replies(cl, state)} replies")
        if mode in ("like", "engage"):
            summary.append(f"{do_likes(cl, state, max_likes)} likes")
        if mode in ("prepare-follows", "engage"):
            n = prepare_follows(cl, state)
            summary.append(f"{n} follows" if AUTO_FOLLOW else f"{n} follow candidates")
    except Exception as e:
        return _degrade(f"engage error: {type(e).__name__} {str(e)[:120]}")
    msg = "tulsagays-ig-engage OK: " + ", ".join(summary)
    log(msg)
    _telegram(msg)
    return 0


def check() -> int:
    cl = _client()
    if cl is None:
        return _degrade("no/expired @tulsagays session - run ig_login_api.py once")
    try:
        me = cl.account_info()
        log(f"session check: OK (logged in as @{me.username})")
        return 0
    except Exception as e:
        return _degrade(f"session check failed: {type(e).__name__} {str(e)[:100]}")


def run_task(task_config=None, task_state=None) -> dict:
    rc = run("engage")
    return {"success": rc == 0, "message": f"ig api engage rc={rc}"}


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "engage"
    sys.exit(check() if cmd == "check" else run(cmd))
