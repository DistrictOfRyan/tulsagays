"""Generate Instagram carousel images (1080x1080) for Tulsa Gays weekly posts.

Brand: Art deco style. Dark background (#0a0a0a), Cinzel headers, Segoe UI Light
body, pink accent (#9B1E5F), white text, thin line decorators, diamond separators.
NO rainbow bars. NO pride colors. Clean, elegant, not cluttered.

Slide structure (10 slides):
  1. Cover: "THIS WEEK" + TULSA [flamingo] GAYS + date range
  2. Event of the Week (center-aligned spotlight)
  3-9. Monday through Sunday (3-5 events each, non-bar events first)
  10. Closing CTA: follow + blog link
"""

import sys
import os
import math
import textwrap
from typing import List, Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ── Brand Constants ─────────────────────────────────────────────────────
SIZE = (1080, 1080)
BG = (10, 10, 10)
PINK = (155, 30, 95)
PINK_LIGHT = (180, 50, 115)
PINK_DARK = (110, 20, 65)
WHITE = (255, 255, 255)
LIGHT = (200, 200, 200)
MUTED = (130, 130, 130)
DARK_LINE = (60, 60, 60)

# Day accent colors (from the blog CSS)
DAY_COLORS = {
    "monday": (139, 168, 136),     # sage green
    "tuesday": (155, 142, 196),    # lavender
    "wednesday": (184, 134, 11),   # gold
    "thursday": (196, 132, 139),   # rose
    "friday": (155, 30, 95),       # pink (brand)
    "saturday": (155, 142, 196),   # lavender
    "sunday": (100, 181, 246),     # sky blue
}

PAD = 60
MAX_EVENTS = 5

# ── Font paths ──────────────────────────────────────────────────────────
FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
WINFONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")


def _cinzel(size: int) -> ImageFont.FreeTypeFont:
    path = os.path.join(FONT_DIR, "Cinzel.ttf")
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _segoe_light(size: int) -> ImageFont.FreeTypeFont:
    path = os.path.join(WINFONTS, "segoeuil.ttf")
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    path2 = os.path.join(WINFONTS, "arial.ttf")
    if os.path.exists(path2):
        return ImageFont.truetype(path2, size)
    return ImageFont.load_default()


def _segoe_body(size: int) -> ImageFont.FreeTypeFont:
    return _segoe_light(size)


# ── Drawing helpers ─────────────────────────────────────────────────────

def _new_slide() -> Tuple[Image.Image, ImageDraw.Draw]:
    img = Image.new("RGB", SIZE, BG)
    return img, ImageDraw.Draw(img)


def _line(draw, y, margin=PAD):
    draw.line([(margin, y), (SIZE[0] - margin, y)], fill=PINK, width=1)


def _diamond(draw, cx, cy, size=5):
    draw.polygon([(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)], fill=PINK)


