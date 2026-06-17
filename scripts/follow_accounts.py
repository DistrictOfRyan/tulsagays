"""
TulsaGays follower-growth ACTION: follow a small, curated set of accounts via the
@tulsagays instagrapi session. Human-paced (jitter between follows). Exactly 5/run.

Usage: python scripts/follow_accounts.py user1 user2 user3 ...
Prints a JSON result per username; never raises on a single failure.
"""
import json, sys, time, random
from pathlib import Path

SETTINGS_FILE = Path.home() / ".credentials" / "ig_settings_tulsagays.json"


def client():
    from instagrapi import Client
    cl = Client()
    cl.delay_range = [3, 7]  # built-in human-like pacing between API calls
    cl.load_settings(str(SETTINGS_FILE))
    cl.get_timeline_feed()  # validate session
    return cl


def main(usernames):
    cl = client()
    print("[ok] session valid", file=sys.stderr)
    results = []
    for i, un in enumerate(usernames):
        rec = {"username": un}
        try:
            uid = cl.user_id_from_username(un)
            ok = cl.user_follow(uid)
            rec["user_id"] = str(uid)
            rec["followed"] = bool(ok)
            rec["status"] = "followed" if ok else "follow_returned_false"
        except Exception as e:
            rec["followed"] = False
            rec["status"] = f"error:{type(e).__name__}"
            rec["detail"] = str(e)[:200]
        results.append(rec)
        print(f"  @{un}: {rec['status']}", file=sys.stderr)
        if i < len(usernames) - 1:
            wait = random.uniform(35, 80)  # space out follows
            print(f"    sleeping {wait:.0f}s before next follow", file=sys.stderr)
            time.sleep(wait)
    Path("scripts/follow_results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("need usernames", file=sys.stderr); sys.exit(2)
    main(sys.argv[1:])
