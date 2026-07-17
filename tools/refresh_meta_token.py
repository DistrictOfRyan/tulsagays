#!/usr/bin/env python3
"""ONE-COMMAND Meta token refresh for TulsaGays (canonical, 2026-07-16).

THE PROCESS IS CLOSED. Do not re-derive it. When the Meta page token dies
(only happens if William changes his Facebook password or revokes the app):

  1. William opens https://developers.facebook.com/tools/explorer/1468075241636760/
     (personal Chrome, logged into his Facebook). The app + permissions are
     already staged there (8 permissions incl. instagram_manage_insights).
  2. He clicks "Generate Access Token" -> "Continue as William" -> copies the
     token with the copy icon (starts with EAA).
  3. Run:  python tools/refresh_meta_token.py --short-token "<paste>"
     This exchanges it for a long-lived user token, derives the PERMANENT page
     token, writes it to .env (TULSAGAYS_PAGE_ACCESS_TOKEN), and verifies
     BOTH capabilities live:
       - page posting identity (me -> Tulsa Gays)
       - Instagram business_discovery (reads ANY public IG business account,
         e.g. @studio.66_, with NO login / session / 429 - gap G7's fix)

FACTS (verified 2026-07-16):
  - instagram_manage_insights is at Standard Access on the app. NO Meta App
    Review is needed for our own use. Never file one for this again.
  - The page token from a long-lived user token does not expire on its own.
  - instagrapi / browser IG sessions are ONLY for engagement (likes/follows),
    NEVER needed for reading public accounts - the Graph API tier-0 in
    scraper/studio66.py covers reads.

App ID 1468075241636760 ("Tulsa Gays Auto Poster"), FB page 1086906044497675,
IG business account 17841441654786297 (@tulsagays).
App secret: ~/.credentials/meta_app_secret_1468075241636760.txt
"""
from __future__ import annotations
import argparse, json, sys, urllib.error, urllib.parse, urllib.request
from pathlib import Path

APP_ID = "1468075241636760"
PAGE_ID = "1086906044497675"
IG_BUSINESS_ID = "17841441654786297"
ENV = Path(__file__).resolve().parent.parent / ".env"
SECRET_FILE = Path.home() / ".credentials" / f"meta_app_secret_{APP_ID}.txt"
GRAPH = "https://graph.facebook.com/v21.0"


def get(url: str) -> dict:
    return json.load(urllib.request.urlopen(url, timeout=30))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--short-token", required=True, help="EAA... token from Graph Explorer")
    a = ap.parse_args()
    secret = SECRET_FILE.read_text(encoding="utf-8").strip()

    print("1/4 exchanging for long-lived user token...")
    ll = get(f"{GRAPH}/oauth/access_token?grant_type=fb_exchange_token"
             f"&client_id={APP_ID}&client_secret={secret}"
             f"&fb_exchange_token={a.short_token}")["access_token"]

    print("2/4 deriving permanent page token...")
    page_tok = None
    for p in get(f"{GRAPH}/me/accounts?access_token={ll}").get("data", []):
        if p.get("id") == PAGE_ID:
            page_tok = p["access_token"]
    if not page_tok:
        print("FATAL: Tulsa Gays page not in me/accounts - did you approve all permissions?")
        return 1

    print("3/4 writing .env ...")
    lines = ENV.read_text(encoding="utf-8").splitlines()
    out, seen = [], False
    for line in lines:
        if line.startswith("TULSAGAYS_PAGE_ACCESS_TOKEN="):
            out.append("TULSAGAYS_PAGE_ACCESS_TOKEN=" + page_tok); seen = True
        else:
            out.append(line)
    if not seen:
        out.append("TULSAGAYS_PAGE_ACCESS_TOKEN=" + page_tok)
    ENV.write_text("\n".join(out) + "\n", encoding="utf-8")

    print("4/4 verifying live...")
    me = get(f"{GRAPH}/me?access_token={page_tok}")
    ok_page = me.get("id") == PAGE_ID
    print(f"    page identity: {'OK - ' + me.get('name','') if ok_page else 'FAIL: ' + str(me)}")
    fields = "business_discovery.username(studio.66_){username,media_count}"
    try:
        bd = get(f"{GRAPH}/{IG_BUSINESS_ID}?fields={urllib.parse.quote(fields)}"
                 f"&access_token={page_tok}").get("business_discovery", {})
        print(f"    business_discovery: OK - @{bd.get('username')} ({bd.get('media_count')} media)")
    except urllib.error.HTTPError as e:
        print(f"    business_discovery FAIL: {e.read().decode()[:120]}")
        print("    (was instagram_manage_insights included when generating the token?)")
        return 1
    print("DONE. Token refreshed, verified, permanent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
