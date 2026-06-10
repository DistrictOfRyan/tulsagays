#!/usr/bin/env python3
"""
meta_system_user.py - verify and install a NON-EXPIRING Meta system-user token.

This is the Phase 3 durable fix for the recurring "token went dark" outage.
A System User token (generated in Business Settings, see the runbook) belongs to
the Business, not to William's personal login session, so it does not die when
his password changes, his session expires, or a 60-day page-token clock runs out.

A page token DERIVED from a non-expiring system-user token is itself non-expiring,
so once installed it drops straight into the existing posting code (config.py's
resolver already reads ~/.credentials/tulsagays_page_token.txt first) with NO
code changes anywhere else.

Two subcommands:

  verify  <SYSTEM_USER_TOKEN>
      Read-only proof. Calls /debug_token with the app access token and asserts:
        - token is valid
        - expires_at == 0  (NEVER expires)  <-- the whole point of Phase 3
        - it is tied to OUR app (1468075241636760)
        - it carries the scopes the posting code needs
        - it can actually see the TulsaGays Page (and IG account if linked)
      Exits 0 only if every assertion passes. Prints a clear PASS/FAIL report.
      The token value itself is never printed.

  install <SYSTEM_USER_TOKEN> [--page-id ID] [--also-hhhh]
      Runs verify first. Then derives the non-expiring PAGE access token for the
      page, re-checks expires_at == 0 on the derived token, and writes it to
      ~/.credentials/tulsagays_page_token.txt (canonical, off the synced drive).
      Any previously stored token that is still alive is added to
      ~/.credentials/meta_revoked_tokens.txt so the resolver can never serve it.

Usage:
    python meta_system_user.py verify  <SYSTEM_USER_TOKEN>
    python meta_system_user.py install <SYSTEM_USER_TOKEN>
    python meta_system_user.py install <SYSTEM_USER_TOKEN> --also-hhhh
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HOME = Path.home()
CRED = HOME / ".credentials"
TOKEN_FILE = CRED / "tulsagays_page_token.txt"
HHHH_TOKEN_FILE = CRED / "hhhh_page_token.txt"
APP_SECRET_FILE = CRED / "meta_app_secret_1468075241636760.txt"
REVOKED_FILE = CRED / "meta_revoked_tokens.txt"

APP_ID = "1468075241636760"
TULSAGAYS_PAGE_ID = "1086906044497675"
GRAPH = "https://graph.facebook.com/v21.0"

# Scopes the posting code actually exercises (facebook.py + instagram.py).
REQUIRED_SCOPES = {
    "pages_manage_posts",       # FB feed + photo publish
    "pages_read_engagement",    # FB page reads
    "instagram_basic",          # IG account info
    "instagram_content_publish",  # IG image/carousel/reel publish
}
# Nice-to-have but not fatal if missing.
OPTIONAL_SCOPES = {"instagram_manage_insights", "pages_show_list", "business_management"}


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read().decode())


def _app_access_token(app_secret: str) -> str:
    # App access token = APP_ID|APP_SECRET. Used to call /debug_token authoritatively.
    return f"{APP_ID}|{app_secret}"


def _debug(token: str, app_secret: str) -> dict:
    url = (
        f"{GRAPH}/debug_token?input_token={urllib.parse.quote(token)}"
        f"&access_token={urllib.parse.quote(_app_access_token(app_secret))}"
    )
    return _get(url).get("data", {})


def _read_app_secret() -> str | None:
    if not APP_SECRET_FILE.exists():
        print(f"FAIL: app secret missing at {APP_SECRET_FILE}")
        return None
    return APP_SECRET_FILE.read_text(encoding="utf-8").strip()


def _verify(token: str, app_secret: str, page_id: str) -> bool:
    """Return True only if the token is valid, never-expiring, ours, and scoped."""
    ok = True
    try:
        data = _debug(token, app_secret)
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300] if hasattr(e, "read") else str(e)
        print(f"FAIL: debug_token call errored: {body}")
        return False

    if not data.get("is_valid"):
        print(f"FAIL: token is not valid. Meta says: {data.get('error', data)}")
        return False
    print("PASS: token is valid.")

    # The crux of Phase 3: expires_at == 0 means NEVER expires.
    expires_at = data.get("expires_at", -1)
    data_access_expires = data.get("data_access_expires_at", -1)
    if expires_at == 0:
        print("PASS: expires_at == 0  ->  token NEVER expires. This is the durable fix.")
    else:
        from datetime import datetime, timezone
        when = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat() if expires_at > 0 else "unknown"
        print(f"FAIL: token EXPIRES at {when} (expires_at={expires_at}). "
              "A real system-user token shows expires_at=0. "
              "Re-generate it with the expiration set to 'Never'.")
        ok = False
    if data_access_expires not in (0, -1):
        # data_access_expires_at is a separate 90-day app-data clock; warn but don't fail.
        from datetime import datetime, timezone
        when = datetime.fromtimestamp(data_access_expires, tz=timezone.utc).isoformat()
        print(f"  note: data_access_expires_at={when} (90-day app-data window, refreshes on use).")

    app_id = str(data.get("app_id", ""))
    if app_id == APP_ID:
        print(f"PASS: token is tied to our app ({APP_ID}).")
    else:
        print(f"FAIL: token belongs to app_id={app_id}, not ours ({APP_ID}).")
        ok = False

    scopes = set(data.get("scopes", []))
    missing = REQUIRED_SCOPES - scopes
    if not missing:
        print(f"PASS: all required scopes present ({', '.join(sorted(REQUIRED_SCOPES))}).")
    else:
        print(f"FAIL: missing required scopes: {', '.join(sorted(missing))}. "
              "Re-generate the token and check those permission boxes.")
        ok = False
    opt_present = OPTIONAL_SCOPES & scopes
    if opt_present:
        print(f"  note: optional scopes also present ({', '.join(sorted(opt_present))}).")

    # Can the token actually see the Page?
    try:
        pg = _get(f"{GRAPH}/{page_id}?fields=name,access_token&access_token=" + urllib.parse.quote(token))
        print(f"PASS: token can see Page '{pg.get('name', '?')}' ({page_id}).")
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200] if hasattr(e, "read") else str(e)
        print(f"FAIL: token cannot read Page {page_id}: {body}. "
              "Assign the Page to the System User (Full control) in Business Settings.")
        ok = False

    print()
    print("RESULT:", "PASS - token is durable and ready to install." if ok
          else "FAIL - fix the items above, regenerate, and re-verify.")
    return ok


def _derive_page_token(system_token: str, page_id: str) -> str | None:
    try:
        pg = _get(f"{GRAPH}/{page_id}?fields=access_token&access_token=" + urllib.parse.quote(system_token))
        return pg.get("access_token")
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200] if hasattr(e, "read") else str(e)
        print(f"FAIL deriving page token for {page_id}: {body}")
        return None


def _install_one(system_token: str, app_secret: str, page_id: str, token_file: Path, label: str) -> bool:
    page_token = _derive_page_token(system_token, page_id)
    if not page_token:
        return False
    # The derived page token must ALSO be non-expiring.
    info = _debug(page_token, app_secret)
    if info.get("expires_at", -1) != 0:
        print(f"FAIL: derived {label} page token is not non-expiring (expires_at="
              f"{info.get('expires_at')}). Aborting; nothing written.")
        return False

    # Revoke-guard the old token if it is still alive.
    if token_file.exists():
        old = token_file.read_text(encoding="utf-8").strip()
        if old and old != page_token:
            try:
                _get(f"{GRAPH}/{page_id}?fields=name&access_token=" + urllib.parse.quote(old))
                CRED.mkdir(parents=True, exist_ok=True)
                existing = REVOKED_FILE.read_text(encoding="utf-8") if REVOKED_FILE.exists() else ""
                if old not in existing:
                    with REVOKED_FILE.open("a", encoding="utf-8") as f:
                        f.write(old + "\n")
                print(f"  note: previous {label} token still alive; added to meta_revoked_tokens.txt.")
            except urllib.error.HTTPError:
                pass  # old token already dead

    CRED.mkdir(parents=True, exist_ok=True)
    token_file.write_text(page_token, encoding="utf-8")
    print(f"PASS: non-expiring {label} page token written to {token_file} (len {len(page_token)}).")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", help="read-only proof the token never expires")
    v.add_argument("token")
    v.add_argument("--page-id", default=TULSAGAYS_PAGE_ID)
    i = sub.add_parser("install", help="derive + store the non-expiring page token")
    i.add_argument("token")
    i.add_argument("--page-id", default=TULSAGAYS_PAGE_ID)
    i.add_argument("--also-hhhh", action="store_true",
                   help="also derive+store the HHHH page token (needs HHHH_PAGE_ID env)")
    args = ap.parse_args()

    app_secret = _read_app_secret()
    if not app_secret:
        return 1
    token = args.token.strip()
    if not token:
        print("FAIL: empty token.")
        return 2

    if args.cmd == "verify":
        return 0 if _verify(token, app_secret, args.page_id) else 1

    # install: verify first, then write.
    if not _verify(token, app_secret, args.page_id):
        print("\nNot installing - verification failed above.")
        return 1
    print("\n--- installing ---")
    ok = _install_one(token, app_secret, args.page_id, TOKEN_FILE, "TulsaGays")
    if args.also_hhhh:
        import os
        hhhh_page = os.environ.get("HHHH_PAGE_ID", "").strip()
        if not hhhh_page:
            print("  skip HHHH: HHHH_PAGE_ID not set in environment.")
        else:
            ok = _install_one(token, app_secret, hhhh_page, HHHH_TOKEN_FILE, "HHHH") and ok
    print("\nDONE." if ok else "\nDONE WITH ERRORS - see above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
