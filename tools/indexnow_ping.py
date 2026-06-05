"""IndexNow crawl accelerator (Answer Engine L7: tell the crawlers now).

When pages publish or change, ping the IndexNow API so Bing, Yandex, and other
participating engines (and the AI crawlers that ride on them) re-crawl in hours
instead of waiting weeks for a natural visit. No account, no money: IndexNow
authenticates via a self-hosted key file at /<key>.txt, which lives in docs/.

Reads docs/sitemap.xml, submits every URL. Run after the weekly deploy (the
source-growth task can call it once the docs commit is pushed). `--dry-run`
builds and prints the payload without sending. `--selftest` proves payload
construction offline.
"""

import os
import sys
import re
import json
import argparse
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

HOST = "www.tulsagays.com"
KEY = "2a58e83c604f275ba8785229be9efd2e"
KEY_LOCATION = f"https://{HOST}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"
SITEMAP = os.path.join(config.PROJECT_DIR, "docs", "sitemap.xml")


def _urls_from_sitemap():
    if not os.path.exists(SITEMAP):
        return []
    xml = open(SITEMAP, encoding="utf-8").read()
    return re.findall(r"<loc>(.*?)</loc>", xml)


def build_payload(urls):
    return {"host": HOST, "key": KEY, "keyLocation": KEY_LOCATION,
            "urlList": urls}


def ping(dry_run=False):
    urls = _urls_from_sitemap()
    if not urls:
        print("[indexnow] no URLs in sitemap; nothing to submit.")
        return {"submitted": 0}
    payload = build_payload(urls)
    if dry_run:
        print(f"[indexnow] DRY RUN: would submit {len(urls)} URLs to {ENDPOINT}")
        print(f"  keyLocation={KEY_LOCATION}")
        for u in urls[:5]:
            print(f"  - {u}")
        return {"submitted": len(urls), "dry_run": True}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(ENDPOINT, data=data, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"[indexnow] submitted {len(urls)} URLs -> HTTP {r.status}")
            return {"submitted": len(urls), "status": r.status}
    except urllib.error.HTTPError as e:
        # IndexNow returns 200/202 on success; 4xx if key not yet reachable
        print(f"[indexnow] HTTP {e.code}: {e.reason} "
              f"(if 403/422, the key file may not be deployed yet — re-run after Pages publishes)")
        return {"submitted": len(urls), "status": e.code}
    except Exception as e:
        print(f"[indexnow] error: {e}")
        return {"submitted": len(urls), "error": str(e)}


def _selftest():
    urls = ["https://www.tulsagays.com/", "https://www.tulsagays.com/guides/gay-bars-in-tulsa.html"]
    p = build_payload(urls)
    assert p["host"] == HOST
    assert p["key"] == KEY and len(KEY) == 32
    assert p["keyLocation"] == KEY_LOCATION
    assert p["urlList"] == urls
    json.dumps(p)  # serializable
    print(f"indexnow_ping selftest: passed (payload valid, key {KEY[:6]}..., {len(urls)} urls)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(_selftest())
    ping(dry_run=args.dry_run)
