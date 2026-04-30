"""
Source health pre-flight check for the Tulsa Gays event scraper.

Reads all SOURCES from config.py, tests each URL, then cross-references
the most recent data/events/*_all.json to show which sources contributed
0 events last week. Writes a summary to pending-william-actions.md and
prints the full report to stdout.

Usage:
    python tools/source_health_check.py
"""
import json
import os
import sys
import glob
import re
from datetime import datetime

# Allow running from repo root or from tools/ subdirectory
_this_dir = os.path.dirname(os.path.abspath(__file__))
_project_dir = os.path.dirname(_this_dir)
if _project_dir not in sys.path:
    sys.path.insert(0, _project_dir)

import requests
from config import SOURCES, EVENTS_DIR

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TIMEOUT = 10
USER_AGENT = (
    "Mozilla/5.0 (compatible; TulsaGays-HealthCheck/1.0; "
    "+https://www.tulsagays.com)"
)
PENDING_ACTIONS_PATH = os.path.join(
    os.path.expanduser("~"), ".claude", "pending-william-actions.md"
)

FACEBOOK_DOMAINS = ("facebook.com", "fb.com", "fb.me")
SLACK_DOMAINS = ("slack.com",)
INSTAGRAM_DOMAINS = ("instagram.com",)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _domain_of(url: str) -> str:
    """Return the bare domain (lowercase) from a URL string."""
    url = url.strip().lower()
    # Strip scheme
    for scheme in ("https://", "http://"):
        if url.startswith(scheme):
            url = url[len(scheme):]
    # Strip path
    return url.split("/")[0]


def _is_facebook(url: str) -> bool:
    d = _domain_of(url)
    return any(d == fb or d.endswith("." + fb) for fb in FACEBOOK_DOMAINS)


def _is_slack(url: str) -> bool:
    d = _domain_of(url)
    return any(d == sl or d.endswith("." + sl) for sl in SLACK_DOMAINS)


def _is_instagram(url: str) -> bool:
    d = _domain_of(url)
    return any(d == ig or d.endswith("." + ig) for ig in INSTAGRAM_DOMAINS)


