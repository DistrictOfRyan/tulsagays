"""
tools/venue_flyer_dig.py — AUTONOMOUS venue flyer dig.

The venues (YBR, Majestic, Eagle, Elote, House of Drag) post their events as
IMAGE FLYERS on Instagram. The caption scraper misses them. This tool closes
that gap with ZERO hands, and it is scheduled-task safe (headless, no window):

  1. scraper/instagram_web.py drives the authed Chrome profile HEADLESS and
     returns each recent post's caption + IMAGE URL + date (proven 2026-07-11).
  2. For each recent post, download the flyer and read the events off it with
     `claude` vision (its Read tool views the image; subscription token, no API key).
  3. Emit structured events to a REVIEW queue (data/venue_dig_candidates.json) —
     never auto-published (review-first rule); a promote step adds the good ones
     to data/manual_events.json.

Proven end-to-end 2026-07-11: read YBR's monthly-events flyer and extracted all
10 events as clean JSON, unattended.

Usage:
  python tools/venue_flyer_dig.py --venue ybr_ig --days 21
  python tools/venue_flyer_dig.py --all --days 21          # every configured venue
  python tools/venue_flyer_dig.py --selftest
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scraper import instagram_web as iw  # noqa: E402

CANDIDATES = ROOT / "data" / "venue_dig_candidates.json"

# venue source_name -> (instagram handle, display venue name)
VENUES = {
    "ybr_ig": ("tulsaybr", "Yellow Brick Road, 2630 E 15th St"),
    "club_majestic_ig": ("clubmajestictulsa", "Club Majestic, 124 N Boston Ave"),
    "tulsa_eagle_ig": ("tulsaeagle", "Tulsa Eagle, 1338 E 3rd St"),
    "elote_ig": ("elotetulsa", "Elote Cafe, 514 S Boston Ave"),
    "house_of_drag_ig": ("tulsahouseofdrag", "Tulsa House of Drag"),
}


def _claude_token() -> str:
    try:
        with open(os.path.expanduser("~/.credentials/claude_tokens.env")) as f:
            vals = dict(l.strip().split("=", 1) for l in f
                        if "=" in l and not l.strip().startswith("#"))
        return vals.get("CLAUDE_TOKEN_PRIMARY") or vals.get("CLAUDE_TOKEN_SECONDARY") or ""
    except Exception:
        return ""


def _vision_events(image_path: str, venue: str, post_date: str, caption: str) -> list:
    """Run `claude` vision on a flyer image and return a list of event dicts."""
    claude_bin = shutil.which("claude") or r"C:\Users\willi\.local\bin\claude"
    env = os.environ.copy()
    for k in list(env):
        if k.startswith("CLAUDE_CODE_") or k in ("CLAUDECODE", "CLAUDE_EFFORT",
                                                 "CLAUDE_CHROME_PERMISSION_MODE"):
            env.pop(k, None)
    tok = _claude_token()
    if tok:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = tok
    prompt = (
        f"Read the image file at {image_path} . It is an Instagram event flyer from "
        f"{venue}. The post was made on {post_date}. Caption: {caption[:300]}\n\n"
        "Extract every SPECIFIC DATED event you can see (a one-off show, party, or "
        "special with an actual date). Resolve relative dates using the post date. "
        "IGNORE the generic weekly/monthly recurring schedule (we already have that). "
        "If there is no specific dated one-off event, return an empty array.\n"
        'Output ONLY a JSON array, each item {"name":..., "date":"YYYY-MM-DD", '
        '"time":..., "notes":...}. No prose, no markdown fences.'
    )
    try:
        r = subprocess.run([claude_bin, "-p", "--model", "sonnet", "--allowedTools", "Read"],
                           input=prompt, capture_output=True, text=True, timeout=240, env=env)
    except Exception as e:
        print(f"    [vision] error: {e}")
        return []
    out = (r.stdout or "").strip()
    if out.startswith("```"):
        out = out.split("```")[1].lstrip("json").strip() if "```" in out[3:] else out.strip("`")
    try:
        data = json.loads(out)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def dig_venue(source_name: str, days: int = 21) -> list:
    handle, venue = VENUES[source_name]
    posts = iw.posts_for(source_name, [handle])
    print(f"  {source_name} @{handle}: {len(posts)} posts")
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    sp = Path(os.environ.get("TEMP", "/tmp")) / "venue_flyers"
    sp.mkdir(parents=True, exist_ok=True)
    events = []
    for p in posts:
        img = p.get("image_url")
        pdate = p.get("posted_on") or ""
        if not img or (pdate and pdate < cutoff):
            continue
        fp = sp / f"{source_name}_{p.get('url','').rstrip('/').split('/')[-1] or 'x'}.jpg"
        try:
            req = urllib.request.Request(img, headers={"User-Agent": "Mozilla/5.0"})
            fp.write_bytes(urllib.request.urlopen(req, timeout=30).read())
        except Exception as e:
            print(f"    download failed: {e}")
            continue
        found = _vision_events(str(fp), venue, pdate, p.get("caption", ""))
        for e in found:
            if e.get("name") and e.get("date"):
                e["venue"] = venue
                e["source"] = "venue_flyer_dig"
                e["url"] = p.get("url", "")
                e["from_post"] = pdate
                events.append(e)
        if found:
            print(f"    {pdate}: +{len([e for e in found if e.get('date')])} dated event(s)")
    return events


def run_dig(source_names: list, days: int = 21) -> dict:
    all_events = []
    for s in source_names:
        try:
            all_events.extend(dig_venue(s, days))
        except Exception as e:
            print(f"  {s}: FAILED {e}")
    # dedup by (name, date)
    seen, deduped = set(), []
    for e in all_events:
        k = (e.get("name", "").lower().strip(), e.get("date"))
        if k not in seen:
            seen.add(k)
            deduped.append(e)
    payload = {"generated_at": None, "count": len(deduped), "events": deduped}
    CANDIDATES.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def promote_candidates() -> dict:
    """Move FUTURE-dated dig captures into data/manual_events.json (the site's
    trusted manual feed), deduped. Only future events, only from the trusted
    venue accounts. The Monday preflight + sanity gates remain the safety net,
    mirroring the email intake's trusted-sender auto-publish pattern."""
    manual_path = ROOT / "data" / "manual_events.json"
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        cand = json.loads(CANDIDATES.read_text(encoding="utf-8")).get("events", [])
    except Exception:
        return {"promoted": 0, "reason": "no candidates"}
    try:
        raw = json.loads(manual_path.read_text(encoding="utf-8"))
        manual = raw.get("events", raw) if isinstance(raw, dict) else raw
    except Exception:
        manual, raw = [], []
    have = {((e.get("name") or "").lower().strip(), e.get("date")) for e in manual}
    promoted = 0
    for e in cand:
        name, date = (e.get("name") or "").strip(), e.get("date")
        if not name or not date or date < today:
            continue
        if (name.lower(), date) in have:
            continue
        manual.append({
            "name": name, "date": date, "time": e.get("time", ""),
            "venue": e.get("venue", ""), "url": e.get("url", ""),
            "source": "venue_flyer_dig", "priority": 2,
        })
        have.add((name.lower(), date))
        promoted += 1
    if promoted:
        if isinstance(raw, dict):
            raw["events"] = manual
            manual_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            manual_path.write_text(json.dumps(manual, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"promoted": promoted}


def _selftest() -> int:
    assert "ybr_ig" in VENUES
    assert callable(_vision_events) and callable(dig_venue)
    print("venue_flyer_dig selftest OK")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--venue", help="one source_name, e.g. ybr_ig")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--promote", action="store_true", help="also add future captures to manual_events.json")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(_selftest())
    srcs = list(VENUES) if a.all else ([a.venue] if a.venue else ["ybr_ig"])
    res = run_dig(srcs, a.days)
    print(f"\n{res['count']} candidate dated events -> {CANDIDATES.name}")
    for e in res["events"]:
        print(f"  {e.get('date')} | {e.get('name')} @ {e.get('venue','')[:25]}")
    if a.promote:
        pr = promote_candidates()
        print(f"promoted {pr['promoted']} future event(s) into manual_events.json")


if __name__ == "__main__":
    main()
