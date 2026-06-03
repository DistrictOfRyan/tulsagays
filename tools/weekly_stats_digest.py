"""
Weekly stats digest for TulsaGays newsletter.
Pulls Kit subscriber count + last broadcast stats and Telegrams William.
Called by tulsagays-newsletter-weekly after each Monday send.

Usage: python tools/weekly_stats_digest.py
"""
import json, os, sys, urllib.request, urllib.parse
from datetime import datetime
from pathlib import Path

KIT_CONFIG = Path(r"C:\Users\willi\.credentials\kit_config.json")
WILLIAM_CHAT_ID = "6202804878"
PENDING_ACTIONS = Path(r"C:\Users\willi\.claude\pending-william-actions.md")


def kit_get(base, key, path):
    req = urllib.request.Request(
        f"{base}{path}",
        headers={"X-Kit-Api-Key": key, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def get_stats():
    cfg = json.loads(KIT_CONFIG.read_text(encoding="utf-8"))
    key = cfg["api_key"]
    base = cfg.get("api_base", "https://api.kit.com/v4").rstrip("/")

    # Subscriber count
    sub_data = kit_get(base, key, "/subscribers?status=active&per_page=100")
    subs = sub_data.get("subscribers", [])
    has_next = sub_data.get("pagination", {}).get("has_next_page", False)
    sub_count = len(subs)

    # Last 3 broadcasts
    bc_data = kit_get(base, key, "/broadcasts?per_page=3")
    broadcasts = bc_data.get("broadcasts", [])

    last_send = None
    for b in broadcasts:
        if b.get("status") == "sent" and b.get("send_at"):
            try:
                stats_data = kit_get(base, key, f"/broadcasts/{b['id']}/stats")
                stats = stats_data.get("broadcast", {}).get("stats", {})
                last_send = {
                    "subject": b.get("subject", "")[:60],
                    "sent_at": b.get("send_at", "")[:10],
                    "recipients": stats.get("recipients", 0),
                    "open_rate": round(stats.get("open_rate", 0) * 100, 1),
                    "emails_opened": stats.get("emails_opened", 0),
                    "unsubscribes": stats.get("unsubscribes", 0),
                    "total_clicks": stats.get("total_clicks", 0),
                }
                break
            except Exception:
                continue

    return {
        "sub_count": sub_count,
        "has_more": has_next,
        "last_send": last_send,
        "broadcasts_total": len(broadcasts),
    }


def format_digest(stats):
    count = stats["sub_count"]
    more = "+" if stats["has_more"] else ""
    lines = [
        f"TulsaGays Newsletter -- Weekly Stats",
        f"--------------------",
        f"Subscribers: {count}{more} active",
    ]
    ls = stats.get("last_send")
    if ls:
        lines += [
            f"",
            f"Last send ({ls['sent_at']}):",
            f"  Subject: {ls['subject']}",
            f"  Recipients: {ls['recipients']}",
            f"  Opened: {ls['emails_opened']} ({ls['open_rate']}%)",
            f"  Clicks: {ls['total_clicks']}",
            f"  Unsubscribes: {ls['unsubscribes']}",
        ]
    else:
        lines.append("No sent broadcasts yet — first send pending.")
    lines += [
        f"",
        f"Next milestone: {next((m for m in [10,25,50,100,250,500,1000] if m > count), 'beyond ladder')} subscribers",
        f"Kit dashboard: app.kit.com",
    ]
    return "\n".join(lines)


def send_telegram(msg):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return False
    data = urllib.parse.urlencode({"chat_id": WILLIAM_CHAT_ID, "text": msg}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            result = json.loads(r.read().decode())
            return result.get("ok", False)
    except Exception:
        return False


def main():
    stats = get_stats()
    digest = format_digest(stats)
    print(digest)

    sent = send_telegram(digest)
    if not sent:
        # Fallback to pending-william-actions.md
        entry = f"\n## [{datetime.now().strftime('%Y-%m-%d %H:%M')}] TulsaGays Weekly Stats\n"
        entry += "\n".join(f"- {l}" for l in digest.split("\n") if l.strip()) + "\n"
        with open(PENDING_ACTIONS, "a", encoding="utf-8") as f:
            f.write(entry)
        print("(Telegram not available — appended to pending-william-actions.md)")


if __name__ == "__main__":
    main()