def _diamond_sep(draw, y):
    _line(draw, y, margin=350)
    _diamond(draw, SIZE[0] // 2, y)
    return y + 20


def _centered(draw, text, y, font, fill=WHITE):
    tw = draw.textlength(text, font=font)
    x = (SIZE[0] - tw) / 2
    draw.text((x, y), text, font=font, fill=fill)
    bbox = draw.textbbox((0, 0), text, font=font)
    return y + (bbox[3] - bbox[1])


def _wrapped_centered(draw, text, y, font, fill=LIGHT, max_width=SIZE[0] - 2 * PAD):
    avg_w = draw.textlength("M", font=font)
    chars = max(int(max_width / avg_w), 10)
    lines = textwrap.wrap(text, width=chars)
    for line in lines:
        tw = draw.textlength(line, font=font)
        x = (SIZE[0] - tw) / 2
        bbox = draw.textbbox((0, 0), line, font=font)
        draw.text((x, y), line, font=font, fill=fill)
        y += (bbox[3] - bbox[1]) + 6
    return y


def _draw_flamingo(draw, cx, cy, scale=1.0):
    s = scale
    head_y = cy - 42 * s
    head_r = 4.5 * s
    draw.ellipse([(cx - head_r, head_y - head_r), (cx + head_r, head_y + head_r)], fill=PINK)
    draw.line([(cx + head_r * 0.6, head_y + 1 * s), (cx + head_r * 2, head_y + 4 * s)], fill=PINK_DARK, width=max(1, int(2 * s)))
    draw.ellipse([(cx - 1 * s, head_y - 1.5 * s), (cx + 1 * s, head_y + 0.5 * s)], fill=BG)
    neck_pts = []
    for t in range(100):
        tt = t / 99.0
        x = cx + math.sin(tt * math.pi * 1.1) * 6 * s * (1 - tt * 0.3)
        y = cy - 5 * s - tt * 38 * s
        neck_pts.append((x, y))
    for i in range(len(neck_pts) - 1):
        p = i / len(neck_pts)
        w = max(1, int((4 - p * 2.5) * s))
        r = int(PINK[0] + p * 15)
        g = int(PINK[1] + p * 10)
        b = int(PINK[2] + p * 10)
        draw.line([neck_pts[i], neck_pts[i + 1]], fill=(r, g, b), width=w)
    body_pts = []
    for angle in range(0, 360, 2):
        rad = math.radians(angle)
        rx = 16 * s * (1 + 0.25 * math.cos(rad))
        ry = 10 * s
        x = cx + rx * math.cos(rad)
        y = cy + 8 * s + ry * math.sin(rad) * 0.6
        body_pts.append((x, y))
    draw.polygon(body_pts, fill=PINK)
    for angle in range(-30, 120, 3):
        rad = math.radians(angle)
        r = 12 * s
        x = cx + 2 * s + r * math.cos(rad) * 0.8
        y = cy + 6 * s + r * math.sin(rad) * 0.4
        if angle > -30:
            prev_rad = math.radians(angle - 3)
            px = cx + 2 * s + r * math.cos(prev_rad) * 0.8
            py = cy + 6 * s + r * math.sin(prev_rad) * 0.4
            draw.line([(px, py), (x, y)], fill=PINK_LIGHT, width=max(1, int(1.5 * s)))
    tail_bx = cx + 16 * s
    tail_by = cy + 8 * s
    for dy, length in [(-3, 14), (1, 11)]:
        draw.line([(tail_bx, tail_by + dy * s), (tail_bx + length * s, tail_by + (dy - 2) * s)], fill=PINK_LIGHT, width=max(1, int(1.2 * s)))
    lt = cy + 16 * s
    lb = cy + 38 * s
    kl = (cx - 3 * s, lt + 10 * s)
    fl = (cx - 1 * s, lb)
    draw.line([(cx - 2 * s, lt), kl], fill=PINK_DARK, width=max(1, int(1.8 * s)))
    draw.line([kl, fl], fill=PINK_DARK, width=max(1, int(1.5 * s)))
    draw.line([fl, (fl[0] + 4 * s, fl[1])], fill=PINK_DARK, width=max(1, int(1.2 * s)))
    kr = (cx + 1 * s, lt + 8 * s)
    fr = (cx + 4 * s, lt + 18 * s)
    draw.line([(cx + 1 * s, lt), kr], fill=PINK_DARK, width=max(1, int(1.5 * s)))
    draw.line([kr, fr], fill=PINK_DARK, width=max(1, int(1.2 * s)))


# ── Slide Generators ────────────────────────────────────────────────────

def make_cover_slide(date_range: str) -> Image.Image:
    img, draw = _new_slide()
    _line(draw, 80)

    tag_font = _cinzel(22)
    tag = "TULSA'S QUEER EVENT GUIDE"
    _centered(draw, tag, 95, tag_font, MUTED)

    # TULSA [flamingo] GAYS
    title_font = _cinzel(72)
    tulsa_w = draw.textlength("TULSA", font=title_font)
    gays_w = draw.textlength("GAYS", font=title_font)
    gap = 55
    total = tulsa_w + gap + gays_w
    x = (SIZE[0] - total) / 2
    y_t = 145
    draw.text((x, y_t), "TULSA", font=title_font, fill=WHITE)
    _draw_flamingo(draw, x + tulsa_w + gap / 2, y_t + 50, scale=1.1)
    draw.text((x + tulsa_w + gap, y_t), "GAYS", font=title_font, fill=PINK)

    _line(draw, 250)

    # Date range
    date_font = _cinzel(28)
    _centered(draw, date_range, 275, date_font, WHITE)

    _diamond_sep(draw, 330)

    # Tagline
    tagline_font = _segoe_light(26)
    _centered(draw, "Nothing to do? Sounds like a straight person problem.", 355, tagline_font, MUTED)

    _line(draw, 1000)
    return img


def make_event_of_week_slide(event: Dict) -> Image.Image:
    img, draw = _new_slide()
    _line(draw, 80)

    label_font = _cinzel(22)
    _centered(draw, "FEATURED EVENT OF THE WEEK", 100, label_font, PINK)

    # Event name
    name = event.get("name", "")
    name_font = _cinzel(44)
    y = 170
    # Handle long names by wrapping
    y = _wrapped_centered(draw, name.upper(), y, name_font, WHITE)

    y += 10
    _diamond_sep(draw, y)
    y += 25

    # Details
    detail_font = _segoe_light(26)
    date_str = event.get("date", "")
    time_str = event.get("time", "")
    dt = "  ·  ".join(filter(None, [date_str, time_str]))
    if dt:
        _centered(draw, dt, y, detail_font, WHITE)
        y += 35

    venue = event.get("venue", event.get("location", ""))
    if venue:
        _centered(draw, venue, y, detail_font, PINK)
        y += 45

    # Description
    desc = event.get("description", "")
    if desc:
        desc_font = _segoe_body(22)
        y = _wrapped_centered(draw, desc, y, desc_font, LIGHT)
        y += 15

    _line(draw, y + 10)

    # Link
    url = event.get("url", "")
    if url:
        url_font = _segoe_body(20)
        _centered(draw, url, y + 30, url_font, PINK)

    _line(draw, 1000)
    return img


def make_day_slide(day_name: str, date_str: str, events: List[Dict]) -> Image.Image:
    img, draw = _new_slide()
    day_color = DAY_COLORS.get(day_name.lower(), PINK)

    _line(draw, 60)

    # Day header
    day_font = _cinzel(52)
    _centered(draw, day_name.upper(), 85, day_font, day_color)

    date_font = _segoe_light(24)
    _centered(draw, date_str, 145, date_font, MUTED)

    draw.line([(PAD, 185), (SIZE[0] - PAD, 185)], fill=day_color, width=1)
    y = 210

    # Events (3-5 per slide)
    name_font = _cinzel(28)
    venue_font = _segoe_light(20)
    desc_font = _segoe_body(20)
    time_font = _segoe_light(22)

    displayed = events[:MAX_EVENTS]
    for i, ev in enumerate(displayed):
        # Time
        t = ev.get("time", "")
        if t:
            _centered(draw, t, y, time_font, day_color)
            y += 28

        # Event name
        ename = ev.get("name", "")
        y = _wrapped_centered(draw, ename, y, name_font, WHITE, max_width=SIZE[0] - 2 * PAD - 40)
        y += 4

        # Venue
        venue = ev.get("venue", ev.get("location", ""))
        if venue:
            _centered(draw, venue, y, venue_font, MUTED)
            y += 24

        # Description (1-2 sentences, hyped)
        desc = ev.get("description", "")
        if desc:
            if len(desc) > 100:
                desc = desc[:97].rsplit(" ", 1)[0] + "..."
            y = _wrapped_centered(draw, desc, y, desc_font, LIGHT, max_width=SIZE[0] - 2 * PAD - 60)

        # Event URL
        url = ev.get("url", "")
        if url:
            url_font = _segoe_light(16)
            y += 4
            _centered(draw, url, y, url_font, PINK_LIGHT)
            y += 20

        y += 8

        # Divider between events
        if i < len(displayed) - 1:
            draw.line([(300, y), (SIZE[0] - 300, y)], fill=DARK_LINE, width=1)
            y += 16

        if y > SIZE[1] - 100:
            break

    # Blog link at bottom of every daily slide
    blog_font = _segoe_light(20)
    _centered(draw, "All events at tulsagays.com", SIZE[1] - 80, blog_font, PINK)

    if len(events) > MAX_EVENTS:
        more_font = _segoe_light(18)
        note = f"+{len(events) - MAX_EVENTS} more on the blog"
        _centered(draw, note, SIZE[1] - 105, more_font, MUTED)

    _line(draw, SIZE[0] - 60)
    return img


def make_closing_slide() -> Image.Image:
    img, draw = _new_slide()
    _line(draw, 80)

    y = 200
    follow_font = _cinzel(60)
    _centered(draw, "FOLLOW", y, follow_font, WHITE)
    y += 80

    handle_font = _cinzel(52)
    _centered(draw, f"@{config.IG_HANDLE}", y, handle_font, PINK)
    y += 70

    sub_font = _segoe_light(28)
    _centered(draw, "for weekly updates", y, sub_font, LIGHT)
    y += 60

    _diamond_sep(draw, y)
    y += 30

    url_font = _cinzel(26)
    _centered(draw, "WWW.TULSAGAYS.COM", y, url_font, PINK)
    y += 50

    tagline_font = _segoe_light(24)
    _centered(draw, "Nothing to do? Sounds like a straight person problem.", y, tagline_font, MUTED)

    # Hashtags
    y += 60
    tag_font = _segoe_light(18)
    tags = " ".join(config.HASHTAGS[:8])
    _wrapped_centered(draw, tags, y, tag_font, MUTED)

    _line(draw, 1000)
    return img


# ── Main carousel builder ───────────────────────────────────────────────

def create_weekly_carousel(
    event_of_week: Dict,
    daily_events: Dict[str, Tuple[str, List[Dict]]],
    date_range: str,
) -> List[Image.Image]:
    """Build a full 10-slide weekly carousel.

    Args:
        event_of_week: dict with name, date, time, venue, description, url
        daily_events: dict mapping day name -> (date_str, [events])
            e.g. {"monday": ("March 31", [...]), "tuesday": ("April 1", [...])}
        date_range: e.g. "March 30 - April 5, 2026"

    Returns:
        List of PIL Image objects.
    """
    slides = []

    # 1. Cover
    slides.append(make_cover_slide(date_range))

    # 2. Event of the Week
    slides.append(make_event_of_week_slide(event_of_week))

    # 3-9. Daily slides
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for day in days:
        if day in daily_events:
            date_str, evts = daily_events[day]
            if evts:
                slides.append(make_day_slide(day, date_str, evts))

    # 10. Closing
    slides.append(make_closing_slide())

    return slides


def save_carousel(images: List[Image.Image], output_dir: str,
                  prefix: str = "slide") -> List[str]:
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for i, img in enumerate(images, start=1):
        filename = f"{prefix}_{i:02d}.png"
        filepath = os.path.join(output_dir, filename)
        img.save(filepath, "PNG", optimize=True)
        paths.append(filepath)
    return paths
