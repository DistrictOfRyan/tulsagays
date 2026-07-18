"""TulsaRemote Slack event scraper — SESSION mode (no app install, no admin).

Proven live 2026-07-17: the workspace admin-blocked the Slack app, so instead of
an installed bot/user token this rides William's OWN logged-in member session.
A one-time headed login (slack_session_login.py) saves a persistent Playwright
profile; this runs HEADLESS against that profile and calls Slack's internal
conversations.history from inside the authenticated page — exactly what the
browser does when he reads the channel by hand. No admin approval required.

Reuses ALL extraction/formatting from slack_api_scraper.py (message_to_event,
extract_*, CHANNELS, output format) so the Monday pipeline sees an identical
data/slack_events_browser.json.

Exit codes (consumed by the task handler):
  0 = wrote a fresh file with >=1 event
  2 = session missing/expired (William must re-run slack_session_login.py)
  3 = Slack API error (channel gone, rate-limited, etc.)
  4 = ran clean but 0 event-shaped messages (file left untouched)
  5 = playwright/profile launch failure

Usage:
  python scraper/slack_session_scraper.py --run
  python scraper/slack_session_scraper.py --dry-run
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

# Reuse the entire proven extraction + output contract from the token scraper.
from scraper.slack_api_scraper import (  # noqa: E402
    CHANNELS, BROWSER_JSON, FLAG_FILE, MAX_PAGES_PER_CHANNEL,
    message_to_event,
)

TEAM_ID = "TF1E6FCR5"
PROFILE_DIR = os.path.join(os.path.expanduser("~"), ".credentials", "slack_pw_profile")
CLIENT_URL = f"https://app.slack.com/client/{TEAM_ID}"

# JS run INSIDE the authenticated Slack page. The `d` auth cookie is sent
# automatically by the browser (credentials:include); the xoxc token comes from
# the page's own localStorage. This is the exact call proven to work live.
_FETCH_JS = """
async (channelId) => {
  let token = null;
  try {
    const cfg = JSON.parse(localStorage.getItem('localConfig_v2'));
    // This profile only ever holds the Tulsa Remote session, and Slack leaves
    // team_id null in a fresh profile, so grab the first xoxc token present.
    for (const t of Object.values(cfg.teams || {})) {
      if (t.token && t.token.startsWith('xoxc')) token = t.token;
    }
  } catch (e) { return {ok:false, error:'localstorage:'+e}; }
  if (!token) return {ok:false, error:'no_session_token'};
  const out = []; let cursor = null; let pages = 0;
  do {
    const fd = new FormData();
    fd.append('token', token);
    fd.append('channel', channelId);
    fd.append('limit', '200');
    if (cursor) fd.append('cursor', cursor);
    let j;
    try {
      const r = await fetch('/api/conversations.history', {method:'POST', body:fd, credentials:'include'});
      j = await r.json();
    } catch (e) { return {ok:false, error:'fetch:'+e, got:out.length}; }
    if (!j.ok) return {ok:false, error:j.error, got:out.length};
    out.push(...(j.messages || []));
    cursor = (j.response_metadata && j.response_metadata.next_cursor) || null;
    pages++;
  } while (cursor && pages < %d);
  return {ok:true, messages: out};
}
""" % (MAX_PAGES_PER_CHANNEL,)


def _logged_in(page) -> bool:
    try:
        return bool(page.evaluate(
            "() => { try { const c = JSON.parse(localStorage.getItem('localConfig_v2'));"
            " return Object.values(c.teams||{}).some(t => t.token"
            " && t.token.startsWith('xoxc')); } catch(e){ return false; } }"))
    except Exception:
        return False


def run(dry_run: bool = False) -> tuple:
    summary = {"ok": False, "mode": "session", "channels": {}, "events_total": 0,
               "wrote_file": False, "notes": []}

    if not os.path.isdir(PROFILE_DIR):
        summary["notes"].append(
            f"no Slack session profile at {PROFILE_DIR} — run "
            "`python scraper/slack_session_login.py` once (William logs in).")
        return 2, summary

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        summary["notes"].append(f"playwright import failed: {e}")
        return 5, summary

    all_events = []
    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                PROFILE_DIR, headless=True,
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"))
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(CLIENT_URL, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(4000)  # let the SPA hydrate localStorage
                if not _logged_in(page):
                    summary["notes"].append(
                        "session expired / not logged in — re-run slack_session_login.py.")
                    ctx.close()
                    return 2, summary

                hard_errors = 0
                for name, cid in CHANNELS.items():
                    if not cid:  # gradient: doesn't exist
                        summary["channels"][name] = {"id": None, "skipped": "no channel id"}
                        continue
                    res = page.evaluate(_FETCH_JS, cid)
                    if not res.get("ok"):
                        hard_errors += 1
                        summary["channels"][name] = {"id": cid, "error": res.get("error")}
                        continue
                    msgs = res.get("messages", [])
                    evs, seen = [], set()
                    for m in msgs:
                        ev = message_to_event(m, name, token="")
                        if ev:
                            k = (ev["name"].lower(), ev["date"])
                            if k not in seen:
                                seen.add(k)
                                evs.append(ev)
                    summary["channels"][name] = {"id": cid, "messages": len(msgs), "events": len(evs)}
                    all_events.extend(evs)
            finally:
                ctx.close()
    except Exception as e:
        summary["notes"].append(f"playwright launch/scrape error: {type(e).__name__}: {e}")
        return 5, summary

    summary["events_total"] = len(all_events)
    live = [c for c in summary["channels"].values() if c.get("id")]
    if live and all(("error" in c) for c in live):
        return 3, summary
    if not all_events:
        summary["notes"].append("0 event-shaped messages found; leaving file untouched.")
        return 4, summary
    if dry_run:
        summary["ok"] = True
        summary["notes"].append("dry-run: file not written")
        return 0, summary

    week_key = f"{datetime.now().year}-W{datetime.now().isocalendar()[1]:02d}"
    payload = {
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "week": week_key,
        "channels": [f"#{n}" for n, c in CHANNELS.items() if c],
        "extraction_method": "slack_session",
        "events": all_events,
    }
    os.makedirs(config.DATA_DIR, exist_ok=True)
    tmp = BROWSER_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, BROWSER_JSON)
    summary["wrote_file"] = True
    summary["ok"] = True
    if os.path.exists(FLAG_FILE):
        try:
            os.remove(FLAG_FILE)
            summary["notes"].append("removed slack_browser_needed.flag")
        except OSError:
            pass
    return 0, summary


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    code, summ = run(dry_run=dry)
    print(json.dumps(summ, indent=2, ensure_ascii=False))
    sys.exit(code)
