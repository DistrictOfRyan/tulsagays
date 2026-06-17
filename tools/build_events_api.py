"""Publish the events as a documented, public JSON API feed.

This is the first concrete step toward the Path A ceiling ("The Queer Local Graph" — a
structured, real-time database of LGBTQ+ events that partners and other clients can read).
Today the site already ships docs/events-current.json; this formalizes it into a versioned,
schema-documented feed at docs/api/events.json that an external app could consume, plus
docs/api/README.md describing the contract.

Run after the weekly elevate step:  python tools/build_events_api.py
"""

from __future__ import annotations

import os
import sys
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "docs", "events-current.json")
API_DIR = os.path.join(REPO, "docs", "api")
OUT = os.path.join(API_DIR, "events.json")
README = os.path.join(API_DIR, "README.md")
API_VERSION = "1"


def build(now_iso: str | None = None) -> dict:
    with open(SRC, encoding="utf-8") as f:
        raw = json.load(f)
    events = raw if isinstance(raw, list) else raw.get("events", [])
    # Normalize to a stable public contract. Extra source fields pass through under "raw".
    norm = []
    for e in events:
        norm.append({
            "name": e.get("name", ""),
            "date": e.get("date", ""),
            "time": e.get("time", ""),
            "venue": e.get("venue", ""),
            "url": e.get("url", "") or e.get("source_url", ""),
            "lgbtq_relevant": bool(e.get("lgbtq_relevant", True)),
            "city": "Tulsa, OK",
        })
    feed = {
        "api_version": API_VERSION,
        "city": "Tulsa, OK",
        "publisher": "Tulsa Gays",
        "generated_at": now_iso or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "license": "CC BY 4.0 — attribute Tulsa Gays (tulsagays.com)",
        "count": len(norm),
        "events": norm,
    }
    return feed


def write(feed: dict) -> None:
    os.makedirs(API_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(feed, f, indent=2, ensure_ascii=False)
    with open(README, "w", encoding="utf-8") as f:
        f.write(_readme(feed))


def _readme(feed: dict) -> str:
    return f"""# Tulsa Gays Events API (v{API_VERSION})

Public, read-only JSON feed of LGBTQ+ events in Tulsa, OK. Free to consume with
attribution. This is the seed of a wider queer-local events graph.

- **Endpoint:** `https://www.tulsagays.com/api/events.json`
- **Format:** JSON, UTF-8
- **License:** {feed['license']}
- **Updated:** weekly (and whenever the site refreshes), `generated_at` is the stamp.

## Shape
```json
{{
  "api_version": "{API_VERSION}",
  "city": "Tulsa, OK",
  "publisher": "Tulsa Gays",
  "generated_at": "<ISO8601 UTC>",
  "license": "...",
  "count": <int>,
  "events": [
    {{
      "name": "string",
      "date": "YYYY-MM-DD",
      "time": "string (human, e.g. '9:00 PM')",
      "venue": "string",
      "url": "string (event or source URL, may be empty)",
      "lgbtq_relevant": true,
      "city": "Tulsa, OK"
    }}
  ]
}}
```

## Using it
```bash
curl -s https://www.tulsagays.com/api/events.json | jq '.events[] | .name'
```

Attribution required: link back to tulsagays.com. Want a richer feed (recurring rules,
geo, categories) or another city? That is the roadmap — partner inquiries via the site.
"""


def main():
    feed = build()
    write(feed)
    print(f"[events_api] wrote {OUT} ({feed['count']} events) + {README}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
