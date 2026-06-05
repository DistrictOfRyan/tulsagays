"""Live newsletter metrics for TulsaGays (Rung 1: the sellable number).

The media kit needs a CURRENT subscriber count + open rate, not a hardcoded
"4 subscribers." This pulls live stats from the Kit (ConvertKit) v4 API and
writes data/newsletter_metrics.json, so the media kit / a sponsor pitch can
quote a real, fresh number.

Read-only: only GETs account + subscriber + broadcast stats. Never sends.

Kit API: base https://api.kit.com/v4, auth header X-Kit-Api-Key.
Creds: C:\\Users\\willi\\.credentials\\kit_config.json
"""

import os
import sys
import json
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

KIT_CONFIG = r"C:\Users\willi\.credentials\kit_config.json"
OUT_FILE = os.path.join(config.DATA_DIR, "newsletter_metrics.json")


def _kit():
    c = json.load(open(KIT_CONFIG, encoding="utf-8"))
    return c["api_key"], c.get("api_base", "https://api.kit.com/v4").rstrip("/")


def _get(path, api_key, base):
    req = urllib.request.Request(base + path, headers={
        "X-Kit-Api-Key": api_key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_metrics():
    api_key, base = _kit()
    metrics = {"source": "kit", "subscribers": None, "broadcasts": None,
               "latest_broadcast": None, "error": None}
    try:
        # Total active subscribers (account-level)
        subs = _get("/subscribers?per_page=1", api_key, base)
        # v4 returns pagination with total_count when available
        tc = subs.get("pagination", {}).get("total_count")
        if tc is None and isinstance(subs.get("subscribers"), list):
            tc = len(subs["subscribers"])
        metrics["subscribers"] = tc

        # Broadcasts (sent newsletters)
        bc = _get("/broadcasts?per_page=5", api_key, base)
        blist = bc.get("broadcasts", [])
        metrics["broadcasts"] = bc.get("pagination", {}).get("total_count", len(blist))
        if blist:
            latest = blist[0]
            metrics["latest_broadcast"] = {
                "subject": latest.get("subject"),
                "id": latest.get("id"),
                "published_at": latest.get("published_at"),
            }
    except urllib.error.HTTPError as e:
        metrics["error"] = f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        metrics["error"] = str(e)
    return metrics


def run():
    m = fetch_metrics()
    if m["error"]:
        print(f"[newsletter] Kit API error: {m['error']} (creds may need refresh)")
    else:
        json.dump(m, open(OUT_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(f"[newsletter] subscribers={m['subscribers']} broadcasts={m['broadcasts']} "
              f"latest={(m['latest_broadcast'] or {}).get('subject')}")
        print(f"[newsletter] wrote {OUT_FILE}")
    return m


if __name__ == "__main__":
    run()
