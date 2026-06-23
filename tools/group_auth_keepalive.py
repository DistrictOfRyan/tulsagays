"""
Daily keepalive for the Facebook group-blast browser session.

Run every day. It loads the saved session headlessly, touches Facebook, and
re-saves the rotated cookies so FB does not expire an idle login. This is what
keeps the Monday group blast working WITHOUT a weekly manual re-login.

If the session is genuinely dead (FB logged it out / password change), it can't
self-heal — only a human login can. In that case it:
  - writes data/GROUP_AUTH_DEAD.flag (group_blast + Monday pre-check read this)
  - appends a one-command re-auth note to pending-william-actions.md, which the
    daily Telegram pusher surfaces to William with lead time BEFORE Monday.

Exit 0 = session healthy (refreshed). Exit 3 = dead (human re-auth needed).
"""
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.group_session import refresh, AUTH_PATH  # noqa: E402

DEAD_FLAG = ROOT / "data" / "GROUP_AUTH_DEAD.flag"
PENDING = Path.home() / ".claude" / "pending-william-actions.md"

REAUTH_NOTE = """
## [{ts}] TulsaGays FB group login expired - 2-min re-auth needed
- The saved Facebook session for the group blast went dead (FB logged it out). The daily keepalive cannot self-heal a true logout.
- Until you re-auth, the Monday carousel will post to FB page + Instagram + website automatically, but NOT to the 11 FB groups.
- FIX (2 min, any time before Monday): run `cd C:\\Users\\willi\\tulsagays && python tools/fb_profile_login.py` and log into Facebook in the REAL Chrome window that opens, then close it. (Use fb_profile_login.py, NOT capture_group_auth.py — the latter opens Chrome-for-Testing, which Google blocks at login.)
- NOTE: FB force-logs-out this automation profile every ~2 weeks regardless of the keepalive. This re-auth is expected periodically; it is not a one-time "permanent" fix.
"""


def _flag_dead():
    try:
        DEAD_FLAG.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    except Exception:
        pass
    # Append a re-auth note to pending actions (deduped: skip if a live note exists today)
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        today = datetime.now().strftime("%Y-%m-%d")
        existing = PENDING.read_text(encoding="utf-8") if PENDING.exists() else ""
        if f"TulsaGays FB group login expired" in existing and today in existing:
            return  # already flagged today; don't spam
        with open(PENDING, "a", encoding="utf-8") as f:
            f.write(REAUTH_NOTE.format(ts=ts))
    except Exception as e:
        print(f"[keepalive] could not write pending note: {e}")


def main():
    if not AUTH_PATH.exists():
        print("[keepalive] no auth file yet - run capture_group_auth.py once.")
        _flag_dead()
        return 3
    ok = refresh()
    if ok:
        # Session healthy: clear any stale dead-flag.
        if DEAD_FLAG.exists():
            try:
                DEAD_FLAG.unlink()
            except Exception:
                pass
        print(f"[keepalive] session healthy, cookies refreshed ({datetime.now():%Y-%m-%d %H:%M})")
        return 0
    print("[keepalive] session DEAD - human re-auth required")
    _flag_dead()
    return 3


if __name__ == "__main__":
    sys.exit(main())
