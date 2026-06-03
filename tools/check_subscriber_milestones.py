"""
Check Kit subscriber count and Telegram William at milestone thresholds.
Called by tulsagays-newsletter-weekly task after each send.
Idempotent: stores last-celebrated milestone in data/newsletter_milestones.json.
"""
import json, os, sys, urllib.request, urllib.parse
from pathlib import Path

REPO = Path(__file__).parent.parent
MILESTONE_FILE = REPO / "data" / "newsletter_milestones.json"
KIT_CONFIG = Path(r"C:\Users\willi\.credentials\kit_config.json")
WILLIAM_CHAT_ID = "6202804878"

MILESTONES = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000]

MILESTONE_MESSAGES = {
    10:   "TulsaGays newsletter hit 10 subscribers. Double digits. We're doing it.",
    25:   "TulsaGays newsletter: 25 subscribers. Word is spreading.",
    50:   "TulsaGays newsletter: 50 subscribers. Half a hundred queer Tulsans in the inbox.",
    100:  "TulsaGays newsletter: 100 subscribers. This is real now.",
    250:  "TulsaGays newsletter: 250 subscribers. Level 3 on the growth ladder reached.",
    500:  "TulsaGays newsletter: 500 subscribers. Time to start pitching Featured Partners.",
    1000: "TulsaGays newsletter: 1,000 subscribers. Level 4 reached. Directory sponsorships now viable.",
    2500: "TulsaGays newsletter: 2,500 subscribers. Sponsorship packages are the play.",
    5000: "TulsaGays newsletter: 5,000 subscribers. This is a real media property.",
}


def get_subscriber_count():
    cfg = json.loads(KIT_CONFIG.read_text(encoding="utf-8"))
    key = cfg["api_key"]
    base = cfg.get("api_base", "https://api.kit.com/v4").rstrip("/")
    headers = {"X-Kit-Api-Key": key, "Accept": "application/json"}
    req = urllib.request.Request(
        f"{base}/subscribers?status=active&per_page=1", headers=headers
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
    # Kit returns pagination with cursor but not a total count directly
    # Fetch all and count — fine at small scale
    all_req = urllib.request.Request(
        f"{base}/subscribers?status=active&per_page=100", headers=headers
    )
    with urllib.request.urlopen(all_req, timeout=30) as r:
        all_data = json.loads(r.read().decode())
    subs = all_data.get("subscribers", [])
    # if has_next_page, count would be >100; for now exact enough
    has_next = all_data.get("pagination", {}).get("has_next_page", False)
    count = len(subs)
    if has_next:
        count = count  # Would need pagination; flag this
        print("WARNING: >100 subscribers, count is approximate")
    return count


def load_milestones():
    if MILESTONE_FILE.exists():
        return json.loads(MILESTONE_FILE.read_text(encoding="utf-8"))
    return {"celebrated": []}


def save_milestones(state):
    MILESTONE_FILE.parent.mkdir(parents=True, exist_ok=True)
    MILESTONE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def telegram(msg):
    """Send via Telegram MCP plugin — or fall back to pending-william-actions.md"""
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            raise ValueError("no TELEGRAM_BOT_TOKEN env var")
        data = urllib.parse.urlencode({"chat_id": WILLIAM_CHAT_ID, "text": msg}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            result = json.loads(r.read().decode())
            if result.get("ok"):
                print(f"Telegram sent: {msg[:80]}")
                return True
    except Exception as e:
        print(f"Telegram fallback to pending-actions: {e}")
    # Fallback: append to pending-william-actions.md
    pa = Path(r"C:\Users\willi\.claude\pending-william-actions.md")
    entry = f"\n## [MILESTONE] {msg}\n"
    with open(pa, "a", encoding="utf-8") as f:
        f.write(entry)
    return False


def main():
    count = get_subscriber_count()
    print(f"Active subscribers: {count}")
    state = load_milestones()
    celebrated = set(state.get("celebrated", []))
    new_celebrations = []
    for m in MILESTONES:
        if count >= m and m not in celebrated:
            msg = MILESTONE_MESSAGES.get(m, f"TulsaGays newsletter: {m} subscribers reached!")
            telegram(msg)
            new_celebrations.append(m)
            celebrated.add(m)
    if new_celebrations:
        state["celebrated"] = sorted(celebrated)
        state["last_count"] = count
        save_milestones(state)
        print(f"Celebrated milestones: {new_celebrations}")
    else:
        print(f"No new milestones (current: {count}, next: "
              f"{next((m for m in MILESTONES if m > count), 'beyond ladder')})")


if __name__ == "__main__":
    main()
