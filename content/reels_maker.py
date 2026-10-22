"""Generate a 15-second 1080×1080 Reels video for Tulsa Gays weekly events.

Uses ffmpeg (system binary) if available; falls back to a Pillow animated GIF.
"""

import os
import shutil
import subprocess
from pathlib import Path

SLIDE_DURATION = 3       # seconds per slide
FADE_DURATION  = 0.5     # xfade crossfade duration in seconds
BRAND_COLOR    = "0x6B21A8"   # purple background
SIZE           = "1080x1080"
FPS            = 30

_FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"
_POIRET    = str(_FONTS_DIR / "PoiretOne-Regular.ttf")


def _esc(text: str) -> str:
    """Escape text for ffmpeg drawtext filter value."""
    return (
        text
        .replace("\\", "\\\\")
        .replace("'",  "\\'")
        .replace(":",  "\\:")
        .replace(",",  "\\,")
    )


def _short(text: str, max_len: int = 32) -> str:
    text = (text or "").strip()
    return text[: max_len - 2] + ".." if len(text) > max_len else text


def _wrap_text(text: str, max_chars: int = 28) -> list:
    words = (text or "").split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _make_with_ffmpeg(slides: list, output_path: str) -> str:
    has_poiret = os.path.exists(_POIRET)
    font_opt   = f":fontfile='{_POIRET}'" if has_poiret else ""

    inputs, chains = [], []

    for i, ev in enumerate(slides):
        img_path = str(ev.get("image_path", "") or "")
        if img_path and os.path.exists(img_path):
            inputs += ["-loop", "1", "-t", str(SLIDE_DURATION), "-i", img_path]
            chains.append(
                f"[{i}:v]scale=1080:1080:force_original_aspect_ratio=increase,"
                f"crop=1080:1080,setsar=1,format=yuv420p[bg{i}]"
            )
        else:
            inputs += [
                "-f", "lavfi", "-t", str(SLIDE_DURATION),
                "-i", f"color=c={BRAND_COLOR}:s={SIZE}:r={FPS}",
            ]
            chains.append(f"[{i}:v]setsar=1,format=yuv420p[bg{i}]")

        name_lines = _wrap_text(ev.get("name", "Event"), max_chars=26)
        venue_text = _short(ev.get("venue", ""), 38)
        date_text  = _short(ev.get("date_str", ""), 30)

        line_h   = 72
        total_h  = len(name_lines) * line_h
        # Vertical center of slide minus offset to leave room for venue/date below
        y_top    = f"(h-{total_h})/2-50"

        dt_parts = []
        for j, ln in enumerate(name_lines):
            y_pos = f"({y_top}+{j * line_h})"
            dt_parts.append(
                f"drawtext=text='{_esc(ln)}'{font_opt}"
                f":fontcolor=white:fontsize=60"
                f":x=(w-text_w)/2:y={y_pos}"
            )

        if venue_text:
            venue_y = f"(h/2+{len(name_lines) * line_h // 2 + 20})"
            dt_parts.append(
                f"drawtext=text='{_esc(venue_text)}'{font_opt}"
                f":fontcolor=0xFF1493:fontsize=38"
                f":x=(w-text_w)/2:y={venue_y}"
            )

        if date_text:
            date_y = f"(h/2+{len(name_lines) * line_h // 2 + 72})"
            dt_parts.append(
                f"drawtext=text='{_esc(date_text)}'"
                f":fontcolor=0xCCCCCC:fontsize=30"
                f":x=(w-text_w)/2:y={date_y}"
            )

        dt_chain = f"[bg{i}]" + ",".join(dt_parts) + f"[s{i}]"
        chains.append(dt_chain)

    # Chain xfade filters between slides
    n = len(slides)
    if n == 1:
        chains.append("[s0]copy[out]")
    else:
        prev = "s0"
        for i in range(1, n):
            out    = "out" if i == n - 1 else f"x{i}"
            offset = round(i * (SLIDE_DURATION - FADE_DURATION), 3)
            chains.append(
                f"[{prev}][s{i}]xfade=transition=fade"
                f":duration={FADE_DURATION}:offset={offset}[{out}]"
            )
            prev = out

    filter_complex = ";".join(chains)

    cmd = (
        ["ffmpeg", "-y"]
        + inputs
        + [
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path,
        ]
    )

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{r.stderr[-2000:]}")
    return output_path


