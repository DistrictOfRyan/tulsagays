"""
ig_media_guard.py - prove every Instagram asset is real, Instagram-acceptable
image bytes at a public URL BEFORE the Graph API /media container call.

WHY THIS EXISTS (2026-10-07, repair queue 1d31a20d039a)
The 2026-W39 and 2026-W41 Instagram carousels failed with "IG container 1
failed: Only photo or video can be accepted as media type" while Facebook
posted fine. Nothing was wrong with the slides. post_weekly.py pushed them to
GitHub Pages, slept a fixed 50 seconds, HEAD-checked only slide 1 (and carried
on after a 404), then handed Instagram the www.tulsagays.com URLs about two
minutes after the push. GitHub's own Actions history shows how long those
deploys really took:

    W39  commit 4725440  pages build 16:00:35Z -> 16:08:36Z   (8 min)   IG tried 16:02:33Z  FAILED
    W40  commit 48b7667  pages build 16:00:38Z -> 16:01:49Z   (71 s)    IG tried ~16:02:45Z OK
    W41  commit 48a2045  pages build 21:00:34Z -> 22:14:05Z   (73 min)  IG tried 21:02:38Z  FAILED

A path GitHub Pages has not deployed yet answers "HTTP 404, text/html", so
Instagram downloaded an HTML page where it expected an image. Every earlier
week that posted had a deploy under about two minutes (W35 finished 14:02:40Z,
seconds before its IG call).

WHAT IT DOES, per asset, fail-closed
  1. prepare_assets(): open each slide with Pillow and refuse anything that is
     not one still image (PDF, HTML, HEIC Pillow cannot read, animated GIF or
     WEBP, real transparency). Convert stills to baseline RGB JPEG, the only
     image_url format Meta documents, at quality 95 with no chroma subsampling.
     Downscale widths over 1440. Refuse widths under 320, aspect ratios outside
     Instagram's 4:5 to 1.91:1 (cropping a text slide is never safe), and files
     over 8 MB.
  2. resolve_public_urls(): after the push, poll the Pages URL with a
     cache-busting HEAD probe until it serves an image of the right size, then
     confirm the exact URL Instagram will get with a full GET: HTTP 200,
     Content-Type image/jpeg, JPEG magic bytes, sha256 equal to the local file,
     and Pillow decodes it. If Pages has not deployed inside the budget, fall
     back to the raw.githubusercontent.com URL pinned to the pushed commit and
     validate that the same way.
  3. Any asset that never validates raises IGAssetError naming that asset and
     the reason. The caller never sends an unvalidated URL to Instagram.

    python tools/ig_media_guard.py --selftest
    python tools/ig_media_guard.py --week 2026-W42             # local check of a week's slides
    python tools/ig_media_guard.py --week 2026-W41 --remote    # also GET the live hosted URLs (read-only)
"""
from __future__ import annotations

import argparse
import hashlib
import io
import shutil
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Instagram content-publishing image limits (Graph API /media image_url).
IG_MIN_WIDTH = 320
IG_MAX_WIDTH = 1440
IG_MIN_ASPECT = 4 / 5          # 0.8, portrait limit
IG_MAX_ASPECT = 1.91           # landscape limit
IG_MAX_BYTES = 8 * 1024 * 1024
JPEG_QUALITY = 95
ASPECT_TOLERANCE = 0.005

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Every URL resolve_public_urls() proved this process. post_weekly checks
# membership before each container call and re-validates anything not in it.
VERIFIED: set[str] = set()


class AssetRejected(ValueError):
    """One local asset cannot be made Instagram-safe."""


class IGAssetError(RuntimeError):
    """One or more assets failed. .failures is a list of (asset_name, reason)."""

    def __init__(self, failures: list[tuple[str, str]]):
        self.failures = list(failures)
        detail = "; ".join(f"{n}: {r}" for n, r in self.failures)
        super().__init__(f"{len(self.failures)} Instagram asset(s) not safe to send: {detail}")


