#!/usr/bin/env python
"""Liveness check for the Instagram/Facebook AUTOMATION PROFILE session.

Why this exists (2026-09-02, tulsagays-campus-sources-verify):
    @tcc_pride returned 0 events and 0 happened to be the correct answer that
    week, so nothing looked wrong. It was luck. All three Instagram tiers were
    dead, and an in-week event would have returned 0 too. The web-session tier
    failed because `data/fb_auto_profile`'s cookie jar was COMPLETELY EMPTY
    (0 cookies), and no health check in the repo looked at it, so the outage was
    invisible for an unknown stretch.

    `tools/check_fb_session.py` does NOT cover this. That checks
    `data/fb_session.json`, the Playwright storage_state used for FB page/group
    SCRAPING. This checks the persistent real-Chrome profile that
    `scraper/instagram_web.py` (IG tier 3) and `posting/group_blast.py` (the FB
    group blast) both drive. Two different credentials, and conflating them is
    the trap [[feedback_tulsagays_fb_group_reauth]] warns about.

Reads the profile's cookie sqlite directly. Does NOT launch a browser, so it is
safe inside a scheduled run (scheduled tasks are barred from opening windows)
and cannot fight another process for the profile lock.

Exit codes:  0 = session present   1 = session missing/expired   2 = probe error

Run:  python tools/check_ig_profile_session.py [--json] [--selftest]
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROFILE = REPO / "data" / "fb_auto_profile"
COOKIE_DB = PROFILE / "Default" / "Network" / "Cookies"

# ds_user_id is the cookie scraper/instagram_web.py itself gates on; c_user is
# the Facebook equivalent the group blast needs. Track both, because the
# 2026-09-02 failure took out BOTH at once and only IG was noticed.
REQUIRED = {"instagram": "ds_user_id", "facebook": "c_user"}
FIX = "python tools/ig_profile_login.py"


def probe(cookie_db: Path = COOKIE_DB) -> dict:
    """Return a verdict dict. Never raises."""
    out = {"ok": False, "profile": str(PROFILE), "total_cookies": 0,
           "sites": {}, "detail": "", "fix": FIX}
    if not cookie_db.exists():
        out["detail"] = f"no cookie DB at {cookie_db}"
        return out
    tmp = Path(tempfile.gettempdir()) / f"ig_profile_ck_{os.getpid()}.db"
    try:
        # Copy first: Chrome holds a lock, and we must never write to the real jar.
        shutil.copy(cookie_db, tmp)
        con = sqlite3.connect(str(tmp))
        try:
            out["total_cookies"] = con.execute(
                "SELECT COUNT(*) FROM cookies").fetchone()[0]
            now_us = int((time.time() + 11644473600) * 1_000_000)  # Chrome epoch
            for site, cookie in REQUIRED.items():
                row = con.execute(
                    "SELECT expires_utc FROM cookies "
                    "WHERE host_key LIKE ? AND name = ? "
                    "ORDER BY expires_utc DESC LIMIT 1",
                    (f"%{site}%", cookie)).fetchone()
                if not row:
                    out["sites"][site] = "MISSING"
                elif row[0] and row[0] < now_us:
                    out["sites"][site] = "EXPIRED"
                else:
                    out["sites"][site] = "present"
        finally:
            con.close()
    except Exception as e:                       # noqa: BLE001 - never break a run
        out["detail"] = f"probe error: {e}"
        out["error"] = True
        return out
    finally:
        tmp.unlink(missing_ok=True)

    if out["total_cookies"] == 0:
        out["detail"] = ("cookie jar is EMPTY (0 cookies) - both the Instagram "
                         "web-session tier and the FB group blast are dark")
        return out
    bad = [s for s, v in out["sites"].items() if v != "present"]
    if bad:
        out["detail"] = "no valid session for: " + ", ".join(sorted(bad))
        return out
    out["ok"] = True
    out["detail"] = "instagram + facebook sessions present"
    return out


def _selftest() -> int:
    """Prove BOTH directions against synthetic jars, per house convention."""
    import datetime
    ok = True
    d = Path(tempfile.mkdtemp())

    def build(rows):
        p = d / f"ck{len(list(d.iterdir()))}.db"
        con = sqlite3.connect(str(p))
        con.execute("CREATE TABLE cookies (host_key TEXT, name TEXT, "
                    "expires_utc INTEGER)")
        con.executemany("INSERT INTO cookies VALUES (?,?,?)", rows)
        con.commit()
        con.close()
        return p

    future = int((time.time() + 86400 * 30 + 11644473600) * 1_000_000)
    past = int((time.time() - 86400 + 11644473600) * 1_000_000)

    # 1. The real 2026-09-02 failure: an existing but empty jar.
    v = probe(build([]))
    ok &= (not v["ok"] and "EMPTY" in v["detail"])
    print(f"  empty jar            -> ok={v['ok']} :: {v['detail'][:60]}")

    # 2. Healthy: both sessions present and unexpired.
    v = probe(build([(".instagram.com", "ds_user_id", future),
                     (".facebook.com", "c_user", future)]))
    ok &= v["ok"]
    print(f"  both present         -> ok={v['ok']} :: {v['detail'][:60]}")

    # 3. IG alive, FB gone - the blast breaks while scraping still works.
    v = probe(build([(".instagram.com", "ds_user_id", future),
                     (".instagram.com", "csrftoken", future)]))
    ok &= (not v["ok"] and "facebook" in v["detail"])
    print(f"  facebook missing     -> ok={v['ok']} :: {v['detail'][:60]}")

    # 4. Cookies exist but are expired - must NOT read as healthy.
    v = probe(build([(".instagram.com", "ds_user_id", past),
                     (".facebook.com", "c_user", past)]))
    ok &= (not v["ok"] and "instagram" in v["detail"])
    print(f"  expired              -> ok={v['ok']} :: {v['detail'][:60]}")

    # 5. Missing file is an honest failure, never a pass.
    v = probe(d / "nope.db")
    ok &= (not v["ok"])
    print(f"  no db                -> ok={v['ok']} :: {v['detail'][:60]}")

    shutil.rmtree(d, ignore_errors=True)
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()

    v = probe()
    if a.json:
        print(json.dumps(v, indent=2))
    else:
        state = "OK" if v["ok"] else "BLOCKED"
        print(f"[ig-profile-session] {state}: {v['detail']}")
        print(f"  profile: {v['profile']}")
        print(f"  cookies: {v['total_cookies']} total  sites: {v['sites']}")
        if not v["ok"]:
            print(f"  FIX (William's hands, it is a login): {v['fix']}")
            print("  Affects: instagram_orgs tier 3 (@tcc_pride and every IG-only "
                  "org) AND posting/group_blast.py")
    if v.get("error"):
        return 2
    return 0 if v["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
