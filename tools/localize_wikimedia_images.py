#!/usr/bin/env python3
"""
Localize all upload.wikimedia.org <img src="..."> references in docs/.

For each unique URL:
  1. Download to docs/blog/img/wikimedia/<safe-filename>
  2. Rewrite HTML to point at the relative local path

Files that 404 on Commons are logged to docs/blog/img/wikimedia/_failures.txt;
those <img> tags are left pointing at the original URL so the failure is visible
and a human can choose a replacement.

Idempotent: re-running skips files already on disk.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
LOCAL_DIR = DOCS / "blog" / "img" / "wikimedia"
FAILURES_PATH = REPO / "tools" / "wikimedia-localize-failures.txt"

USER_AGENT = (
    "TulsaGaysSiteLocalizer/1.0 "
    "(+https://tulsagays.com; admin@tulsagays.com) "
    "Python-urllib"
)

WIKI_SRC_RE = re.compile(
    r'src="(https://upload\.wikimedia\.org/wikipedia/commons/[^"]+)"'
)


def safe_filename(url: str) -> str:
    name = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    return re.sub(r"[^A-Za-z0-9._\-]", "_", name)


def download(url: str, dest: Path) -> tuple[bool, str]:
    # Retry transient errors (429 throttle, 5xx, network blips) with
    # exponential backoff. Wikimedia returns 429 readily on bursty traffic.
    delays = [2, 5, 15, 30]
    last_reason = "no attempt"
    for attempt, delay in enumerate([0] + delays):
        if delay:
            time.sleep(delay)
        req = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(req, timeout=30) as resp:
                data = resp.read()
            dest.write_bytes(data)
            return True, f"{len(data)} bytes (attempt {attempt + 1})"
        except HTTPError as e:
            last_reason = f"HTTP {e.code}"
            if e.code in (429, 500, 502, 503, 504):
                continue
            return False, last_reason
        except URLError as e:
            last_reason = f"URLError {e.reason}"
            continue
        except Exception as e:  # noqa: BLE001
            return False, f"{type(e).__name__}: {e}"
    return False, last_reason


def main() -> int:
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)

    html_files = sorted(DOCS.rglob("*.html"))
    print(f"Scanning {len(html_files)} HTML files under {DOCS}", flush=True)

    urls: set[str] = set()
    for hf in html_files:
        urls.update(WIKI_SRC_RE.findall(hf.read_text(encoding="utf-8")))
    print(f"Found {len(urls)} unique upload.wikimedia.org references", flush=True)

    url_to_local: dict[str, Path] = {}
    failures: list[tuple[str, str]] = []

    for url in sorted(urls):
        dest = LOCAL_DIR / safe_filename(url)
        if dest.exists() and dest.stat().st_size > 0:
            print(f"  skip   {dest.name}", flush=True)
            url_to_local[url] = dest
            continue

        print(f"  fetch  {url}", flush=True)
        ok, info = download(url, dest)
        if ok:
            print(f"         -> {dest.name} ({info})", flush=True)
            url_to_local[url] = dest
            time.sleep(2)  # be polite to Wikimedia
        else:
            print(f"         FAILED: {info}", flush=True)
            failures.append((url, info))
            if dest.exists():
                dest.unlink()

    rewritten = 0
    for hf in html_files:
        text = hf.read_text(encoding="utf-8")
        original = text
        for url, local_file in url_to_local.items():
            rel = os.path.relpath(local_file, hf.parent).replace(os.sep, "/")
            text = text.replace(f'src="{url}"', f'src="{rel}"')
        if text != original:
            hf.write_text(text, encoding="utf-8")
            rewritten += 1
            print(f"  rewrite {hf.relative_to(REPO)}", flush=True)

    if failures:
        FAILURES_PATH.write_text(
            "# Wikipedia Commons URLs that failed to download.\n"
            "# These <img> tags still point at the original (broken) URL —\n"
            "# pick a replacement on Commons and re-run.\n"
            + "\n".join(f"{url}\t{reason}" for url, reason in failures)
            + "\n",
            encoding="utf-8",
        )
    elif FAILURES_PATH.exists():
        FAILURES_PATH.unlink()

    print()
    print(f"Localized: {len(url_to_local)} images")
    print(f"HTML files rewritten: {rewritten}")
    if failures:
        print(f"FAILED: {len(failures)} images (see {FAILURES_PATH.relative_to(REPO)})")
        for url, reason in failures:
            print(f"  {reason}  {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