@dataclass
class PreparedAsset:
    source: Path
    path: Path
    name: str
    sha256: str
    size: int
    width: int
    height: int
    converted_from: str = ""
    notes: list[str] = field(default_factory=list)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sniff(head: bytes) -> str:
    """Name what a file really is from its first bytes, regardless of extension."""
    h = head.lstrip()
    if head.startswith(b"%PDF"):
        return "PDF document"
    if h[:1] == b"<" or h[:9].lower() == b"<!doctype":
        return "HTML/XML text"
    if head[4:8] == b"ftyp" and head[8:12] in (b"heic", b"heix", b"hevc", b"mif1", b"msf1", b"avif"):
        return f"HEIF/AVIF ({head[8:12].decode('ascii', 'replace')})"
    return ""


def prepare_asset(src: Path, out_dir: Path) -> PreparedAsset:
    """Validate one slide and write an Instagram-safe JPEG to out_dir.

    Raises AssetRejected with a specific reason when the asset cannot be made
    safe. Never guesses: transparency, animation, unreadable formats and
    unsupported aspect ratios are refused, not coerced."""
    from PIL import Image, UnidentifiedImageError

    src = Path(src)
    if not src.exists():
        raise AssetRejected(f"file missing: {src}")
    raw = src.read_bytes()
    if not raw:
        raise AssetRejected("file is empty (0 bytes)")
    kind = _sniff(raw[:64])
    if kind.startswith(("PDF", "HTML")):
        raise AssetRejected(f"{kind}, not an image (extension {src.suffix or 'none'} is lying)")

    try:
        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()
        im = Image.open(io.BytesIO(raw))
        im.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as e:
        what = kind or "unrecognised bytes"
        raise AssetRejected(f"Pillow cannot read it ({what}): {e}") from e

    fmt = (im.format or "").upper()
    frames = int(getattr(im, "n_frames", 1) or 1)
    if frames > 1:
        raise AssetRejected(f"animated {fmt} with {frames} frames; an Instagram image item must be one still")

    notes: list[str] = []
    mode = im.mode
    if mode in ("RGBA", "LA", "PA") or (mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        lo, _hi = rgba.getchannel("A").getextrema()
        if lo < 255:
            raise AssetRejected(
                f"{fmt} has transparent pixels (min alpha {lo}); flattening would guess a "
                f"background colour, so it is not converted automatically")
        im = rgba.convert("RGB")
        notes.append(f"dropped a fully opaque alpha channel ({mode})")
    elif mode == "CMYK":
        im = im.convert("RGB")
        notes.append("CMYK converted to RGB")
    elif mode in ("RGB", "L"):
        pass
    elif mode == "P":
        im = im.convert("RGB")
        notes.append("palette image converted to RGB")
    else:
        raise AssetRejected(f"unsupported pixel mode {mode} (high bit depth or float)")

    w, h = im.size
    if w < IG_MIN_WIDTH:
        raise AssetRejected(f"width {w}px is under Instagram's {IG_MIN_WIDTH}px minimum; upscaling a slide is not safe")
    aspect = w / h
    if aspect < IG_MIN_ASPECT - ASPECT_TOLERANCE or aspect > IG_MAX_ASPECT + ASPECT_TOLERANCE:
        raise AssetRejected(
            f"aspect ratio {w}x{h} ({aspect:.3f}) is outside Instagram's 4:5 (0.8) to 1.91:1; "
            f"cropping a text slide is not safe")
    resized = False
    if w > IG_MAX_WIDTH:
        nh = round(h * IG_MAX_WIDTH / w)
        im = im.resize((IG_MAX_WIDTH, nh), Image.LANCZOS)
        notes.append(f"downscaled {w}x{h} -> {IG_MAX_WIDTH}x{nh}")
        w, h = im.size
        resized = True

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{src.stem}.ig.jpg"
    passthrough = (fmt == "JPEG" and mode in ("RGB", "L") and not resized and len(raw) <= IG_MAX_BYTES)
    if passthrough:
        dst.write_bytes(raw)
        converted_from = ""
    else:
        if im.mode != "RGB":
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=JPEG_QUALITY, subsampling=0, optimize=True)
        dst.write_bytes(buf.getvalue())
        converted_from = fmt or "unknown"

    data = dst.read_bytes()
    if len(data) > IG_MAX_BYTES:
        raise AssetRejected(f"{len(data)} bytes after conversion is over Instagram's 8 MB limit")
    with Image.open(io.BytesIO(data)) as chk:
        if (chk.format or "").upper() != "JPEG" or chk.size != (w, h):
            raise AssetRejected(f"re-read of {dst.name} came back {chk.format} {chk.size}, expected JPEG {(w, h)}")
    return PreparedAsset(source=src, path=dst, name=dst.name, sha256=_sha256(data), size=len(data),
                         width=w, height=h, converted_from=converted_from, notes=notes)


