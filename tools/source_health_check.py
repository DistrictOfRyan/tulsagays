"""
Source health pre-flight check for the Tulsa Gays event scraper.

Reads all SOURCES from config.py, tests each URL, then cross-references
the most recent data/events/*_all.json to show which sources contributed
0 events last week. Writes a summary to pending-william-actions.md and
prints the full report to stdout.

Level 2 (The Differ): persists each run to data/source_health_history/
and leads the report with a diff (newly broken / still broken / recovered).

Usage:
    python tools/source_health_check.py
    python tools/source_health_check.py --selftest
"""
import json
import os
import sys
import glob
import re
from datetime import datetime
from urllib.parse import urlparse, urlunparse

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
# Use a browser-like UA: a self-identifying bot UA gets 403/406 from anti-bot
# sites (Songkick, AXS, sometimes Ticketmaster/BOK), producing false-positive
# "dead source" flags every run. The real scraper fetches as a browser, so the
# health check should probe the same way to reflect true reachability.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
PENDING_ACTIONS_PATH = os.path.join(
    os.path.expanduser("~"), ".claude", "pending-william-actions.md"
)

FACEBOOK_DOMAINS = ("facebook.com", "fb.com", "fb.me")
SLACK_DOMAINS = ("slack.com",)
INSTAGRAM_DOMAINS = ("instagram.com",)

# Level 2: history persistence directory
HISTORY_DIR = os.path.join(_project_dir, "data", "source_health_history")

# Statuses that count as "broken" for diff purposes
_BROKEN = {"DEAD", "TIMEOUT", "REDIRECT_LOOP", "ERROR"}
# Statuses excluded from diff (auth/browser-required, not fixable via URL)
_SKIP_DIFF = {"SKIP", "BROWSER_REQUIRED", "NO_URL"}

# Level 3: URL variant triager constants
TIMEOUT_VARIANT = 5  # faster probe for candidate variant URLs
_VARIANT_PROBE_CODES = {404, 410}  # HTTP errors worth attempting URL variants for

# Level 4: Yield Monitor constants
YIELD_HISTORY_WEEKS = 6      # baseline window: weeks of *_all.json to read
YIELD_MIN_BASELINE_WEEKS = 2  # source must appear in ≥N history weeks to trigger alert

# ---------------------------------------------------------------------------
# Level 2 helpers: history + diff
# ---------------------------------------------------------------------------

def _get_week_key() -> str:
    """Return ISO week string like '2026-W28'."""
    n = datetime.now()
    return f"{n.year}-W{n.isocalendar()[1]:02d}"


def load_previous_run() -> dict:
    """
    Load the most recent history JSON.  Returns {} if none exists.
    Format: {source_key: {status, consecutive_failures}}
    """
    if not os.path.isdir(HISTORY_DIR):
        return {}
    files = sorted(glob.glob(os.path.join(HISTORY_DIR, "*.json")))
    if not files:
        return {}
    try:
        with open(files[-1], encoding="utf-8") as f:
            data = json.load(f)
        return data.get("sources", {})
    except Exception:
        return {}


def compute_diff(results: list, prev: dict) -> dict:
    """
    Compare current run to previous run.
    Returns dict with keys: newly_broken, still_broken, recovered.
    Each value is a list of (key, name, priority, status) tuples.
    """
    newly_broken, still_broken, recovered = [], [], []
    for r in results:
        key = r["key"]
        status = r["status"]
        if status in _SKIP_DIFF:
            continue
        prev_status = prev.get(key, {}).get("status", "OK")
        prev_broken = prev_status in _BROKEN
        now_broken = status in _BROKEN
        tup = (key, r["name"], r["priority"], status)
        if now_broken and not prev_broken:
            newly_broken.append(tup)
        elif now_broken and prev_broken:
            still_broken.append(tup)
        elif not now_broken and prev_broken:
            recovered.append(tup)
    return {
        "newly_broken": sorted(newly_broken, key=lambda x: x[2]),
        "still_broken": sorted(still_broken, key=lambda x: x[2]),
        "recovered": sorted(recovered, key=lambda x: x[2]),
    }


