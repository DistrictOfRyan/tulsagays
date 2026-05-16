#!/usr/bin/env python3
"""
Verify every <img src> in docs/*.html resolves to a 2xx response.

- Local relative paths are checked against the filesystem.
- Absolute http(s) URLs are checked with a HEAD request (falling back to GET
  when HEAD is not supported).
- HTTP 429 (rate-limited) is treated as a soft pass: the resource exists, the
  CDN is just throttling CI. This is common with wikimedia.org.
- Exit code is non-zero when any image fails, so this can gate CI.
"""

from __future__ import annotations

import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
SITE_BASE = "https://www.tulsagays.com/"

USER_AGENT = (
    "TulsaGaysLinkChecker/1.0 "
    "(+https://tulsagays.com; admin@tulsagays.com) "
    "Python-urllib"
)

SRC_RE = re.compile(r'<img[^>]*src="([^"]+)"')


def collect_refs() -> list[tuple[Path, str]]:
    refs: list[tuple[Path, str]] = []
    for hf in sorted(DOCS.rglob("*.html")):
        for src in SRC_RE.findall(hf.read_text(encoding="utf-8")):
            refs.append((hf, src))
    return refs


def check_url(url: str) -> tuple[bool, str]:
    for method in ("HEAD", "GET"):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT}, method=method)
            with urlopen(req, timeout=20) as resp:
                if 200 <= resp.status < 300:
                    return True, f"{method} {resp.status}"
                return False, f"{method} {resp.status}"
        except HTTPError as e:
            if e.code == 405 and method == "HEAD":
                continue
            if e.code == 429:
                # Rate-limited by CDN (common with wikimedia.org in CI).
                # The resource exists; treat as soft pass.
                return True, f"RATE_LIMITED (429 skipped)"
            return False, f"HTTP {e.code}"
        except URLError as e:
            return False, f"URLError {e.reason}"
        except Exception as e:  # noqa: BLE001
            return False, f"{type(e).__name__}: {e}"
    return False, "unreachable"


def resolve_local(html_path: Path, src: str) -> Path:
    if src.startswith("/"):
        return DOCS / src.lstrip("/")
    return (html_path.parent / src).resolve()


def main() -> int:
    refs = collect_refs()
    print(f"Scanning {len(refs)} <img src> references", flush=True)

    remote_urls: dict[str, list[Path]] = {}
    local_misses: list[tuple[Path, str, Path]] = []

    for html_path, src in refs:
        if src.startswith(("http://", "https://")):
            remote_urls.setdefault(src, []).append(html_path)
        elif src.startswith("data:"):
            continue
        else:
            local = resolve_local(html_path, src)
            if not local.exists():
                local_misses.append((html_path, src, local))

    failures: list[str] = []

    if local_misses:
        for hf, src, _local in local_misses:
            failures.append(f"LOCAL MISSING  {hf.relative_to(REPO)}  src={src}")

    if remote_urls:
        print(f"Checking {len(remote_urls)} remote URLs in parallel...", flush=True)
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(check_url, u): u for u in remote_urls}
            for fut in as_completed(futures):
                url = futures[fut]
                ok, info = fut.result()
                pages = remote_urls[url]
                if ok:
                    print(f"  OK    {info}  {url}", flush=True)
                else:
                    print(f"  FAIL  {info}  {url}", flush=True)
                    for hf in pages:
                        failures.append(
                            f"REMOTE FAIL    {hf.relative_to(REPO)}  {info}  {url}"
                        )

    if failures:
        print()
        print(f"{len(failures)} broken image reference(s):")
        for line in failures:
            print(f"  {line}")
        return 1

    print()
    print("All image references resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