def prepare_assets(sources, out_dir: Path) -> tuple[list[PreparedAsset], list[tuple[str, str]]]:
    """prepare_asset() for every source. Returns (prepared, failures); the
    caller must treat any failure as fatal for the Instagram leg."""
    prepared: list[PreparedAsset] = []
    failures: list[tuple[str, str]] = []
    sizes: set[tuple[int, int]] = set()
    for s in sources:
        try:
            a = prepare_asset(Path(s), out_dir)
            prepared.append(a)
            sizes.add((a.width, a.height))
        except AssetRejected as e:
            failures.append((Path(s).name, str(e)))
    if len({round(w / h, 3) for (w, h) in sizes}) > 1 and prepared:
        # Instagram crops every carousel item to the first item's ratio.
        prepared[0].notes.append(f"mixed aspect ratios in one carousel: {sorted(sizes)}")
    return prepared, failures


# ── Remote validation ───────────────────────────────────────────────────────

def _http(method: str, url: str):
    import requests
    return requests.request(method, url, timeout=25, allow_redirects=True,
                            headers={"User-Agent": "tulsagays-ig-media-guard/1.0",
                                     "Cache-Control": "no-cache"})


def _header(resp, name: str) -> str:
    hdrs = getattr(resp, "headers", {}) or {}
    for k, v in hdrs.items():
        if k.lower() == name.lower():
            return str(v)
    return ""


def _ctype(resp) -> str:
    return _header(resp, "Content-Type").split(";")[0].strip().lower()


def validate_remote(url: str, asset: PreparedAsset | None = None, fetch=None,
                    allowed=("image/jpeg",)) -> tuple[bool, str]:
    """Full GET of the exact URL Instagram will fetch. With an asset, the bytes
    must hash to the local file; without one, they must be a decodable image."""
    fetch = fetch or _http
    try:
        r = fetch("GET", url)
    except Exception as e:
        return False, f"unreachable ({type(e).__name__}: {e})"
    status = int(getattr(r, "status_code", 0) or 0)
    ctype = _ctype(r)
    if status != 200:
        why = f"HTTP {status} {ctype or 'no Content-Type'}"
        if "html" in ctype:
            why += " (an HTML page, not image bytes: the file is not deployed at this URL yet)"
        return False, why
    if ctype not in allowed:
        return False, f"Content-Type {ctype or 'missing'}, expected {' or '.join(allowed)}"
    body = getattr(r, "content", b"") or b""
    magic_ok = (body.startswith(JPEG_MAGIC) and "image/jpeg" in allowed) or \
               (body.startswith(PNG_MAGIC) and "image/png" in allowed)
    if not magic_ok:
        sniffed = _sniff(body[:64]) or repr(body[:8])
        return False, f"body is not {'/'.join(allowed)} bytes (starts {sniffed})"
    if asset is not None and _sha256(body) != asset.sha256:
        return False, (f"served {len(body)} bytes that differ from the local {asset.size}-byte file "
                       f"(stale or partial deploy)")
    try:
        from PIL import Image
        with Image.open(io.BytesIO(body)) as im:
            im.verify()
    except Exception as e:
        return False, f"Pillow cannot decode the served bytes: {e}"
    return True, "ok"


