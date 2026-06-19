#!/usr/bin/env python3
"""Blocked-on-William registry - things that need William's hands to unblock.

William's rule (2026-06-18): "when I'm blocking something from working, it needs
to show up on my daily TODAY dashboard so it gets fixed when I'm around." This is
the durable home for those items. Any session (or the scraper health guard)
registers a block here; the guard surfaces open items on the TODAY dashboard via
chief-of-staff/submit_brief.py on every run, so they stay in front of William
until resolved.

A "blocked-on-William" item is something the automation CANNOT do itself: a login
/ re-auth, an API token or app-review approval, a paid signup, a judgment call, or
a "find the org's new website" type human task. Do NOT register things Claude can
just do - do those.

File: data/blocked_on_william.json  (list of objects)
  { "id", "item", "reason", "source", "since" (YYYY-MM-DD), "status": open|resolved }

CLI:
  python tools/blocked_items.py add --item "..." --reason "..." --source "..." --since 2026-06-18
  python tools/blocked_items.py list [--all]
  python tools/blocked_items.py resolve --match "<substring>"
"""
import argparse
import json
import re
from pathlib import Path

STORE = Path(__file__).resolve().parent.parent / "data" / "blocked_on_william.json"


def load() -> list:
    if STORE.exists():
        try:
            return json.loads(STORE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save(items: list):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:48]


def add(item: str, reason: str, source: str = "", since: str = "") -> dict:
    items = load()
    iid = _slug(item)
    for ex in items:
        if ex.get("id") == iid and ex.get("status") == "open":
            ex.update({"reason": reason, "source": source})  # refresh, no dup
            _save(items)
            return ex
    rec = {"id": iid, "item": item, "reason": reason, "source": source,
           "since": since or "", "status": "open"}
    items.append(rec)
    _save(items)
    return rec


def resolve(match: str) -> int:
    items = load()
    n = 0
    for it in items:
        if it.get("status") == "open" and match.lower() in (it.get("item", "") + it.get("id", "")).lower():
            it["status"] = "resolved"
            n += 1
    _save(items)
    return n


def open_items() -> list:
    return [i for i in load() if i.get("status") == "open"]


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--item", required=True)
    a.add_argument("--reason", required=True)
    a.add_argument("--source", default="")
    a.add_argument("--since", default="")
    sub.add_parser("list").add_argument("--all", action="store_true")
    r = sub.add_parser("resolve")
    r.add_argument("--match", required=True)
    args = ap.parse_args()

    if args.cmd == "add":
        rec = add(args.item, args.reason, args.source, args.since)
        print("registered:", rec["id"])
    elif args.cmd == "list":
        items = load() if getattr(args, "all", False) else open_items()
        for it in items:
            print(f"  [{it.get('status','?'):8s}] {it['item']}  ({it.get('reason','')})")
        print(f"({len(items)} item(s))")
    elif args.cmd == "resolve":
        print(f"resolved {resolve(args.match)} item(s)")


if __name__ == "__main__":
    main()
