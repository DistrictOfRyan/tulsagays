"""Send an email via the Brevo transactional API as events@tulsagays.com.

Used by the email-intake autoresponder (tools/ingest_email_events._autorespond).
Anonymous by design: From is the TulsaGays Events sender (never William's address).
Reply-To is events@tulsagays.com so any reply forwards back to the inbox.

Key: BREVO_API_KEY in ~/.credentials/api_keys.env (added 2026-07-08). Until the
tulsagays.com domain is authenticated in Brevo (SPF/DKIM DNS), Brevo stamps the
From with its own subdomain; the Reply-To still routes correctly and the display
name stays "TulsaGays Events". Domain auth upgrades the visible address to the
clean events@tulsagays.com.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

ENV = Path.home() / ".credentials" / "api_keys.env"
SENDER = {"name": "TulsaGays Events", "email": "events@tulsagays.com"}
REPLY_TO = {"email": "events@tulsagays.com"}


def _key() -> str:
    k = os.environ.get("BREVO_API_KEY", "")
    if k:
        return k
    try:
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if line.startswith("BREVO_API_KEY="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def send(to_email: str, subject: str, text: str) -> tuple[bool, str]:
    """Returns (ok, detail). Never raises."""
    key = _key()
    if not key:
        return False, "no BREVO_API_KEY"
    html = "<div style=\"font-family:Arial,sans-serif;white-space:pre-wrap\">" + \
           re.sub(r"&", "&amp;", text).replace("<", "&lt;") + "</div>"
    body = {
        "sender": SENDER,
        "to": [{"email": to_email}],
        "replyTo": REPLY_TO,
        "subject": subject,
        "textContent": text,
        "htmlContent": html,
    }
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email", data=json.dumps(body).encode(),
        headers={"api-key": key, "accept": "application/json", "content-type": "application/json"},
        method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return (r.status in (200, 201)), r.read().decode()[:120]
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode()[:160]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:120]}"


if __name__ == "__main__":
    import sys
    ok, detail = send("williamryanhunt+brevoselftest@gmail.com",
                      "Brevo send selftest", "Selftest of tools/brevo_send.py")
    print("ok" if ok else "FAIL", detail)