def _probe(url: str, asset: PreparedAsset, fetch) -> tuple[bool, str]:
    """Cheap HEAD: is the deploy live yet? The full GET comes after."""
    try:
        r = fetch("HEAD", url)
    except Exception as e:
        return False, f"unreachable ({type(e).__name__}: {e})"
    status = int(getattr(r, "status_code", 0) or 0)
    ctype = _ctype(r)
    if status != 200:
        why = f"HTTP {status} {ctype or 'no Content-Type'}"
        if "html" in ctype:
            why += " (an HTML page, not image bytes: the file is not deployed at this URL yet)"
        return False, why
    if ctype != "image/jpeg":
        return False, f"Content-Type {ctype or 'missing'}, expected image/jpeg"
    clen = _header(r, "Content-Length")
    if clen.isdigit() and int(clen) != asset.size:
        return False, f"Content-Length {clen} != local {asset.size} (an older deploy of this path)"
    return True, "ok"


def resolve_public_urls(assets: list[PreparedAsset], pages_base: str, raw_base: str | None = None,
                        fetch=None, budget_s: float = 240, poll_s: float = 10,
                        clock=None, sleep=None, log=print) -> list[str]:
    """Return one verified public URL per asset, in order, or raise IGAssetError.

    Pages first (the URL that has posted every good week), with a
    cache-busting probe so a 404 cached before the deploy cannot be served back
    to us, and a ?v=<sha> on the final URL so no edge can hand Instagram a 404
    it cached for the bare path. If Pages is not live inside budget_s, the
    commit-pinned raw.githubusercontent.com copy is validated instead."""
    fetch = fetch or _http
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    pages_base = pages_base.rstrip("/")
    verified: dict[str, str] = {}
    reasons: dict[str, str] = {a.name: "not checked" for a in assets}
    pending = list(assets)
    deadline = clock() + max(0.0, budget_s)
    rounds = 0
    while pending:
        rounds += 1
        still: list[PreparedAsset] = []
        for i, a in enumerate(pending):
            base = f"{pages_base}/{a.name}"
            ok, why = _probe(f"{base}?probe={uuid.uuid4().hex[:12]}", a, fetch)
            if not ok:
                reasons[a.name] = f"Pages: {why}"
                # A Pages deploy publishes a commit atomically: if this file is
                # not live, the rest of the batch is not either. Wait, retry.
                still.extend(pending[i:])
                break
            final = f"{base}?v={a.sha256[:12]}"
            ok, why = validate_remote(final, a, fetch)
            if ok:
                verified[a.name] = final
            else:
                reasons[a.name] = f"Pages: {why}"
                still.append(a)
        pending = still
        if not pending or clock() >= deadline:
            break
        sleep(poll_s)
    if pending:
        log(f"[ig-guard] Pages not serving {len(pending)} of {len(assets)} file(s) after "
            f"{rounds} check(s): {reasons[pending[0].name]}")
    if pending and raw_base:
        raw_base = raw_base.rstrip("/")
        log("[ig-guard] falling back to raw.githubusercontent.com at the pushed commit")
        for attempt in range(3):
            left: list[PreparedAsset] = []
            for a in pending:
                ok, why = validate_remote(f"{raw_base}/{a.name}", a, fetch)
                if ok:
                    verified[a.name] = f"{raw_base}/{a.name}"
                else:
                    reasons[a.name] = reasons[a.name].split("; raw:")[0] + f"; raw: {why}"
                    left.append(a)
            pending = left
            if not pending:
                break
            if attempt < 2:
                sleep(poll_s)
    if pending:
        raise IGAssetError([(a.name, reasons[a.name]) for a in pending])
    VERIFIED.update(verified.values())
    for a in assets:
        log(f"[ig-guard] verified {a.name}: {verified[a.name]}")
    return [verified[a.name] for a in assets]


def is_verified(url: str) -> bool:
    return url in VERIFIED


def check_url_for_ig(url: str, fetch=None) -> tuple[bool, str]:
    """For a URL this process did not resolve itself: it must serve a real,
    decodable JPEG or PNG right now."""
    return validate_remote(url, None, fetch, allowed=("image/jpeg", "image/png"))


# ── CLI: dry-run a week ─────────────────────────────────────────────────────

def week_slides(week: str) -> list[Path]:
    d = ROOT / "data" / "posts" / week
    slides = sorted(d.glob("weekday__*.png")) or sorted(d.glob("all__*.png"))
    return slides + sorted((d / "weekend").glob("weekend_*.png"))


