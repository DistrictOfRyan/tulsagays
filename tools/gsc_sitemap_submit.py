"""Resubmit tulsagays.com's sitemap to Google Search Console (API, no browser).

Replaces two dead routes in the Wednesday blog task (2026-09-15):
  * the unauthenticated google.com/ping?sitemap= endpoint (404 since mid-2023), and
  * the Indexing API (403 "Web Search Indexing API has not been used in project
    592105005223"). That API is also officially limited to JobPosting and
    BroadcastEvent pages, so pinging it for blog posts was the wrong tool anyway.

The GA4 service account (claude-ops/tulsagays/google_service_account.json) holds
siteFullUser on https://www.tulsagays.com/ in Search Console, which is enough to
PUT a sitemap. Proven live 2026-09-15: PUT -> 204, then GET showed
lastSubmitted updated and isPending true.

Usage
  python tools/gsc_sitemap_submit.py            # submit + print status
  python tools/gsc_sitemap_submit.py --status   # status only
Exit 0 only when the submit is accepted (204/200) and the status read succeeds.
"""
import argparse
import json
import sys
import urllib.parse
from pathlib import Path

SA_FILE = Path(r"C:\Users\willi\claude-ops\tulsagays\google_service_account.json")
SITE = "https://www.tulsagays.com/"
SITEMAP = "https://www.tulsagays.com/sitemap.xml"


def _session():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    creds = service_account.Credentials.from_service_account_file(
        str(SA_FILE), scopes=["https://www.googleapis.com/auth/webmasters"])
    return AuthorizedSession(creds)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true", help="read status only, do not submit")
    a = ap.parse_args()
    s = _session()
    base = (f"https://www.googleapis.com/webmasters/v3/sites/{urllib.parse.quote(SITE, safe='')}"
            f"/sitemaps/{urllib.parse.quote(SITEMAP, safe='')}")
    if not a.status:
        r = s.put(base)
        print(f"[gsc] submit {SITEMAP} -> HTTP {r.status_code} {r.text[:160]}")
        if r.status_code not in (200, 204):
            return 1
    r = s.get(base)
    if r.status_code != 200:
        print(f"[gsc] status read failed: HTTP {r.status_code} {r.text[:200]}")
        return 1
    d = r.json()
    print(json.dumps({k: d.get(k) for k in ("lastSubmitted", "lastDownloaded", "isPending",
                                            "warnings", "errors")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
