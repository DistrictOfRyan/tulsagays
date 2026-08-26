"""Verify events@tulsagays.com forwarding is LIVE, then publish the site notice.

Run this after the Namecheap forward (events@ -> williamryanhunt@gmail.com) is
added. It PROVES inbound delivery before publishing the address anywhere (never
announce a bouncing address to partners), then injects the email-submission
callout into docs/submit.html and pushes.

  python tools/go_live_email_intake.py            # probe + verify + deploy
  python tools/go_live_email_intake.py --check     # probe + verify only, no deploy

Exit 0 = forwarding verified (and deployed unless --check). Exit 2 = not live yet.
"""
from __future__ import annotations

import imaplib
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path.home() / ".claude" / "scripts"
# Moved to the non-synced credentials vault by the 2026-08 secret sweep.
IMAP_TOKEN = Path.home() / ".credentials" / "oauth" / "token_gmail_imap.json"
SUBMIT_HTML = ROOT / "docs" / "submit.html"
EMAIL_BOX = ROOT / "drafts" / "tulsagays" / "submit_email_box.html"
CONFIG = ROOT / "data" / "email_intake_config.json"
PROBE_SUBJECT = "TG-forward-verify"


def _imap():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    creds = Credentials.from_authorized_user_file(str(IMAP_TOKEN))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request()); IMAP_TOKEN.write_text(creds.to_json(), encoding="utf-8")
    auth = f"user=williamryanhunt@gmail.com\x01auth=Bearer {creds.token}\x01\x01"
    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    M.authenticate("XOAUTH2", lambda _: auth.encode())
    return M


def verify_forwarding(timeout_s: int = 150) -> bool:
    """Send a probe to events@ and confirm it DELIVERS to the INBOX (a real
    forward), not just the Sent folder. Returns True iff forwarding works."""
    stamp = str(int(time.time()))
    subj = f"{PROBE_SUBJECT} {stamp}"
    sys.path.insert(0, str(SCRIPTS))
    from send_gmail import send_email
    send_email("events@tulsagays.com", subj,
               "Automated forwarding verification. Safe to ignore.",
               account="personal",
               verified_evidence="own tulsagays.com domain, live MX, verifying forwarding",
               allow_repeat=True)   # a technical self-probe, not outreach — repeat is fine
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(20)
        try:
            M = _imap()
            M.select("INBOX")
            typ, d = M.search(None, f'(SUBJECT "{subj}")')   # INBOX = a real forward delivery
            inbox_hit = bool(d and d[0])
            M.select('"[Gmail]/All Mail"')
            typ, db = M.search(None, '(FROM "mailer-daemon" SUBJECT "Delivery" SINCE 07-Jul-2026)')
            M.logout()
            if inbox_hit:
                print(f"[verify] forwarding LIVE — probe delivered to inbox ({subj}).")
                return True
        except Exception as e:
            print(f"[verify] poll error (retrying): {e}")
    print("[verify] no inbox delivery within timeout — forward not live yet.")
    return False


def deploy_site_notice() -> bool:
    html = SUBMIT_HTML.read_text(encoding="utf-8")
    if "events@tulsagays.com" in html:
        print("[deploy] submit.html already has the email callout.")
        return True
    box = EMAIL_BOX.read_text(encoding="utf-8")
    anchor = '<form action="https://formspree.io/f/mykogbrb"'
    if anchor not in html:
        print("[deploy] could not find the form anchor in submit.html — insert manually.")
        return False
    html = html.replace(anchor, box.strip() + "\n\n            " + anchor, 1)
    SUBMIT_HTML.write_text(html, encoding="utf-8")
    print("[deploy] injected email-submission callout into docs/submit.html.")
    return True


def main():
    check_only = "--check" in sys.argv
    if not verify_forwarding():
        print("\nNext: add the events@ -> williamryanhunt@gmail.com forward at Namecheap, then re-run.")
        return 2
    # flip the config so the fleet knows inbound is live
    try:
        import json
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        cfg["forwarding_live"] = True
        CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        pass
    if check_only:
        print("[check] forwarding verified; skipping deploy (--check).")
        return 0
    if deploy_site_notice():
        for cmd in (["git", "add", "docs/submit.html", "data/email_intake_config.json"],
                    ["git", "commit", "-m", "Email intake LIVE: submit.html now offers events@tulsagays.com (forwarding verified)"],
                    ["git", "push"]):
            r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
            if r.returncode != 0 and cmd[1] != "commit":
                print(f"[deploy] git {cmd[1]} failed: {r.stderr[-200:]}")
                return 1
        print("[deploy] pushed. tulsagays.com/submit.html now lists events@tulsagays.com.")
    print("\nNEXT (outreach, address now works): send YBR (IG DM) + PFLAG (email Nicole, tomorrow) "
          "from drafts/tulsagays/. Autoresponder still needs the Gmail 'Send mail as' alias verified.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