def check_week(week: str, remote: bool = False) -> int:
    from PIL import Image, ImageChops, ImageStat

    slides = week_slides(week)
    if not slides:
        print(f"[ig-guard] {week}: no slides on disk under data/posts/{week}/ (not generated yet)")
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="ig_guard_"))
    try:
        prepared, failures = prepare_assets(slides, tmp)
        for a in prepared:
            with Image.open(a.source) as s, Image.open(a.path) as j:
                diff = ImageStat.Stat(ImageChops.difference(s.convert("RGB"), j.convert("RGB"))).mean
            mad = sum(diff) / 3
            how = f"converted {a.converted_from}->JPEG" if a.converted_from else "JPEG passthrough"
            print(f"  OK   {a.source.name:<18} {a.width}x{a.height} {how}, {a.size // 1024}KB, "
                  f"mean abs pixel diff {mad:.2f}/255" + (f" | {'; '.join(a.notes)}" if a.notes else ""))
        for name, why in failures:
            print(f"  FAIL {name:<18} {why}")
        if remote:
            import config
            site = (getattr(config, "SITE_URL", "") or "").rstrip("/")
            print(f"[ig-guard] remote: what {site}/posts/{week}/ serves right now (read-only GETs)")
            for s in slides:
                url = f"{site}/posts/{week}/{s.name}"
                ok, why = check_url_for_ig(url)
                local = _sha256(s.read_bytes())
                same = ""
                if ok:
                    try:
                        same = " bytes==local" if _sha256(_http("GET", url).content) == local else " BYTES DIFFER"
                    except Exception:
                        pass
                print(f"  {'LIVE' if ok else 'DEAD'} {url} -> {why}{same}")
        print(f"[ig-guard] {week}: {len(prepared)} ready, {len(failures)} rejected")
        return 0 if not failures else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Selftest (offline: fake HTTP, temp files) ───────────────────────────────

class _Resp:
    def __init__(self, status: int, ctype: str, body: bytes = b""):
        self.status_code = status
        self.headers = {"Content-Type": ctype, "Content-Length": str(len(body))}
        self.content = body


GITHUB_404 = (b"<!DOCTYPE html>\n<html>\n  <head>\n    <meta http-equiv=\"Content-type\" "
              b"content=\"text/html; charset=utf-8\">\n    <title>Page not found &middot; "
              b"GitHub Pages</title>\n")