def save_run_history(results: list, prev: dict, week_key: str,
                     event_counts: dict | None = None):
    """
    Persist this run to HISTORY_DIR/<week_key>.json.
    Carries forward consecutive_failures from previous run.
    Optionally persists event_count per source (Level 4).
    """
    os.makedirs(HISTORY_DIR, exist_ok=True)
    sources = {}
    for r in results:
        key = r["key"]
        status = r["status"]
        prev_entry = prev.get(key, {})
        if status in _BROKEN:
            consec = prev_entry.get("consecutive_failures", 0) + 1
        else:
            consec = 0
        entry = {
            "status": status,
            "priority": r["priority"],
            "consecutive_failures": consec,
        }
        if event_counts is not None:
            entry["event_count"] = event_counts.get(key, 0)
        sources[key] = entry
    out = {
        "week": week_key,
        "run_ts": datetime.now().isoformat(timespec="seconds"),
        "sources": sources,
    }
    path = os.path.join(HISTORY_DIR, f"{week_key}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    return path


# ---------------------------------------------------------------------------
# Level 3 helpers: URL variant triager
# ---------------------------------------------------------------------------

def _generate_url_variants(url: str) -> list:
    """
    Generate candidate URL variants to probe when a source returns 404/410.
    Tries: scheme toggle, www toggle, trailing-slash toggle, calendar path
    swaps, and bare domain root.  Returns deduplicated list (original
    excluded), capped at 6 so wall-clock stays bounded.
    """
    variants = []
    u = url.strip()
    try:
        parsed = urlparse(u)
    except Exception:
        return []
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc
    path = parsed.path

    # 1. Scheme toggle
    if scheme == "http":
        variants.append(urlunparse(parsed._replace(scheme="https")))
    elif scheme == "https":
        variants.append(urlunparse(parsed._replace(scheme="http")))

    # 2. WWW toggle
    if netloc.startswith("www."):
        variants.append(urlunparse(parsed._replace(netloc=netloc[4:])))
    elif netloc:
        variants.append(urlunparse(parsed._replace(netloc="www." + netloc)))

    # 3. Trailing slash toggle (skip root paths)
    if path not in ("", "/"):
        if path.endswith("/"):
            variants.append(urlunparse(parsed._replace(path=path.rstrip("/"))))
        else:
            variants.append(urlunparse(parsed._replace(path=path + "/")))

    # 4. Calendar path swaps — most event sites use one of these
    _CAL_ALTS = [
        ("/events", "/event-calendar"),
        ("/event-calendar", "/events"),
        ("/calendar", "/events"),
        ("/events/", "/event-calendar/"),
        ("/event-calendar/", "/events/"),
        ("/calendar/", "/events/"),
    ]
    for suffix, alt in _CAL_ALTS:
        if path == suffix or path.endswith(suffix):
            base = "" if path == suffix else path[: len(path) - len(suffix)]
            variants.append(urlunparse(parsed._replace(path=base + alt)))

    # 5. Domain root — verify the site is alive at all
    if path not in ("", "/"):
        variants.append(urlunparse(parsed._replace(path="/")))

    seen = {u}
    result = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result[:6]


def try_url_variants(url: str, check_fn=None) -> str | None:
    """
    Probe URL variants for a 404/410 source and return the first one that
    responds with an HTTP 200.  Returns None if no variant succeeds.
    Never modifies any config or source file — probes only.

    check_fn(url: str) -> str  accepts a URL and returns "OK" if the URL
    is reachable, anything else otherwise.  Defaults to a requests.get
    probe with TIMEOUT_VARIANT.  Injectable for unit-testing without
    network calls.
    """
    if check_fn is None:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        def check_fn(u):
            try:
                resp = requests.get(u, headers=headers, timeout=TIMEOUT_VARIANT,
                                    allow_redirects=True, stream=True)
                resp.raw.read(256)
                return "OK" if resp.status_code < 400 else "FAIL"
            except Exception:
                return "FAIL"

    for variant in _generate_url_variants(url):
        try:
            if check_fn(variant) == "OK":
                return variant
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Level 4 helpers: Yield Monitor
# ---------------------------------------------------------------------------

def load_event_count_history(n_weeks: int = YIELD_HISTORY_WEEKS,
                              events_dir: str | None = None) -> dict:
    """
    Load per-source event counts from the last n_weeks *_all.json files,
    excluding the most recent file (which is the current run's data).
    Returns {week_key: {source_key: count}}.

    events_dir is injectable for tests; defaults to EVENTS_DIR from config.
    """
    edir = events_dir if events_dir is not None else EVENTS_DIR
    files = sorted(glob.glob(os.path.join(edir, "*_all.json")))
    # Exclude the most recent file (current week) so baseline != current run
    history_files = files[:-1] if len(files) > 1 else []
    # Take the last n_weeks
    history_files = history_files[-n_weeks:]

    result = {}
    for fpath in history_files:
        fname = os.path.basename(fpath)
        week_key = fname.replace("_all.json", "")
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        events = data.get("events", []) if isinstance(data, dict) else data
        counts: dict = {}
        for evt in events:
            src = evt.get("source", "").strip()
            if src:
                counts[src] = counts.get(src, 0) + 1
        result[week_key] = counts
    return result


def compute_yield_baseline(history: dict) -> dict:
    """
    From {week_key: {source: count}}, compute per-source stats:
      avg_events: mean count across weeks where source appeared (count > 0)
      weeks_with_data: how many weeks had ≥1 event from this source
      max_events: peak single-week count
    Returns {source_key: {avg_events, weeks_with_data, max_events}}.
    """
    source_counts: dict = {}  # source -> list of nonzero counts
    for counts in history.values():
        for src, count in counts.items():
            if count > 0:
                source_counts.setdefault(src, []).append(count)

    baseline = {}
    for src, count_list in source_counts.items():
        baseline[src] = {
            "avg_events": sum(count_list) / len(count_list),
            "weeks_with_data": len(count_list),
            "max_events": max(count_list),
        }
    return baseline


def detect_yield_collapse(current_counts: dict, baseline: dict,
                          min_baseline_weeks: int = YIELD_MIN_BASELINE_WEEKS) -> list:
    """
    Return sources whose yield has collapsed to 0 this week.
    A collapse = source averaged ≥1 event/week over ≥min_baseline_weeks weeks
    AND this week's count is 0.
    Returns list of (source_key, avg_events, max_events, weeks_with_data),
    sorted by avg_events descending (biggest losses first).
    """
    collapsed = []
    for src, stats in baseline.items():
        if stats["weeks_with_data"] < min_baseline_weeks:
            continue  # too sparse: could be a one-off, not a collapse
        if stats["avg_events"] < 1.0:
            continue  # source never reliably produced events
        if current_counts.get(src, 0) == 0:
            collapsed.append((
                src,
                stats["avg_events"],
                stats["max_events"],
                stats["weeks_with_data"],
            ))
    return sorted(collapsed, key=lambda x: -x[1])


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
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    result = {"url": url, "status": None, "code": None, "final_url": None, "note": ""}

    # Try HEAD first
    try:
        resp = requests.head(url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
        result["code"] = resp.status_code
        result["final_url"] = resp.url
        if resp.status_code < 400:
            result["status"] = "OK"
        else:
            # HEAD is unreliable: many sites reject it with 403/405/406 while
            # serving GET fine. Leave status unset so the GET fallback below
            # makes the authoritative call before we declare an ERROR.
            pass
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

    # Fall back to GET whenever HEAD did not conclusively succeed (any HTTP
    # >=400 left status unset). Connection/timeout errors set a terminal status
    # above and are NOT retried here, to avoid doubling wall-clock on dead hosts.
    if result["status"] is None:
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
            elif resp.status_code in (401, 403, 406, 429):
                # Server is up but refusing automated clients (anti-bot /
                # auth wall). This is materially different from a 404/410:
                # the URL is fine, the site just blocks bots. Bucketed
                # separately so "HTTP ERRORS" stays a fix-the-URL signal.
                result["status"] = "BLOCKED"
                result["note"] = f"HTTP {resp.status_code} (anti-bot / auth wall)"
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

    # *_all.json is a flat list of event dicts. Stay tolerant of an older
    # {"events": [...]} wrapper shape just in case.
    if isinstance(data, dict):
        events = data.get("events", [])
    else:
        events = data
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
            "proposed_fix": None,
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

        # Level 3: for 404/410 errors try common URL variants (propose only)
        if entry["status"] == "ERROR" and entry.get("code") in _VARIANT_PROBE_CODES:
            fix = try_url_variants(url)
            if fix:
                entry["proposed_fix"] = fix

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


def build_summary_lines(results: list, week_file: str, diff: dict | None = None,
                        yield_collapsed: list | None = None) -> list:
    """Build the bullet list for the pending-william-actions.md entry."""
    lines = []

    dead = [r for r in results if r["status"] in ("DEAD", "TIMEOUT", "REDIRECT_LOOP")]
    errors = [r for r in results if r["status"] == "ERROR"]
    blocked = [r for r in results if r["status"] == "BLOCKED"]
    no_url = [r for r in results if r["status"] == "NO_URL"]
    zero_events = [
        r for r in results
        if r["status"] == "OK" and r["event_count"] == 0 and week_file != "none found"
    ]
    ok_with_events = [r for r in results if r["status"] == "OK" and r["event_count"] > 0]
    skipped = [r for r in results if r["status"] == "SKIP"]

    # Level 2: lead with diff when available
    if diff is not None:
        nb = diff["newly_broken"]
        sb = diff["still_broken"]
        rec = diff["recovered"]
        lines.append(
            f"DIFF vs last run: {len(nb)} newly broken, "
            f"{len(sb)} still broken, "
            f"{len(rec)} recovered"
        )
        if nb:
            lines.append("  Newly broken: " + ", ".join(
                f"{k} (P{p})" for k, _n, p, _s in nb
            ))
        if rec:
            lines.append("  Recovered: " + ", ".join(
                f"{k}" for k, _n, p, _s in rec
            ))
        lines.append("")

    lines.append(f"Cross-referenced against: {week_file}")
    lines.append(
        f"Summary: {len(ok_with_events)} OK with events, "
        f"{len(zero_events)} reachable but 0 events last week, "
        f"{len(dead)} dead/timeout, "
        f"{len(errors)} HTTP errors, "
        f"{len(blocked)} blocked (anti-bot), "
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
        lines.append("HTTP ERRORS (broken URL -- fix or retire):")
        for r in sorted(errors, key=lambda x: x["priority"]):
            lines.append(
                f"  - {r['name']} [{r['key']}] P{r['priority']}: {r['note']}"
            )

    if blocked:
        lines.append("")
        lines.append("BLOCKED -- anti-bot / auth wall (URL fine, needs browser; low-priority):")
        for r in sorted(blocked, key=lambda x: x["priority"]):
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

    # Level 3: proposed URL fixes (auto-detected variant, not applied)
    proposed = [r for r in results if r.get("proposed_fix")]
    if proposed:
        lines.append("")
        lines.append("PROPOSED URL FIXES (auto-detected -- update SOURCES to apply, not done yet):")
        for r in sorted(proposed, key=lambda x: x["priority"]):
            lines.append(
                f"  - {r['name']} [{r['key']}] P{r['priority']}: "
                f"try {r['proposed_fix']}"
            )

    # Level 4: yield collapse (source was producing events, now 0 this week)
    if yield_collapsed:
        lines.append("")
        lines.append("YIELD COLLAPSE (URL alive but 0 events this week vs. historical baseline):")
        for src, avg, mx, weeks in yield_collapsed:
            lines.append(
                f"  - {src}: avg {avg:.1f} events/wk over {weeks} weeks "
                f"(peak {mx}) -> 0 this week. Selector may have broken."
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


def _run_selftest() -> int:
    """
    Level 2 + Level 3 selftest: history persist + diff + URL variant triager.
    No network calls. Returns 0 on pass, 1 on fail.
    """
    import tempfile, shutil
    fails = []
    tmp = tempfile.mkdtemp()
    orig_history = os.environ.get("_SHC_HISTORY_OVERRIDE")
    # Monkey-patch HISTORY_DIR for the test
    import tools.source_health_check as _self  # noqa: F401 (self-ref for patch)
    original_dir = _self.HISTORY_DIR
    _self.HISTORY_DIR = tmp

    try:
        # Build fake results representing a first run
        fake_results = [
            {"key": "venue_a", "name": "Venue A", "priority": 1, "status": "OK",
             "event_count": 5, "code": 200, "final_url": "", "note": "", "skip_reason": None},
            {"key": "venue_b", "name": "Venue B", "priority": 2, "status": "DEAD",
             "event_count": 0, "code": None, "final_url": None, "note": "dns fail", "skip_reason": None},
        ]
        wk = "2026-TEST1"
        path = _self.save_run_history(fake_results, {}, wk)
        if not os.path.isfile(path):
            fails.append("save_run_history: file not created")
        prev = _self.load_previous_run()
        if prev.get("venue_b", {}).get("status") != "DEAD":
            fails.append(f"load_previous_run: expected venue_b DEAD, got {prev.get('venue_b')}")
        if prev.get("venue_b", {}).get("consecutive_failures", 0) != 1:
            fails.append(f"consecutive_failures: expected 1 for venue_b, got {prev.get('venue_b',{}).get('consecutive_failures')}")

        # Second run: venue_a breaks, venue_b recovers
        fake2 = [
            {"key": "venue_a", "name": "Venue A", "priority": 1, "status": "TIMEOUT",
             "event_count": 0, "code": None, "final_url": None, "note": "", "skip_reason": None},
            {"key": "venue_b", "name": "Venue B", "priority": 2, "status": "OK",
             "event_count": 3, "code": 200, "final_url": "", "note": "", "skip_reason": None},
        ]
        diff = _self.compute_diff(fake2, prev)
        if len(diff["newly_broken"]) != 1 or diff["newly_broken"][0][0] != "venue_a":
            fails.append(f"compute_diff newly_broken: expected [venue_a], got {diff['newly_broken']}")
        if len(diff["recovered"]) != 1 or diff["recovered"][0][0] != "venue_b":
            fails.append(f"compute_diff recovered: expected [venue_b], got {diff['recovered']}")
        if diff["still_broken"]:
            fails.append(f"compute_diff still_broken: expected [], got {diff['still_broken']}")

        # Save second run and verify consecutive_failures resets for venue_b
        wk2 = "2026-TEST2"
        path2 = _self.save_run_history(fake2, prev, wk2)
        prev2 = _self.load_previous_run()
        if prev2.get("venue_b", {}).get("consecutive_failures", -1) != 0:
            fails.append(f"consecutive_failures reset: expected 0 for venue_b after recovery")
        if prev2.get("venue_a", {}).get("consecutive_failures", 0) != 1:
            fails.append(f"consecutive_failures: expected 1 for venue_a on first timeout")

        # Level 3: _generate_url_variants produces expected candidates
        variants_http = _self._generate_url_variants("http://example.com/events")
        if "https://example.com/events" not in variants_http:
            fails.append("_generate_url_variants: https scheme toggle missing")
        if "http://example.com/events/" not in variants_http:
            fails.append("_generate_url_variants: trailing slash toggle missing")

        # Level 3: try_url_variants uses injectable check_fn (no real network)
        def _mock_ok_calendar(u):
            return "OK" if "/event-calendar" in u else "FAIL"
        fix = _self.try_url_variants("http://example.com/events", check_fn=_mock_ok_calendar)
        if fix != "http://example.com/event-calendar":
            fails.append(f"try_url_variants found: expected .../event-calendar, got {fix!r}")
        no_fix = _self.try_url_variants("http://example.com/events", check_fn=lambda u: "FAIL")
        if no_fix is not None:
            fails.append(f"try_url_variants None: expected None, got {no_fix!r}")

        # Level 4: compute_yield_baseline from fake history
        fake_history = {
            "2026-W24": {"source_alpha": 10, "source_beta": 5},
            "2026-W25": {"source_alpha": 8, "source_beta": 0, "source_gamma": 2},
            "2026-W26": {"source_alpha": 12, "source_gamma": 3},
        }
        baseline = _self.compute_yield_baseline(fake_history)
        # source_alpha appeared all 3 weeks: avg (10+8+12)/3 = 10.0
        if abs(baseline.get("source_alpha", {}).get("avg_events", 0) - 10.0) > 0.01:
            fails.append(f"compute_yield_baseline source_alpha avg: expected 10.0, got {baseline.get('source_alpha',{}).get('avg_events')}")
        # source_beta appeared 1 week (week W25 count=0 excluded, W24 count=5): avg=5.0, weeks=1
        if baseline.get("source_beta", {}).get("weeks_with_data", 0) != 1:
            fails.append(f"compute_yield_baseline source_beta weeks_with_data: expected 1, got {baseline.get('source_beta',{}).get('weeks_with_data')}")
        # source_gamma appeared 2 weeks: max=3
        if baseline.get("source_gamma", {}).get("max_events", 0) != 3:
            fails.append(f"compute_yield_baseline source_gamma max_events: expected 3, got {baseline.get('source_gamma',{}).get('max_events')}")

        # Level 4: detect_yield_collapse
        # source_alpha: avg=10, weeks=3, current=0 -> collapse (above min_baseline_weeks=2)
        # source_beta: avg=5, weeks=1, current=3 -> no collapse (1 week < min=2 AND not 0)
        # source_gamma: avg=2.5, weeks=2, current=0 -> collapse (meets min and goes to 0)
        current = {"source_alpha": 0, "source_beta": 3}  # gamma not in current -> 0
        collapsed = _self.detect_yield_collapse(current, baseline, min_baseline_weeks=2)
        collapsed_keys = [c[0] for c in collapsed]
        if "source_alpha" not in collapsed_keys:
            fails.append(f"detect_yield_collapse: expected source_alpha collapsed, got {collapsed_keys}")
        if "source_beta" in collapsed_keys:
            fails.append("detect_yield_collapse: source_beta should NOT collapse (only 1 baseline week)")
        if "source_gamma" not in collapsed_keys:
            fails.append(f"detect_yield_collapse: expected source_gamma collapsed (avg=2.5, 2wks, current=0), got {collapsed_keys}")
        # sorted by avg_events descending: source_alpha (10) first
        if len(collapsed_keys) >= 2 and collapsed_keys[0] != "source_alpha":
            fails.append(f"detect_yield_collapse sort: expected source_alpha first (avg=10), got {collapsed_keys[0]!r}")

        # Level 4: load_event_count_history with injectable events_dir (no real network)
        fake_events_dir = os.path.join(tmp, "events")
        os.makedirs(fake_events_dir, exist_ok=True)
        import json as _json
        # Write two history weeks + one "current" (latest) that should be excluded
        _json.dump([{"source": "venue_x", "title": "e1"}, {"source": "venue_x", "title": "e2"}],
                   open(os.path.join(fake_events_dir, "2026-W10_all.json"), "w"))
        _json.dump([{"source": "venue_x", "title": "e3"}, {"source": "venue_y", "title": "e4"}],
                   open(os.path.join(fake_events_dir, "2026-W11_all.json"), "w"))
        _json.dump([{"source": "venue_z", "title": "current"}],
                   open(os.path.join(fake_events_dir, "2026-W12_all.json"), "w"))  # latest, excluded
        hist = _self.load_event_count_history(n_weeks=6, events_dir=fake_events_dir)
        if "2026-W12" in hist:
            fails.append("load_event_count_history: current week (W12) must be excluded from baseline")
        if hist.get("2026-W10", {}).get("venue_x", 0) != 2:
            fails.append(f"load_event_count_history: expected venue_x=2 in W10, got {hist.get('2026-W10', {})}")
        if hist.get("2026-W11", {}).get("venue_y", 0) != 1:
            fails.append(f"load_event_count_history: expected venue_y=1 in W11, got {hist.get('2026-W11', {})}")

        # 8 (L2) + 4 (L3) + 3 (L4 baseline) + 4 (L4 collapse) + 3 (L4 history) = 22
        total_checks = 22
        print(f"  selftest: {total_checks - len(fails)}/{total_checks} checks pass")
        for f in fails:
            print(f"  FAIL: {f}")
    finally:
        _self.HISTORY_DIR = original_dir
        shutil.rmtree(tmp, ignore_errors=True)

    return 0 if not fails else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(_run_selftest())

    # Level 2: load previous run for diff
    prev = load_previous_run()
    week_key = _get_week_key()

    results, week_file = run()

    # Level 4: load yield history and detect collapses before saving this run
    yield_history = load_event_count_history()
    yield_baseline = compute_yield_baseline(yield_history)
    # event_counts comes from run() via load_recent_event_sources() called inside run()
    # Re-load it here to pass to detect_yield_collapse and save_run_history
    event_result = load_recent_event_sources()
    current_event_counts = event_result[0] if event_result else {}
    yield_collapsed = detect_yield_collapse(current_event_counts, yield_baseline)
    if yield_collapsed:
        print(f"\n[L4] Yield collapse detected in {len(yield_collapsed)} source(s):")
        for src, avg, mx, weeks in yield_collapsed:
            print(f"     {src}: avg {avg:.1f}/wk over {weeks}wk (peak {mx}) -> 0 this week")

    # Level 2: compute diff and persist history (Level 4: also saves event_count)
    diff = compute_diff(results, prev)
    history_path = save_run_history(results, prev, week_key, event_counts=current_event_counts)
    print(f"\n[L2/L4] History saved: {history_path}")

    # Print summary section
    print("\n" + "=" * 68)
    print("SUMMARY")
    print("=" * 68)
    summary_lines = build_summary_lines(results, week_file, diff=diff,
                                        yield_collapsed=yield_collapsed)
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
