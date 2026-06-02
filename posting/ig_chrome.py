"""
ig_chrome.py - drive the REAL Chrome (not a Playwright-launched one) via the
DevTools protocol, using a dedicated @tulsagays profile.

Why: Instagram blocks Playwright-launched browsers at login (the reCAPTCHA never
renders). Launching the genuine chrome.exe ourselves -- with its own user-data-dir
and --remote-debugging-port -- and then attaching with connect_over_cdp avoids the
automation fingerprint that triggers that wall. The login persists in the profile
dir, so unattended engage runs reuse it headlessly (chrome --headless=new).

The profile dir is OUTSIDE the synced vault and holds the session; no password is
ever stored by us.
"""
from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
IG_PROFILE_DIR = Path.home() / ".ig_profile_tulsagays"  # dedicated, NOT synced
PORT = 9333


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _cdp_endpoint(port: int, timeout: float = 25.0) -> str | None:
    """Poll the DevTools /json/version endpoint until Chrome is ready."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as r:
                json.loads(r.read().decode())  # ensure it's live
                return f"http://127.0.0.1:{port}"
        except Exception:
            time.sleep(0.6)
    return None


def kill_existing() -> None:
    """Kill any Chrome already using the dedicated IG profile (a leftover/stale one
    silently hijacks the debug port and makes login attach to an invisible window).
    Only touches the @tulsagays profile -- never the user's main Chrome."""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" -ErrorAction SilentlyContinue | "
             "Where-Object { $_.CommandLine -like '*ig_profile_tulsagays*' } | "
             "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
        )
        time.sleep(1.5)
    except Exception:
        pass


def launch_clean(url: str = "") -> subprocess.Popen | None:
    """Launch real Chrome on the IG profile with NO remote-debugging / automation
    flags. This is indistinguishable from a normal browser, so Instagram's login
    reCAPTCHA renders and works (the debug port is what makes it refuse to load).
    Used only for the interactive login; the session persists to the profile dir."""
    IG_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    kill_existing()
    if not Path(CHROME_EXE).exists():
        return None
    args = [CHROME_EXE, f"--user-data-dir={IG_PROFILE_DIR}",
            "--no-first-run", "--no-default-browser-check"]
    if url:
        args.append(url)
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def launch(headless: bool) -> tuple[subprocess.Popen | None, str | None]:
    """Launch a FRESH real Chrome with the IG profile + remote debugging.
    Returns (proc, cdp_url). Always starts clean (kills any stale IG-profile Chrome)
    so login reliably opens a real window instead of attaching to a stuck instance."""
    IG_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    kill_existing()
    if not Path(CHROME_EXE).exists():
        return None, None
    args = [
        CHROME_EXE,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={IG_PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-popup-blocking",
    ]
    if headless:
        args += ["--headless=new", "--disable-gpu", "--window-size=1280,900"]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    endpoint = _cdp_endpoint(PORT)
    return proc, endpoint


def kill(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception:
        pass
