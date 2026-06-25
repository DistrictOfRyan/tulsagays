"""
TulsaGays weekly newsletter -> Kit (nextlevel Rung 2: Owned Audience).

Builds the week's email from the SAME cleaned/deduped event data the carousel
uses (slide_manifest.json) and creates a Kit broadcast. DRAFT BY DEFAULT — it
never sends without the explicit --send flag, because a broadcast is an outward
publish to the owned list (approval-gated by policy). So this prepares a
one-click-ready draft in Kit; William hits send (or passes --send after his ok).

Usage:
  python tools/send_newsletter.py            # create/refresh this week's DRAFT
  python tools/send_newsletter.py --send     # actually broadcast (needs William's go)
  python tools/send_newsletter.py --week 2026-W24
"""
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402

KIT = json.loads((Path.home() / ".credentials" / "kit_config.json").read_text(encoding="utf-8"))
API = "https://api.kit.com/v4"
SITE = "https://www.tulsagays.com"


def _hdr():
    return {"X-Kit-Api-Key": KIT["api_key"].strip(), "Accept": "application/json",
            "Content-Type": "application/json"}


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_email(week_key):
    man = json.loads((ROOT / "data" / "posts" / week_key / "slide_manifest.json").read_text(encoding="utf-8"))
    eotw = (man.get("eotw") or [{}])[0]
    by_day = man.get("featured_by_day", {})
    DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    subj = f"This week in queer Tulsa: {eotw.get('name', 'your LGBTQ+ calendar')}"
    preview = "Your hand-picked LGBTQ+ events for the week. Get off the couch."

    parts = ['<div style="font-family:Helvetica,Arial,sans-serif;max-width:600px;margin:0 auto;color:#222;line-height:1.6">']
    parts.append('<p style="font-size:18px"><strong>pov: you actually have plans this week.</strong></p>')
    # EOTW hero
    if eotw.get("name"):
        parts.append('<div style="border:2px solid #e6007e;border-radius:10px;padding:16px;margin:16px 0">')
        parts.append('<div style="color:#e6007e;font-size:12px;letter-spacing:.1em;text-transform:uppercase">Event of the Week</div>')
        parts.append(f'<h2 style="margin:6px 0">{_esc(eotw.get("name"))}</h2>')
        when = " · ".join(x for x in [eotw.get("date", ""), eotw.get("time", "")] if x)
        ven = (eotw.get("venue") or "").split(",")[0].strip()
        parts.append(f'<p style="color:#666;margin:2px 0">{_esc(when)}{" · " + _esc(ven) if ven else ""}</p>')
        parts.append(f'<p>{_esc(eotw.get("website_description") or eotw.get("description") or "")}</p>')
        if (eotw.get("url") or "").startswith("http"):
            parts.append(f'<a href="{_esc(eotw["url"])}" style="color:#e6007e">Tickets / info &rarr;</a>')
        parts.append('</div>')
    # day-by-day featured
    for day in DAYS:
        evs = by_day.get(day, [])
        if not evs:
            continue
        parts.append(f'<h3 style="border-bottom:1px solid #eee;padding-bottom:4px;margin-top:22px">{day}</h3>')
        for e in evs:
            when = " · ".join(x for x in [e.get("time", "")] if x)
            ven = (e.get("venue") or "").split(",")[0].strip()
            line = f'<strong>{_esc(e.get("name",""))}</strong>'
            meta = " · ".join(x for x in [when, ven] if x)
            if meta:
                line += f' <span style="color:#888">· {_esc(meta)}</span>'
            parts.append(f'<p style="margin:8px 0">{line}<br>'
                         f'<span style="color:#444">{_esc(e.get("description",""))}</span></p>')
    parts.append(f'<p style="margin-top:26px"><a href="{SITE}" style="background:#e6007e;color:#fff;'
                 f'padding:10px 18px;border-radius:6px;text-decoration:none">See every event at tulsagays.com &rarr;</a></p>')
    parts.append('<p style="color:#999;font-size:12px;margin-top:24px">You\'re getting this because you '
                 'wanted Tulsa\'s queer calendar in your inbox. Pace yourself, hydrate, look out for each other.</p>')
    parts.append('</div>')
    return subj, preview, "\n".join(parts)


DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def content_guard(week_key):
    """Safety gate for the AUTOMATED Tuesday send. Returns (ok, reason, stats).

    A broken/empty week must NEVER blast to the owned list. Aborts the send when
    the Monday pipeline didn't produce a usable manifest:
      - manifest missing/unreadable
      - no EOTW hero
      - fewer than 5 of 7 days have a featured event
      - fewer than 10 featured events total
    """
    man_path = ROOT / "data" / "posts" / week_key / "slide_manifest.json"
    if not man_path.exists():
        return False, f"no slide_manifest.json for {week_key} (Monday pipeline didn't run?)", {}
    try:
        man = json.loads(man_path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return False, f"manifest unreadable: {e}", {}
    eotw = (man.get("eotw") or [{}])[0]
    by_day = man.get("featured_by_day", {})
    days_with = [d for d in DAYS if by_day.get(d)]
    total = sum(len(by_day.get(d, [])) for d in DAYS)
    stats = {"eotw": eotw.get("name"), "days_populated": len(days_with), "events": total}
    if not eotw.get("name"):
        return False, "no EOTW in manifest", stats
    if len(days_with) < 5:
        return False, f"only {len(days_with)}/7 days populated", stats
    if total < 10:
        return False, f"only {total} featured events (need >=10)", stats
    return True, "ok", stats


def main():
    args = sys.argv[1:]
    send = "--send" in args
    dry_run = "--dry-run" in args
    force = "--force" in args
    week = config.current_week_key()
    if "--week" in args:
        week = args[args.index("--week") + 1]

    # Automated/real send is gated on content sanity (skippable with --force for a
    # manual override). Draft creation is never gated.
    if (send or dry_run) and not force:
        ok, reason, stats = content_guard(week)
        print(f"content guard [{week}]: {'PASS' if ok else 'BLOCK'} - {reason} | {stats}")
        if not ok:
            print("ABORTED: not sending a broken/empty newsletter. Fix the Monday pipeline and re-run.")
            return 2

    if dry_run:
        subj, preview, html = build_email(week)
        print(f"DRY RUN (no send): would send '{subj}' ({len(html)} bytes) for {week}")
        return 0

    subj, preview, html = build_email(week)
    payload = {"subject": subj, "preview_text": preview, "content": html, "public": False}
    if send:
        payload["send_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    req = urllib.request.Request(API + "/broadcasts", method="POST",
                                 data=json.dumps(payload).encode("utf-8"), headers=_hdr())
    try:
        d = json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        print("FAILED:", e.code, e.read().decode()[:300])
        return 1
    b = d.get("broadcast", d)
    print(f"{'SENT' if send else 'DRAFT created'}: broadcast id={b.get('id')} | status={b.get('status')}")
    print(f"  subject: {subj}")
    print(f"  edit/send in Kit: https://app.kit.com/broadcasts/{b.get('id')}")
    if not send:
        print("  -> review in Kit and hit Send, or run with --send after William's go.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