def _selftest() -> int:
    from PIL import Image, ImageDraw

    checks = 0
    failed: list[str] = []

    def check(cond, msg):
        nonlocal checks
        checks += 1
        print(("  ok   " if cond else "  FAIL ") + msg)
        if not cond:
            failed.append(msg)

    tmp = Path(tempfile.mkdtemp(prefix="ig_guard_selftest_"))
    try:
        src_dir, out = tmp / "src", tmp / "out"
        src_dir.mkdir()

        def slide(name, size=(1080, 1080), mode="RGB", fmt="PNG", **kw):
            im = Image.new(mode, size, (40, 10, 60) if mode == "RGB" else (40, 10, 60, 255))
            d = ImageDraw.Draw(im)
            d.rectangle([60, 60, size[0] - 60, 200], fill=(255, 20, 147) if mode == "RGB" else (255, 20, 147, 255))
            d.text((80, 100), "TULSA GAYS THIS WEEK", fill=(255, 255, 255) if mode == "RGB" else (255, 255, 255, 255))
            p = src_dir / name
            im.save(p, fmt, **kw)
            return p

        # The real W41 slide when it is on disk, else a synthetic 1080x1080 RGB PNG.
        real = ROOT / "data" / "posts" / "2026-W41" / "all__01.png"
        w41 = src_dir / "all__01.png"
        if real.exists():
            shutil.copy2(real, w41)
        else:
            slide("all__01.png")
        slides = [w41, slide("all__02.png"), slide("all__03.png")]

        print("[1] W41 reproduction: Pages answers 404 text/html for every slide (deploy still running)")
        prepared, bad = prepare_assets(slides, out)
        check(not bad and len(prepared) == 3, "the W41-shaped PNG slides prepare cleanly")
        a0 = prepared[0]
        check(a0.converted_from == "PNG" and a0.name == "all__01.ig.jpg", "PNG converted to all__01.ig.jpg")
        with Image.open(a0.path) as j:
            check(j.format == "JPEG" and j.mode == "RGB" and j.size == (1080, 1080), "output is a 1080x1080 RGB JPEG")
        calls: list[tuple[str, str]] = []

        def pages_never(method, url):
            calls.append((method, url))
            return _Resp(404, "text/html; charset=utf-8", GITHUB_404)

        try:
            resolve_public_urls(prepared, "https://www.tulsagays.com/posts/2026-W41", None,
                                fetch=pages_never, budget_s=0, log=lambda *_: None)
            check(False, "an undeployed URL must raise IGAssetError")
        except IGAssetError as e:
            names = [n for n, _ in e.failures]
            check(names == ["all__01.ig.jpg", "all__02.ig.jpg", "all__03.ig.jpg"],
                  "every slide is named in the failure, in order")
            check("HTTP 404 text/html" in e.failures[0][1] and "not deployed" in e.failures[0][1],
                  f"reason says what Instagram would have fetched: {e.failures[0][1][:90]}")
        check(not any(is_verified(u) for _, u in calls), "nothing from the dead host was marked verified")
        ok, why = validate_remote("https://x/all__01.ig.jpg", a0,
                                  fetch=lambda m, u: _Resp(200, "text/html", GITHUB_404))
        check(not ok and "text/html" in why, "a 200 that serves HTML is still refused")

        print("[2] W39 shape: deploy finishes after several polls -> the Pages URL is used, after waiting")
        state = {"n": 0}
        by_name = {a.name: a.path.read_bytes() for a in prepared}

        def pages_slow(method, url):
            name = url.rsplit("/", 1)[1].split("?")[0]
            if method == "HEAD":
                state["n"] += 1
            if state["n"] <= 4:
                return _Resp(404, "text/html; charset=utf-8", GITHUB_404)
            return _Resp(200, "image/jpeg", by_name[name])

        slept: list[float] = []
        t = {"now": 0.0}
        urls = resolve_public_urls(prepared, "https://www.tulsagays.com/posts/2026-W39", "https://raw.example/sha",
                                   fetch=pages_slow, budget_s=240, poll_s=10,
                                   clock=lambda: t["now"],
                                   sleep=lambda s: (slept.append(s), t.__setitem__("now", t["now"] + s)),
                                   log=lambda *_: None)
        check(len(slept) == 4, f"it waited for the deploy ({len(slept)} polls) instead of firing blind")
        check(all(u.startswith("https://www.tulsagays.com/posts/2026-W39/") and "?v=" in u for u in urls),
              "verified URLs are the Pages host with a content-hash cache key")
        check(all(is_verified(u) for u in urls), "verified URLs are registered for the container call")

        print("[3] W41 shape: Pages takes 73 min -> raw.githubusercontent.com at the commit, validated")

        def pages_dead_raw_ok(method, url):
            if "raw.githubusercontent.com" in url:
                return _Resp(200, "image/jpeg", by_name[url.rsplit("/", 1)[1]])
            return _Resp(404, "text/html; charset=utf-8", GITHUB_404)

        t["now"] = 0.0
        urls = resolve_public_urls(prepared, "https://www.tulsagays.com/posts/2026-W41",
                                   "https://raw.githubusercontent.com/DistrictOfRyan/tulsagays/48a2045/docs/posts/2026-W41",
                                   fetch=pages_dead_raw_ok, budget_s=240, poll_s=10,
                                   clock=lambda: t["now"],
                                   sleep=lambda s: t.__setitem__("now", t["now"] + s), log=lambda *_: None)
        check(all("raw.githubusercontent.com" in u for u in urls), "falls back to the commit-pinned raw URL")

        print("[4] stale deploy: right type, wrong bytes")
        ok, why = validate_remote("https://x/all__01.ig.jpg", a0,
                                  fetch=lambda m, u: _Resp(200, "image/jpeg", by_name["all__02.ig.jpg"]))
        check(not ok and "differ" in why, "bytes that do not hash to the local file are refused")

        print("[5] conversions that are safe")
        webp = slide("weekend_01.webp", fmt="WEBP", quality=90)
        a = prepare_asset(webp, out)
        check(a.converted_from == "WEBP" and a.path.suffix == ".jpg", "WEBP -> JPEG")
        opaque = slide("opaque.png", mode="RGBA")
        a = prepare_asset(opaque, out)
        check(a.converted_from == "PNG" and any("opaque alpha" in n for n in a.notes), "fully opaque RGBA PNG -> JPEG")
        big = slide("big.png", size=(2160, 2700))
        a = prepare_asset(big, out)
        check((a.width, a.height) == (1440, 1800), "2160x2700 downscaled to 1440x1800")
        jpg = slide("portrait.jpg", size=(1080, 1350), fmt="JPEG", quality=92)
        a = prepare_asset(jpg, out)
        check(a.converted_from == "" and a.sha256 == _sha256(jpg.read_bytes()), "a good RGB JPEG passes through byte-identical")
        with Image.open(w41) as s, Image.open(prepared[0].path) as j:
            from PIL import ImageChops, ImageStat
            mad = sum(ImageStat.Stat(ImageChops.difference(s.convert("RGB"), j.convert("RGB"))).mean) / 3
        check(mad < 2.0, f"PNG->JPEG keeps the slide visually identical (mean abs diff {mad:.2f}/255)")

        print("[6] assets that must fail loudly, one reason each")
        cases = {}
        p = src_dir / "w41_404_saved_as.png"
        p.write_bytes(GITHUB_404)
        cases["html"] = (p, "HTML")
        p = src_dir / "deck.png"
        p.write_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n")
        cases["pdf"] = (p, "PDF")
        p = src_dir / "phone.heic"
        p.write_bytes(b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 64)
        cases["heic"] = (p, "Pillow cannot read")
        clear = Image.new("RGBA", (1080, 1080), (0, 0, 0, 0))
        p = src_dir / "transparent.png"
        clear.save(p)
        cases["alpha"] = (p, "transparent")
        frames = [Image.new("RGB", (1080, 1080), c) for c in ((255, 0, 0), (0, 255, 0))]
        p = src_dir / "anim.gif"
        frames[0].save(p, save_all=True, append_images=frames[1:], duration=200)
        cases["anim"] = (p, "animated")
        cases["story"] = (slide("story.png", size=(1080, 1920)), "aspect ratio")
        cases["tiny"] = (slide("tiny.png", size=(200, 200)), "under Instagram")
        p = src_dir / "empty.png"
        p.write_bytes(b"")
        cases["empty"] = (p, "empty")
        cases["missing"] = (src_dir / "nope.png", "missing")
        _, fails = prepare_assets([c[0] for c in cases.values()], out)
        got = dict(fails)
        for key, (path, needle) in cases.items():
            reason = got.get(path.name, "")
            check(needle in reason, f"{key}: {reason[:80] or 'NOT REJECTED'}")

        print("[7] URLs the poster did not resolve itself are re-checked")
        png_bytes = w41.read_bytes()
        ok, _ = check_url_for_ig("https://x/a.png", fetch=lambda m, u: _Resp(200, "image/png", png_bytes))
        check(ok, "a live PNG URL is accepted")
        ok, why = check_url_for_ig("https://x/a.png", fetch=lambda m, u: _Resp(404, "text/html", GITHUB_404))
        check(not ok and "404" in why, "a 404 HTML URL is refused")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failed:
        print(f"SELFTEST FAIL: {len(failed)} of {checks} checks failed")
        return 1
    print(f"SELFTEST PASS ({checks} checks)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--week", help="dry-run validate this week's slides, e.g. 2026-W42")
    ap.add_argument("--remote", action="store_true", help="with --week, also GET the hosted URLs (read-only)")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.week:
        sys.path.insert(0, str(ROOT))
        return check_week(args.week, remote=args.remote)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
