"""
Special July 4th weekend TulsaGays post.
Run once: Thursday July 3, 2026 morning.
Posts to Facebook page + Instagram (text post only, no carousel).
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import os, json, requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(r"C:\Users\willi\tulsagays\.env")

with open(r"C:\Users\willi\tulsagays\meta_api_config.json") as f:
    cfg = json.load(f)

page_id = cfg["page_id"]
ig_id = cfg.get("instagram_business_account_id") or cfg.get("ig_user_id")
token = os.environ.get("TULSAGAYS_PAGE_ACCESS_TOKEN")

if not token or token.startswith("MOVED_TO_ENV"):
    print("[FATAL] No usable TULSAGAYS_PAGE_ACCESS_TOKEN in environment")
    sys.exit(1)

caption = """YOUR FOUR-DAY WEEKEND STARTS TONIGHT. 🌈🎆

Tonight (Thu, Jul 3) | Homo Hotel Happy Hour
The Campbell Hotel, 6-8pm. Free, inclusive, no agenda except good people and cold drinks.

Tomorrow (Fri, Jul 4) | Babes & Bi-cons Dance Party
Yellow Brick Road, 9:30pm. Queer dance party on the Fourth. Come out. Literally.

Fri, Jul 4 | July 4th Too Geeked Ta Function
The Boman, 9pm. Good vibes, good music, holiday weekend done right.

Sun, Jul 5 | Sunday Showdown Open Talent Night
Club Majestic, 124 N Boston Ave. Doors 9pm, show 11pm. Show off or just watch.

Full weekend at tulsagays.com
#TulsaGays #TulsaLGBTQIA #LGBTQTulsa #TulsaEvents #GayTulsa #July4th #Tulsa"""

print("=== CAPTION ===")
print(caption)
print("=== END CAPTION ===")
print(f"Length: {len(caption)} chars")

# Post to Facebook
print("\n[Facebook] Posting...")
fb_resp = requests.post(
    f"https://graph.facebook.com/v19.0/{page_id}/feed",
    data={"message": caption, "access_token": token},
    timeout=30
)
fb_result = fb_resp.json()
print("FB response:", fb_result)

if "error" in fb_result:
    print(f"[ERROR] Facebook failed: {fb_result['error']}")
    sys.exit(1)

fb_post_id = fb_result.get("id", "")
print(f"[ok] FB post_id: {fb_post_id}")

# Verify FB post
verify = requests.get(
    f"https://graph.facebook.com/v19.0/{fb_post_id}",
    params={"fields": "message,permalink_url", "access_token": token},
    timeout=15
).json()
posted_msg = verify.get("message", "")
fb_url = verify.get("permalink_url", "")
if not posted_msg:
    print(f"[FAIL] FB post verification failed: {verify}")
    sys.exit(1)
print(f"[verified] FB post live: {fb_url}")

# Post to Instagram (text-only via background image)
ig_result = None
image_url = "https://www.tulsagays.com/assets/weekend-preview-bg.png"

# Check if image is available
import urllib.request
image_ok = False
try:
    req = urllib.request.Request(image_url, method="HEAD")
    urllib.request.urlopen(req, timeout=5)
    image_ok = True
    print(f"\n[IG] Image available at {image_url}")
except Exception as e:
    print(f"\n[IG] Background image not available ({e}) -- trying text-only container")

if image_ok and ig_id:
    container_resp = requests.post(
        f"https://graph.facebook.com/v19.0/{ig_id}/media",
        data={"image_url": image_url, "caption": caption, "access_token": token},
        timeout=30
    ).json()
    print("IG container:", container_resp)

    if "id" in container_resp:
        publish_resp = requests.post(
            f"https://graph.facebook.com/v19.0/{ig_id}/media_publish",
            data={"creation_id": container_resp["id"], "access_token": token},
            timeout=30
        ).json()
        print("IG publish:", publish_resp)
        ig_result = publish_resp.get("id", "")
        if ig_result:
            print(f"[ok] IG post_id: {ig_result}")
        else:
            print("[WARN] IG publish did not return id -- FB post succeeded")
    else:
        print(f"[WARN] IG container creation failed -- FB only: {container_resp}")
elif ig_id:
    print("[IG] Image unavailable -- FB only post this run")

# Write post record
record = {
    "type": "july4_holiday_preview",
    "posted_at": datetime.now().isoformat(),
    "fb_post_id": fb_post_id,
    "fb_url": fb_url,
    "ig_post_id": ig_result or "skipped",
    "events": [
        "HHHH The Campbell Hotel Jul 3 6-8pm",
        "Babes & Bi-cons Dance Party YBR Jul 4 9:30pm",
        "July 4th Too Geeked Ta Function The Boman Jul 4 9pm",
        "Sunday Showdown Club Majestic Jul 5 doors 9pm"
    ]
}

record_path = r"C:\Users\willi\tulsagays\data\posts\2026-W27\july4_preview_result.json"
with open(record_path, "w") as f:
    json.dump(record, f, indent=2)
print(f"\n[record] Written to {record_path}")
print("\n[DONE] July 4th weekend post complete.")
print(f"FB: {fb_url}")
print(f"IG: {ig_result or 'skipped'}")
