"""
Generate docs/issues/index.html — a public archive of sent newsletters.
Pulls sent broadcast metadata from Kit and renders a clean archive page.
Run weekly after sending, or on demand.

Usage: python tools/gen_newsletter_archive.py
"""
import json, os, urllib.request
from datetime import datetime
from pathlib import Path

KIT_CONFIG = Path(r"C:\Users\willi\.credentials\kit_config.json")
REPO = Path(__file__).parent.parent
OUT_DIR = REPO / "docs" / "issues"
OUT_FILE = OUT_DIR / "index.html"

SITE = "https://www.tulsagays.com"
BERRY = "#9B1E5F"


def kit_get(base, key, path):
    req = urllib.request.Request(
        f"{base}{path}",
        headers={"X-Kit-Api-Key": key, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def get_sent_broadcasts():
    cfg = json.loads(KIT_CONFIG.read_text(encoding="utf-8"))
    key = cfg["api_key"]
    base = cfg.get("api_base", "https://api.kit.com/v4").rstrip("/")
    data = kit_get(base, key, "/broadcasts?per_page=50")
    broadcasts = data.get("broadcasts", [])
    sent = [b for b in broadcasts if b.get("status") == "sent"]
    sent.sort(key=lambda b: b.get("send_at", ""), reverse=True)
    return sent


def format_date(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%B %-d, %Y") if os.name != "nt" else dt.strftime("%B %d, %Y").replace(" 0", " ")
    except Exception:
        return iso[:10] if iso else ""


def render_archive(broadcasts):
    if not broadcasts:
        items = '<p style="color:#777;text-align:center;padding:3rem 0;">No sent newsletters yet. The first one is coming soon.</p>'
    else:
        rows = []
        for b in broadcasts:
            date_str = format_date(b.get("send_at", ""))
            subject = b.get("subject", "Untitled")
            pub_url = b.get("public_url", "")
            link = f'<a href="{pub_url}" target="_blank" rel="noopener" style="color:{BERRY};font-weight:600;text-decoration:none">{subject}</a>' if pub_url else f'<span style="color:#ccc">{subject}</span>'
            rows.append(
                f'<div style="padding:14px 0;border-bottom:1px solid #1e1e1e;display:flex;justify-content:space-between;align-items:baseline;gap:1rem">'
                f'<div style="font-size:1rem">{link}</div>'
                f'<div style="color:#666;font-size:0.82rem;white-space:nowrap">{date_str}</div>'
                f'</div>'
            )
        items = "\n".join(rows)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Newsletter Archive | Tulsa Gays</title>
<meta name="description" content="Past issues of the TulsaGays weekly LGBTQ+ event newsletter for Tulsa, Oklahoma.">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{SITE}/issues/">
<meta property="og:title" content="Newsletter Archive — Tulsa Gays">
<meta property="og:description" content="Every weekly LGBTQ+ event digest we've sent, archived and public.">
<meta property="og:url" content="{SITE}/issues/">
<meta property="og:image" content="{SITE}/images/og-event.png">
<meta property="og:site_name" content="Tulsa Gays">
<link rel="icon" href="/favicon.ico">
<link rel="stylesheet" href="/style.css">
<style>
.arch-wrap{{max-width:680px;margin:0 auto;padding:48px 24px 80px}}
.arch-eyebrow{{color:{BERRY};font-size:.75rem;letter-spacing:.2em;text-transform:uppercase;margin-bottom:12px}}
.arch-title{{color:#fff;font-size:2rem;font-weight:800;margin:0 0 8px}}
.arch-sub{{color:#888;font-size:.95rem;margin:0 0 36px;line-height:1.6}}
.arch-sub a{{color:{BERRY}}}
.arch-cta{{display:inline-block;background:{BERRY};color:#fff;padding:11px 22px;border-radius:8px;font-weight:700;text-decoration:none;margin-bottom:40px;font-size:.9rem}}
</style>
</head>
<body>
<div class="arch-wrap">
  <div class="arch-eyebrow">Tulsa Gays</div>
  <h1 class="arch-title">Newsletter Archive</h1>
  <p class="arch-sub">Every weekly LGBTQ+ event digest, public and searchable.
  Not subscribed yet? <a href="/newsletter.html">Join the list</a> and get it every Monday.</p>
  <a class="arch-cta" href="/newsletter.html">Subscribe free &rarr;</a>
  <div>
{items}
  </div>
</div>
</body>
</html>'''


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    broadcasts = get_sent_broadcasts()
    print(f"Sent broadcasts found: {len(broadcasts)}")
    html = render_archive(broadcasts)
    OUT_FILE.write_text(html, encoding="utf-8")
    print(f"Written: {OUT_FILE} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