def check_url(url: str) -> dict:
    """
    Attempt a HEAD request, fall back to GET on failure.
    Returns a dict with: status, code, final_url, note.
    """
    headers = {"User-Agent": USER_AGENT}
    result = {"url": url, "status": None, "code": None, "final_url": None, "note": ""}

    # Try HEAD first
    try:
        resp = requests.head(url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
        result["code"] = resp.status_code
        result["final_url"] = resp.url
        if resp.status_code < 400:
            result["status"] = "OK"
        elif resp.status_code == 405:
            # Server does not allow HEAD - fall through to GET
            pass
        else:
            result["status"] = "ERROR"
            result["note"] = f"HTTP {resp.status_code}"
    except requests.exceptions.ConnectionError:
        result["status"] = "DEAD"
        result["note"] = "connection refused / DNS failure"
    except requests.exceptions.Timeout:
        result["status"] = "TIMEOUT"
        result["note"] = f"no response within {TIMEOUT}s"
    except requests.exceptions.TooManyRedirects:
        result["status"] = "REDIRECT_LOOP"
        result["note"] = "redirect loop"
    except Exception as exc:
        result["status"] = "ERROR"
        result["note"] = str(exc)[:120]

    # Fall back to GET if HEAD failed or returned 405
    if result["status"] is None or result["code"] == 405:
        try:
            resp = requests.get(
                url, headers=headers, timeout=TIMEOUT,
                allow_redirects=True, stream=True
            )
            # Read a tiny bit so we don't time out on large pages
            _ = resp.raw.read(512)
            result["code"] = resp.status_code
            result["final_url"] = resp.url
            if resp.status_code < 400:
                result["status"] = "OK"
            else:
                result["status"] = "ERROR"
                result["note"] = f"HTTP {resp.status_code}"
        except requests.exceptions.ConnectionError:
            result["status"] = "DEAD"
            result["note"] = "connection refused / DNS failure"
        except requests.exceptions.Timeout:
            result["status"] = "TIMEOUT"
            result["note"] = f"no response within {TIMEOUT}s"
        except requests.exceptions.TooManyRedirects:
            result["status"] = "REDIRECT_LOOP"
            result["note"] = "redirect loop"
        except Exception as exc:
            result["status"] = "ERROR"
            result["note"] = str(exc)[:120]

    return result


def load_recent_event_sources() -> dict:
    """
    Load the most recent *_all.json file from EVENTS_DIR and return a
    dict mapping source_key -> event_count for that week.
    """
    pattern = os.path.join(EVENTS_DIR, "*_all.json")
    files = sorted(glob.glob(pattern))
    if not files:
        return {}

    latest = files[-1]
    try:
        with open(latest, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    events = data.get("events", [])
    counts = {}
    for evt in events:
        src = evt.get("source", "").strip()
        if src:
            counts[src] = counts.get(src, 0) + 1

    return counts, os.path.basename(latest)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> list:
    """Run the health check and return a list of result dicts."""
    print("=" * 68)
    print("TULSA GAYS SOURCE HEALTH CHECK")
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 68)

    # Load recent event counts
    event_result = load_recent_event_sources()
    if event_result:
        event_counts, week_file = event_result
        print(f"\nCross-referencing against: {week_file}")
    else:
        event_counts = {}
        week_file = "none found"
        print("\nNo recent *_all.json found - skipping event count cross-reference.")

    print(f"\nTesting {len(SOURCES)} sources (10s timeout each)...\n")

    results = []

    for key, src in SOURCES.items():
        name = src.get("name", key)
        url = src.get("url", "").strip()
        priority = src.get("priority", 3)
        evt_count = event_counts.get(key, 0)

        entry = {
            "key": key,
            "name": name,
            "url": url,
            "priority": priority,
            "event_count": evt_count,
            "status": None,
            "code": None,
            "final_url": None,
            "note": "",
            "skip_reason": None,
        }

        # No URL configured
        if not url:
            entry["status"] = "NO_URL"
            entry["note"] = "no URL configured"
            _print_row(entry)
            results.append(entry)
            continue

        # Skip Facebook
        if _is_facebook(url):
            entry["status"] = "SKIP"
            entry["skip_reason"] = "Facebook"
            entry["note"] = "SKIP (Facebook - requires auth)"
            _print_row(entry)
            results.append(entry)
            continue

        # Slack — REQUIRED via browser (Claude-in-Chrome), never truly skipped
        if _is_slack(url):
            entry["status"] = "BROWSER_REQUIRED"
            entry["skip_reason"] = "Slack"
            entry["note"] = "BROWSER_REQUIRED (Slack - use Claude-in-Chrome, NOT skippable)"
            _print_row(entry)
            results.append(entry)
            continue

        # Skip Instagram (login wall)
        if _is_instagram(url):
            entry["status"] = "SKIP"
            entry["skip_reason"] = "Instagram"
            entry["note"] = "SKIP (Instagram - login wall)"
            _print_row(entry)
            results.append(entry)
            continue

        # Test the URL
        check = check_url(url)
        entry["status"] = check["status"]
        entry["code"] = check["code"]
        entry["final_url"] = check["final_url"]
        entry["note"] = check["note"]

        # If OK but 0 events last week, flag it
        if entry["status"] == "OK" and evt_count == 0 and week_file != "none found":
            entry["note"] = (entry["note"] + " | 0 events last week").strip(" |")

        _print_row(entry)
        results.append(entry)

    return results, week_file


def _print_row(entry: dict):
    status = entry["status"]
    key = entry["key"]
    name = entry["name"]
    code = f" [{entry['code']}]" if entry.get("code") else ""
    note = f" -- {entry['note']}" if entry.get("note") else ""
    evt = f" ({entry['event_count']} events)" if entry["status"] not in ("SKIP", "NO_URL") else ""
    print(f"  [{status:10s}] {key:<35} {name[:40]}{code}{evt}{note}")


def build_summary_lines(results: list, week_file: str) -> list:
    """Build the bullet list for the pending-william-actions.md entry."""
    lines = []

    dead = [r for r in results if r["status"] in ("DEAD", "TIMEOUT", "REDIRECT_LOOP")]
    errors = [r for r in results if r["status"] == "ERROR"]
    no_url = [r for r in results if r["status"] == "NO_URL"]
    zero_events = [
        r for r in results
        if r["status"] == "OK" and r["event_count"] == 0 and week_file != "none found"
    ]
    ok_with_events = [r for r in results if r["status"] == "OK" and r["event_count"] > 0]
    skipped = [r for r in results if r["status"] == "SKIP"]

    lines.append(f"Cross-referenced against: {week_file}")
    lines.append(
        f"Summary: {len(ok_with_events)} OK with events, "
        f"{len(zero_events)} reachable but 0 events last week, "
        f"{len(dead)} dead/timeout, "
        f"{len(errors)} HTTP errors, "
        f"{len(no_url)} no URL configured, "
        f"{len(skipped)} skipped (FB/Slack/IG)"
    )

    if dead:
        lines.append("")
        lines.append("DEAD / TIMEOUT (need attention):")
        for r in sorted(dead, key=lambda x: x["priority"]):
            lines.append(
                f"  - {r['name']} [{r['key']}] P{r['priority']}: "
                f"{r['status']} -- {r['note']}"
            )

    if errors:
        lines.append("")
        lines.append("HTTP ERRORS:")
        for r in sorted(errors, key=lambda x: x["priority"]):
            lines.append(
                f"  - {r['name']} [{r['key']}] P{r['priority']}: {r['note']}"
            )

    # Only flag zero-event sources for priority 1 and 2 (skip P3 noise)
    high_zero = [r for r in zero_events if r["priority"] <= 2]
    if high_zero:
        lines.append("")
        lines.append("REACHABLE BUT 0 EVENTS LAST WEEK (P1/P2 only):")
        for r in sorted(high_zero, key=lambda x: (x["priority"], x["key"])):
            lines.append(
                f"  - {r['name']} [{r['key']}] P{r['priority']}: URL OK, got nothing last week"
            )

    if no_url:
        lines.append("")
        lines.append("NO URL CONFIGURED:")
        for r in sorted(no_url, key=lambda x: x["priority"]):
            lines.append(
                f"  - {r['name']} [{r['key']}] P{r['priority']}: no URL -- {r.get('description', '')[:60]}"
            )

    return lines


def append_to_pending_actions(summary_lines: list):
    """Append the health check results to pending-william-actions.md."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"## [{timestamp}] Tulsa Gays Source Health Check"
    block = header + "\n" + "\n".join(f"- {line}" for line in summary_lines) + "\n\n"

    try:
        # Read existing content
        if os.path.exists(PENDING_ACTIONS_PATH):
            with open(PENDING_ACTIONS_PATH, encoding="utf-8") as f:
                existing = f.read()
        else:
            existing = ""

        with open(PENDING_ACTIONS_PATH, "a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(block)

        print(f"\nSummary appended to: {PENDING_ACTIONS_PATH}")
    except Exception as exc:
        print(f"\nWARNING: Could not write to pending-william-actions.md: {exc}")


def main():
    results, week_file = run()

    # Print summary section
    print("\n" + "=" * 68)
    print("SUMMARY")
    print("=" * 68)
    summary_lines = build_summary_lines(results, week_file)
    for line in summary_lines:
        print(line)

    # Write to pending-william-actions.md
    append_to_pending_actions(summary_lines)

    # Exit with non-zero code if any P1 sources are dead
    dead_keys = {r["key"] for r in results if r["status"] in ("DEAD", "TIMEOUT")}
    p1_dead = [
        r for r in results
        if r["key"] in dead_keys and r["priority"] == 1
    ]
    if p1_dead:
        print(
            f"\nEXIT 1: {len(p1_dead)} priority-1 source(s) unreachable. "
            "Scraper may produce incomplete results."
        )
        sys.exit(1)

    print("\nHealth check complete.")
    sys.exit(0)


if __name__ == "__main__":
    main()