def _make_with_pillow(slides: list, output_path: str) -> str:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore

    SIZE_PX  = (1080, 1080)
    BG_COLOR = (107, 33, 168)   # #6B21A8
    PINK     = (255, 20, 147)   # #FF1493

    def _load_font(path: str, size: int):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
        for fallback in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]:
            try:
                return ImageFont.truetype(fallback, size)
            except OSError:
                pass
        return ImageFont.load_default()

    fnt_name  = _load_font(_POIRET, 60)
    fnt_venue = _load_font(_POIRET, 38)
    fnt_date  = _load_font("", 30)  # system default for date

    frames = []
    for ev in slides:
        img_path = str(ev.get("image_path", "") or "")
        if img_path and os.path.exists(img_path):
            try:
                bg    = Image.open(img_path).convert("RGB")
                scale = max(SIZE_PX[0] / bg.width, SIZE_PX[1] / bg.height)
                bg    = bg.resize(
                    (int(bg.width * scale), int(bg.height * scale)), Image.LANCZOS
                )
                left  = (bg.width  - SIZE_PX[0]) // 2
                top   = (bg.height - SIZE_PX[1]) // 2
                bg    = bg.crop((left, top, left + SIZE_PX[0], top + SIZE_PX[1]))
                # Darken for text readability
                overlay = Image.new("RGBA", SIZE_PX, (0, 0, 0, 140))
                bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
            except Exception:
                bg = Image.new("RGB", SIZE_PX, BG_COLOR)
        else:
            bg = Image.new("RGB", SIZE_PX, BG_COLOR)

        draw = ImageDraw.Draw(bg)

        name_lines = _wrap_text(ev.get("name", "Event"), max_chars=26)
        line_h  = 74
        total_h = len(name_lines) * line_h
        y       = (SIZE_PX[1] - total_h) // 2 - 50

        for line in name_lines:
            bbox = draw.textbbox((0, 0), line, font=fnt_name)
            tw   = bbox[2] - bbox[0]
            draw.text(((SIZE_PX[0] - tw) // 2, y), line, fill="white", font=fnt_name)
            y += line_h

        y += 20
        if ev.get("venue"):
            venue = _short(ev["venue"], 38)
            bbox = draw.textbbox((0, 0), venue, font=fnt_venue)
            tw   = bbox[2] - bbox[0]
            draw.text(((SIZE_PX[0] - tw) // 2, y), venue, fill=PINK, font=fnt_venue)
            y += 52

        if ev.get("date_str"):
            ds   = _short(ev["date_str"], 30)
            bbox = draw.textbbox((0, 0), ds, font=fnt_date)
            tw   = bbox[2] - bbox[0]
            draw.text(((SIZE_PX[0] - tw) // 2, y), ds, fill=(204, 204, 204), font=fnt_date)

        # 3 seconds at 10 fps = 30 frames per slide
        for _ in range(30):
            frames.append(bg.copy())

    if not frames:
        raise RuntimeError("No frames generated")

    # Pillow cannot write MP4; save as animated GIF (preview only — Instagram
    # Reels requires MP4; use ffmpeg for production posting)
    gif_path = str(Path(output_path).with_suffix(".gif"))
    frames[0].save(
        gif_path,
        save_all=True,
        append_images=frames[1:],
        duration=100,   # 100 ms/frame = 10 fps
        loop=0,
        optimize=False,
    )
    return gif_path


def make_reels_video(events: list, output_path: str) -> str:
    """
    Generate a 15-second 1080×1080 video from the top 3-5 events.

    events: list of dicts with keys:
        name        (str)  event title
        venue       (str)  venue / business name
        date_str    (str)  human-readable date + time, e.g. "Fri, Jun 6  ·  7:00 PM"
        image_path  (str, optional) local path to a background image
    output_path: where to write the MP4 (or .gif when Pillow fallback is used)

    Returns the path that was written on success; raises on failure.
    """
    slides = events[:5]
    if not slides:
        raise ValueError("Need at least 1 event to make a Reels video")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    if shutil.which("ffmpeg"):
        return _make_with_ffmpeg(slides, output_path)

    try:
        import PIL  # noqa: F401
        return _make_with_pillow(slides, output_path)
    except ImportError:
        raise RuntimeError(
            "Neither ffmpeg nor Pillow is available. "
            "Install ffmpeg (system package) or run: pip install Pillow"
        )
