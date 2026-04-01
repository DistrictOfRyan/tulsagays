"""Generate minimal, modern Instagram carousel slides (1080x1080) for Tulsa Gays.

Clean dark-background design with typography-focused layout, subtle accent
colors per category, and no visual clutter. Max 3 events per slide.
"""

import re
import sys
import os
import textwrap
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

# ── Project imports ──────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ── Constants ────────────────────────────────────────────────────────────
SIZE = (1080, 1080)
W, H = SIZE

# Backgrounds
BG = "#0a0a0a"
BG_RGB = (10, 10, 10)

# Text colors
WHITE = "#ffffff"
GRAY = "#999999"
DARK_GRAY = "#555555"
LIGHT = "#cccccc"

# Accent palette (one per category)
MCM_DARK_GOLD = "#D4A574"   # warm amber for HHHH
ACCENT_COMMUNITY = "#8BA888"  # soft sage
ACCENT_ARTS = "#9B8EC4"       # muted lavender
ACCENT_NIGHTLIFE = "#C4848B"  # dusty rose
ACCENT_DEFAULT = "#888888"    # neutral fallback
# ── Mid-Century Deco Palette ─────────────────────────────────────────────
MCM_DARK_GOLD = "#8B7234"     # deep warm gold (not yellow)
MCM_GOLD_LIGHT = "#A89050"    # lighter gold for accents
MCM_PEACOCK = "#006D6F"       # deep peacock teal
MCM_PEACOCK_LIGHT = "#00838F" # deep peacock, still readable on dark
MCM_HUNTER = "#355E3B"        # hunter green
MCM_BURNT_ORANGE = "#BF5700"  # burnt orange
MCM_CREAM = "#F5E6C8"         # warm cream for text

# Subtle rainbow for the 3px top line
RAINBOW = [
    (228, 3, 3),    # red
    (255, 140, 0),  # orange
    (255, 237, 0),  # yellow
    (0, 128, 38),   # green
    (0, 77, 255),   # blue
    (117, 7, 135),  # purple
]

# Layout
PAD = 80            # slide edge padding
MAX_EVENTS = 3      # max events per category slide
NAME_MAX = 45       # truncate event names
DESC_MAX = 70       # truncate descriptions
RAINBOW_H = 3       # thin rainbow line height

# Sassy cover tagline (rotate these weekly for variety)
COVER_TAGLINES = [
    "Nothing to do in Tulsa? Sounds like a straight person problem.",
    "There's only nothing to do in Tulsa if you're boring.",
    "If you're bored in Tulsa, that's a you problem.",
    "You said there's nothing to do? Girl, keep up.",
    "Boring people say Tulsa is boring. We stay booked.",
    "Tulsa has nothing to do? You're just not invited to the right things.",
]

# Skip garbage event names
SKIP_NAMES = {"event calendar", "events", "calendar", "untitled", ""}


# ── Font loading ─────────────────────────────────────────────────────────

def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a Windows system font, falling back gracefully."""
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    mapping = {
        "segoe": "segoeui.ttf",
        "segoe-light": "segoeuil.ttf",
        "segoe-bold": "segoeuib.ttf",
        "segoe-semibold": "seguisb.ttf",
        "arial": "arial.ttf",
        "arial-bold": "arialbd.ttf",
        "impact": "impact.ttf",
    }
    filename = mapping.get(name.lower(), f"{name}.ttf")
    path = os.path.join(fonts_dir, filename)
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    # Try raw filename
    try:
        return ImageFont.truetype(filename, size)
    except OSError:
        pass
    # Fallback chain: try Arial, then default
    for fallback in ["arial.ttf", "arialbd.ttf"]:
        fb_path = os.path.join(fonts_dir, fallback)
        if os.path.exists(fb_path):
            return ImageFont.truetype(fb_path, size)
    return ImageFont.load_default()


# ── Text helpers ─────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Strip emoji, non-ASCII decorative chars, and excess whitespace."""
    if not text:
        return ""
    # Remove emoji and misc symbols (broad Unicode ranges)
    text = re.sub(
        r'[\U0001F600-\U0001F64F'   # emoticons
        r'\U0001F300-\U0001F5FF'     # symbols & pictographs
        r'\U0001F680-\U0001F6FF'     # transport & map
        r'\U0001F1E0-\U0001F1FF'     # flags
        r'\U00002702-\U000027B0'     # dingbats
        r'\U0000FE00-\U0000FE0F'     # variation selectors
        r'\U0001F900-\U0001F9FF'     # supplemental symbols
        r'\U0001FA00-\U0001FA6F'     # chess symbols
        r'\U0001FA70-\U0001FAFF'     # symbols extended-A
        r'\U00002600-\U000026FF'     # misc symbols
        r'\U0000200D'                # zero width joiner
        r'\U0000231A-\U0000231B'     # watch/hourglass
        r'\U00002B50'                # star
        r'\U000023F0-\U000023F3'     # clocks
        r']+', '', text
    )
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def format_date(date_str: str) -> str:
    """Convert various date formats to 'Thu, Apr 3' style.

    Handles: '2026-04-03', 'April 3, 2026', 'Thursday, April 3',
    'Apr 3', and already-formatted strings.
    """
    if not date_str:
        return ""

    date_str = date_str.strip()

    # Already short format like "Thu, Apr 3"
    if re.match(r'^[A-Z][a-z]{2}, [A-Z][a-z]{2} \d{1,2}$', date_str):
        return date_str

    # Try ISO format: 2026-04-03
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%a, %b %-d") if os.name != 'nt' else dt.strftime("%a, %b %#d")
    except ValueError:
        pass

    # Try common formats
    for fmt in ["%B %d, %Y", "%A, %B %d", "%A, %B %d, %Y",
                "%b %d, %Y", "%b %d", "%B %d"]:
        try:
            dt = datetime.strptime(date_str, fmt)
            # If year wasn't in format, keep current year
            if dt.year == 1900:
                dt = dt.replace(year=datetime.now().year)
            return dt.strftime("%a, %b %-d") if os.name != 'nt' else dt.strftime("%a, %b %#d")
        except ValueError:
            continue

    # Strip day-of-week prefix if present: "Wednesday, Apr 2" -> "Wed, Apr 2"
    m = re.match(r'^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s*(.+)$',
                 date_str, re.IGNORECASE)
    if m:
        remainder = m.group(1)
        for fmt in ["%B %d", "%b %d", "%B %d, %Y", "%b %d, %Y"]:
            try:
                dt = datetime.strptime(remainder.strip(), fmt)
                if dt.year == 1900:
                    dt = dt.replace(year=datetime.now().year)
                return dt.strftime("%a, %b %-d") if os.name != 'nt' else dt.strftime("%a, %b %#d")
            except ValueError:
                continue

    # Give up, return cleaned original
    return date_str


def _truncate(text: str, limit: int) -> str:
    """Truncate text to limit, adding ellipsis if needed."""
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[:limit - 1].rsplit(" ", 1)[0] + "..."


def _is_garbage_event(event: Dict) -> bool:
    """Return True if event should be skipped."""
    name = clean_text(event.get("name", "")).lower().strip()
    return name in SKIP_NAMES or len(name) < 3


# ── Drawing primitives ───────────────────────────────────────────────────

def _new_slide() -> Tuple[Image.Image, ImageDraw.Draw]:
    """Create a blank 1080x1080 dark slide."""
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)
    return img, draw


def _rainbow_line(draw: ImageDraw.Draw, y: int = 0, height: int = RAINBOW_H):
    """Draw a thin rainbow gradient line across the full width."""
    segment_w = W // len(RAINBOW)
    for i, color in enumerate(RAINBOW):
        x0 = i * segment_w
        x1 = (i + 1) * segment_w if i < len(RAINBOW) - 1 else W
        draw.rectangle([x0, y, x1, y + height - 1], fill=color)


def _centered_text(draw: ImageDraw.Draw, text: str, y: int,
                   font: ImageFont.FreeTypeFont, fill: str = WHITE) -> int:
    """Draw horizontally centered text. Returns y after text."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (W - tw) // 2
    draw.text((x, y), text, font=font, fill=fill)
    return y + th


def _thin_line(draw: ImageDraw.Draw, y: int, color: str = DARK_GRAY,
               margin: int = PAD) -> int:
    """Draw a subtle 1px divider line. Returns y after line + gap."""
    draw.line([(margin, y), (W - margin, y)], fill=color, width=1)
    return y + 20


def _watermark(draw: ImageDraw.Draw):
    """Draw small 'TULSA GAYS' watermark in bottom-right corner."""
    font = _font("segoe", 16)
    text = "TULSA GAYS"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = W - tw - 30
    y = H - 40
    draw.text((x, y), text, font=font, fill=DARK_GRAY)


def _accent_dot(draw: ImageDraw.Draw, x: int, y: int, color: str, r: int = 4):
    """Draw a small colored dot."""
    draw.ellipse([x - r, y - r, x + r, y + r], fill=color)


# ── Slide generators ─────────────────────────────────────────────────────

def _deco_line(draw: ImageDraw.Draw, y: int, color: str = MCM_DARK_GOLD,
               margin: int = 200, thickness: int = 2) -> int:
    """Draw an Art Deco style decorative line."""
    draw.rectangle([margin, y, W - margin, y + thickness - 1], fill=color)
    return y + thickness + 10


def _deco_double_line(draw: ImageDraw.Draw, y: int, color: str = MCM_DARK_GOLD,
                      margin: int = 250) -> int:
    """Draw Art Deco double-line accent."""
    draw.rectangle([margin, y, W - margin, y], fill=color)
    draw.rectangle([margin, y + 4, W - margin, y + 4], fill=color)
    return y + 15


def make_cover_slide(post_type: str, date_range: str,
                     tagline: Optional[str] = None) -> Image.Image:
    """Cover slide: Art Deco / mid-century modern style."""
    img, draw = _new_slide()

    # Pick a tagline
    if tagline is None:
        week_num = datetime.now().isocalendar()[1]
        tagline = COVER_TAGLINES[week_num % len(COVER_TAGLINES)]

    # Fonts — Impact for deco bold feel, Segoe for supporting text
    title_font = _font("impact", 50)
    tulsa_font = _font("impact", 110)
    gays_font = _font("impact", 110)
    date_font = _font("segoe-light", 34)
    tagline_font = _font("segoe-semibold", 24)
    brand_font = _font("segoe-bold", 20)

    # Top deco accent — burnt orange line
    draw.rectangle([0, 0, W, 4], fill=MCM_BURNT_ORANGE)

    # Deco double line
    y = 200
    _deco_double_line(draw, y, MCM_DARK_GOLD, margin=300)
    y += 30

    # "THIS WEEK" / "THIS WEEKEND" in burnt orange
    title = "THIS WEEKEND" if post_type == "weekend" else "THIS WEEK"
    y = _centered_text(draw, title, y, title_font, MCM_BURNT_ORANGE)
    y += 20

    # "TULSA" in dark gold
    y = _centered_text(draw, "TULSA", y, tulsa_font, MCM_DARK_GOLD)
    y += 5

    # "GAYS" in deep peacock
    y = _centered_text(draw, "GAYS", y, gays_font, MCM_PEACOCK_LIGHT)
    y += 20

    # Deco double line under title block
    _deco_double_line(draw, y, MCM_DARK_GOLD, margin=300)
    y += 30

    # Date range in cream
    y = _centered_text(draw, date_range, y, date_font, MCM_CREAM)

    # Sassy tagline
    y += 30
    y = _centered_text(draw, tagline, y, tagline_font, GRAY)

    # Small deco diamond accent
    y += 25
    cx, cy = W // 2, y
    draw.polygon([(cx, cy - 5), (cx + 5, cy), (cx, cy + 5), (cx - 5, cy)],
                 fill=MCM_DARK_GOLD)

    # Bottom branding
    brand_y = H - 80
    _deco_double_line(draw, brand_y - 20, MCM_DARK_GOLD, margin=350)
    # "TULSA" in gold, "GAYS" in burnt orange
    tulsa_bbox = draw.textbbox((0, 0), "TULSA ", font=brand_font)
    gays_bbox = draw.textbbox((0, 0), "GAYS", font=brand_font)
    total_w = (tulsa_bbox[2] - tulsa_bbox[0]) + (gays_bbox[2] - gays_bbox[0])
    bx = (W - total_w) // 2
    draw.text((bx, brand_y), "TULSA ", font=brand_font, fill=MCM_DARK_GOLD)
    draw.text((bx + tulsa_bbox[2] - tulsa_bbox[0], brand_y), "GAYS",
              font=brand_font, fill=MCM_BURNT_ORANGE)

    # Bottom deco line
    draw.rectangle([0, H - 4, W, H], fill=MCM_HUNTER)

    return img


def make_homo_hotel_slide(event: Dict) -> Image.Image:
    """Homo Hotel Happy Hour feature slide -- warm, special, inviting."""
    img, draw = _new_slide()

    # Thin amber accent line at top
    draw.rectangle([0, 0, W, 2], fill=MCM_DARK_GOLD)

    # Build date/time string
    raw_date = event.get("date", "")
    time_str = event.get("time", "")
    venue = event.get("venue", event.get("location", ""))
    description = event.get("description", "")

    nice_date = format_date(raw_date)

    # Layout: centered, generous spacing
    label_font = _font("segoe", 20)
    hero_font = _font("segoe-light", 52)
    detail_font = _font("segoe", 34)
    venue_font = _font("segoe", 28)
    tagline_font = _font("segoe", 22)

    # "FEATURED EVENT OF THE WEEK" label at top
    y = 180
    y = _centered_text(draw, "FEATURED EVENT OF THE WEEK", y, label_font, MCM_PEACOCK_LIGHT)
    y += 40

    # Hero title
    y = _centered_text(draw, "HOMO HOTEL", y, hero_font, MCM_DARK_GOLD)
    y += 6
    y = _centered_text(draw, "HAPPY HOUR", y, hero_font, MCM_DARK_GOLD)

    # Thin gold line
    y += 35
    line_w = 200
    line_x = (W - line_w) // 2
    draw.rectangle([line_x, y, line_x + line_w, y + 1], fill=MCM_DARK_GOLD)
    y += 40

    # Date and time
    if nice_date and time_str:
        dt_line = f"{nice_date}  ·  {time_str}"
    elif nice_date:
        dt_line = nice_date
    elif time_str:
        dt_line = time_str
    else:
        dt_line = ""

    if dt_line:
        y = _centered_text(draw, dt_line, y, detail_font, WHITE)
        y += 20

    # Venue
    if venue:
        venue_clean = clean_text(venue)
        y = _centered_text(draw, f"@ {venue_clean}", y, venue_font, MCM_DARK_GOLD)
        y += 30

    # Tagline
    if description:
        desc_clean = _truncate(description, DESC_MAX)
        y = _centered_text(draw, desc_clean, y, tagline_font, GRAY)
    else:
        y = _centered_text(draw, "The weekly queer happy hour tradition", y,
                           tagline_font, GRAY)

    # Bottom amber accent line
    draw.rectangle([0, H - 2, W, H], fill=MCM_DARK_GOLD)

    _watermark(draw)
    return img


def make_category_slide(category_name: str, events: List[Dict],
                        accent_color: str = ACCENT_DEFAULT) -> Image.Image:
    """Category event slide with up to 3 events, clean layout."""
    img, draw = _new_slide()

    # Filter out garbage events
    events = [e for e in events if not _is_garbage_event(e)]
    if not events:
        return img

    # Thin accent line at top
    draw.rectangle([0, 0, W, 2], fill=accent_color)

    # Category label - small, uppercase, at top
    cat_font = _font("segoe", 20)
    y = 70
    y = _centered_text(draw, category_name.upper(), y, cat_font, accent_color)

    # Thin divider under category name
    y += 20
    line_w = 60
    line_x = (W - line_w) // 2
    draw.rectangle([line_x, y, line_x + line_w, y + 1], fill=accent_color)
    y += 50

    # Render events (max 3)
    displayed = events[:MAX_EVENTS]
    total_events = len(displayed)

    # Calculate vertical spacing to center events
    # Each event block is roughly 130-160px tall
    estimated_block_h = 140
    total_content_h = total_events * estimated_block_h + (total_events - 1) * 20
    available_h = H - y - 120  # leave room for bottom
    start_y = y + max(0, (available_h - total_content_h) // 2)
    y = start_y

    name_font = _font("segoe-bold", 32)
    date_font = _font("segoe", 22)
    venue_font = _font("segoe", 22)
    desc_font = _font("segoe", 19)

    for i, event in enumerate(displayed):
        # Event name (bold, white)
        name = _truncate(event.get("name", "Untitled"), NAME_MAX)
        bbox = draw.textbbox((0, 0), name, font=name_font)
        tw = bbox[2] - bbox[0]
        name_x = (W - tw) // 2
        draw.text((name_x, y), name, font=name_font, fill=WHITE)
        y += (bbox[3] - bbox[1]) + 10

        # Date and time line
        raw_date = event.get("date", "")
        time_str = event.get("time", "")
        nice_date = format_date(raw_date)

        if nice_date and time_str:
            dt_text = f"{nice_date}  ·  {time_str}"
        elif nice_date:
            dt_text = nice_date
        elif time_str:
            dt_text = time_str
        else:
            dt_text = ""

        if dt_text:
            y = _centered_text(draw, dt_text, y, date_font, GRAY)
            y += 8

        # Venue
        venue = event.get("venue", event.get("location", ""))
        if venue:
            venue_text = f"@ {clean_text(venue)}"
            if len(venue_text) > 50:
                venue_text = venue_text[:47] + "..."
            y = _centered_text(draw, venue_text, y, venue_font, accent_color)
            y += 8

        # Brief description
        desc = event.get("description", "")
        if desc:
            desc_clean = _truncate(desc, DESC_MAX)
            y = _centered_text(draw, desc_clean, y, desc_font, DARK_GRAY)
            y += 6

        # Divider between events
        if i < total_events - 1:
            y += 15
            y = _thin_line(draw, y, color="#222222", margin=PAD + 100)
            y += 5

        # Safety: bail if running out of space
        if y > H - 140:
            break

    # "+" note if events were truncated
    if len(events) > MAX_EVENTS:
        remaining = len(events) - MAX_EVENTS
        note_font = _font("segoe", 18)
        note = f"+{remaining} more events at tulsagays.github.io"
        _centered_text(draw, note, H - 90, note_font, DARK_GRAY)

    # Bottom accent line
    draw.rectangle([0, H - 2, W, H], fill=accent_color)

    _watermark(draw)
    return img


def make_closing_slide() -> Image.Image:
    """Closing CTA slide: follow prompt, clean and centered."""
    img, draw = _new_slide()

    # Small rainbow gradient dot cluster at top
    dot_y = 380
    spacing = 14
    start_x = W // 2 - (len(RAINBOW) * spacing) // 2
    for i, color in enumerate(RAINBOW):
        _accent_dot(draw, start_x + i * spacing, dot_y, _rgb_to_hex(color), r=4)

    # Main CTA
    handle_font = _font("segoe-light", 56)
    sub_font = _font("segoe", 26)
    brand_font = _font("segoe", 20)

    y = 420
    y = _centered_text(draw, f"FOLLOW @TULSAGAYS", y, handle_font, WHITE)

    y += 25
    y = _centered_text(draw, "for weekly LGBTQ+ events in Tulsa", y, sub_font, GRAY)

    # Small rainbow line at bottom
    _rainbow_line(draw, y=H - RAINBOW_H, height=RAINBOW_H)

    _watermark(draw)
    return img


def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """Convert RGB tuple to hex string."""
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _get_accent_color(category_name: str) -> str:
    """Pick accent color based on category name."""
    cat = category_name.lower()
    if "community" in cat:
        return ACCENT_COMMUNITY
    elif "art" in cat or "culture" in cat:
        return ACCENT_ARTS
    elif "nightlife" in cat or "bar" in cat or "club" in cat:
        return ACCENT_NIGHTLIFE
    return ACCENT_DEFAULT


# ── Main carousel builders ───────────────────────────────────────────────

def make_featured_slide(event: Dict) -> Image.Image:
    """Featured event slide — the coolest/trendiest event of the week.
    If HHHH is happening, it's always this. Otherwise pick the best one."""
    name = clean_text(event.get("name", ""))
    if "homo hotel" in name.lower():
        return make_homo_hotel_slide(event)

    # Generic featured event with special styling
    img, draw = _new_slide()

    # Rainbow line at top for featured
    _rainbow_line(draw, y=0, height=4)

    raw_date = event.get("date", "")
    time_str = event.get("time", "")
    venue = event.get("venue", event.get("location", ""))
    description = event.get("description", "")
    nice_date = format_date(raw_date)

    label_font = _font("segoe", 20)
    hero_font = _font("segoe-bold", 48)
    detail_font = _font("segoe", 32)
    venue_font = _font("segoe", 26)
    desc_font = _font("segoe", 22)

    y = 220
    y = _centered_text(draw, "FEATURED EVENT OF THE WEEK", y, label_font, MCM_PEACOCK_LIGHT)
    y += 15
    line_w = 80
    line_x = (W - line_w) // 2
    draw.rectangle([line_x, y, line_x + line_w, y + 1], fill=MCM_PEACOCK_LIGHT)
    y += 60

    # Event name (wrap if long)
    event_name = _truncate(name, 60)
    lines = textwrap.wrap(event_name, width=25)
    for line in lines:
        y = _centered_text(draw, line, y, hero_font, WHITE)
        y += 8
    y += 20

    if nice_date and time_str:
        dt_line = f"{nice_date}  ·  {time_str}"
    elif nice_date:
        dt_line = nice_date
    else:
        dt_line = time_str
    if dt_line:
        y = _centered_text(draw, dt_line, y, detail_font, GRAY)
        y += 15

    if venue:
        y = _centered_text(draw, f"@ {clean_text(venue)}", y, venue_font, MCM_PEACOCK_LIGHT)
        y += 25

    if description:
        desc_clean = _truncate(description, 100)
        wrapped = textwrap.wrap(desc_clean, width=45)
        for line in wrapped[:3]:
            y = _centered_text(draw, line, y, desc_font, DARK_GRAY)
            y += 4

    _rainbow_line(draw, y=H - 4, height=4)
    _watermark(draw)
    return img


def make_day_slide(day_name: str, events: List[Dict]) -> Image.Image:
    """Single day slide — shows all events for one day of the week."""
    img, draw = _new_slide()

    events = [e for e in events if not _is_garbage_event(e)]
    if not events:
        # Empty day — still show the day name
        day_font = _font("segoe-light", 48)
        note_font = _font("segoe", 24)
        _rainbow_line(draw, y=0, height=2)
        _centered_text(draw, day_name.upper(), 400, day_font, DARK_GRAY)
        _centered_text(draw, "No events listed yet", 470, note_font, DARK_GRAY)
        _watermark(draw)
        return img

    # Pick accent based on day
    day_accents = {
        "Monday": ACCENT_COMMUNITY,
        "Tuesday": ACCENT_ARTS,
        "Wednesday": "#B8860B",       # dark gold
        "Thursday": ACCENT_NIGHTLIFE,
        "Friday": MCM_DARK_GOLD,
        "Saturday": "#9B8EC4",        # lavender
        "Sunday": MCM_PEACOCK_LIGHT,
    }
    accent = day_accents.get(day_name, ACCENT_DEFAULT)

    # Thin accent line at top
    draw.rectangle([0, 0, W, 2], fill=accent)

    # Day name header
    day_font = _font("segoe-light", 44)
    y = 60
    y = _centered_text(draw, day_name.upper(), y, day_font, accent)
    y += 15
    line_w = 60
    line_x = (W - line_w) // 2
    draw.rectangle([line_x, y, line_x + line_w, y + 1], fill=accent)
    y += 40

    # Render events (up to 4 per day)
    displayed = events[:4]
    name_font = _font("segoe-bold", 30)
    time_font = _font("segoe", 21)
    venue_font = _font("segoe", 21)
    desc_font = _font("segoe", 18)

    for i, event in enumerate(displayed):
        name = _truncate(event.get("name", "Untitled"), NAME_MAX)
        bbox = draw.textbbox((0, 0), name, font=name_font)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, y), name, font=name_font, fill=WHITE)
        y += (bbox[3] - bbox[1]) + 8

        time_str = event.get("time", "")
        if time_str:
            y = _centered_text(draw, time_str, y, time_font, GRAY)
            y += 6

        venue = event.get("venue", event.get("location", ""))
        if venue:
            y = _centered_text(draw, f"@ {clean_text(venue)}", y, venue_font, accent)
            y += 6

        desc = event.get("description", "")
        if desc:
            y = _centered_text(draw, _truncate(desc, DESC_MAX), y, desc_font, DARK_GRAY)
            y += 4

        if i < len(displayed) - 1:
            y += 12
            y = _thin_line(draw, y, color="#222222", margin=PAD + 80)
            y += 8

        if y > H - 120:
            break

    if len(events) > 4:
        remaining = len(events) - 4
        note_font = _font("segoe", 17)
        _centered_text(draw, f"+{remaining} more at tulsagays.github.io", H - 80, note_font, DARK_GRAY)

    draw.rectangle([0, H - 2, W, H], fill=accent)
    _watermark(draw)
    return img


def create_carousel(events_by_category: Dict[str, List[Dict]],
                    post_type: str,
                    date_range: str,
                    logo_path: Optional[str] = None,
                    events_by_day: Optional[Dict[str, List[Dict]]] = None,
                    featured_event: Optional[Dict] = None) -> List[Image.Image]:
    """Build a full carousel: Cover → Featured → Mon-Sun → CTA.

    Args:
        events_by_category: dict mapping category keys to event lists
            (kept for backward compat; used to find HHHH if featured_event not given)
        post_type: "weekday" or "weekend"
        date_range: human-readable range, e.g. "Mar 31 - Apr 6"
        logo_path: unused (kept for API compatibility)
        events_by_day: dict mapping day names to event lists
            e.g. {"Monday": [...], "Tuesday": [...], ...}
        featured_event: the single best event of the week (HHHH if available)

    Returns:
        List of PIL Image objects (one per slide).
    """
    slides: List[Image.Image] = []
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday",
                    "Friday", "Saturday", "Sunday"]

    # 1. Cover slide
    slides.append(make_cover_slide(post_type, date_range))

    # 2. Featured event slide (HHHH always wins if present)
    hh_events = events_by_category.get("homo_hotel", [])
    if featured_event:
        slides.append(make_featured_slide(featured_event))
    elif hh_events:
        slides.append(make_featured_slide(hh_events[0]))
    else:
        # Pick the first interesting event from any category
        for cat in ["community", "arts", "nightlife"]:
            cat_events = events_by_category.get(cat, [])
            valid = [e for e in cat_events if not _is_garbage_event(e)]
            if valid:
                slides.append(make_featured_slide(valid[0]))
                break
        else:
            # No events at all — use HHHH placeholder
            placeholder = {
                "name": "Homo Hotel Happy Hour",
                "date": "", "time": "", "venue": "TBA",
                "description": "The weekly queer happy hour tradition",
            }
            slides.append(make_homo_hotel_slide(placeholder))

    # 3. Daily slides (Monday through Sunday)
    if events_by_day:
        for day in days_of_week:
            day_events = events_by_day.get(day, [])
            slides.append(make_day_slide(day, day_events))
    else:
        # Fallback: use old category format if events_by_day not provided
        category_display = {
            "community": "COMMUNITY",
            "arts": "ARTS & CULTURE",
            "nightlife": "NIGHTLIFE",
        }
        category_colors = {
            "community": ACCENT_COMMUNITY,
            "arts": ACCENT_ARTS,
            "nightlife": ACCENT_NIGHTLIFE,
        }
        for key, display_name in category_display.items():
            events = events_by_category.get(key, [])
            events = [e for e in events if not _is_garbage_event(e)]
            if events:
                slides.append(make_category_slide(
                    display_name, events, category_colors.get(key, ACCENT_DEFAULT)
                ))

    # 4. Closing CTA
    slides.append(make_closing_slide())

    return slides


def save_carousel(images: List[Image.Image], output_dir: str,
                  prefix: str = "slide") -> List[str]:
    """Save slides as numbered PNGs.

    Args:
        images: list of PIL Image objects
        output_dir: directory to save into (created if needed)
        prefix: filename prefix

    Returns:
        List of saved file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for i, img in enumerate(images, start=1):
        filename = f"{prefix}_{i:02d}.png"
        filepath = os.path.join(output_dir, filename)
        img.save(filepath, "PNG", optimize=True)
        paths.append(filepath)
    return paths


# ── CLI test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Generating sample carousel with minimal design...")

    sample_events = {
        "homo_hotel": [{
            "name": "Homo Hotel Happy Hour",
            "date": "2026-04-02",
            "time": "5:00 PM - 8:00 PM",
            "venue": "The Venue, 123 Main St",
            "description": "Join us for the weekly happy hour!",
        }],
        "community": [
            {
                "name": "OKEQ Support Group",
                "date": "2026-04-01",
                "time": "6:30 PM",
                "venue": "Dennis R. Neill Equality Center",
                "description": "Peer support for the LGBTQ+ community",
            },
            {
                "name": "All Souls LGBTQ Fellowship",
                "date": "2026-04-02",
                "time": "7:00 PM",
                "venue": "All Souls Unitarian Church",
            },
            {
                "name": "Tulsa Pride Planning Committee",
                "date": "2026-04-03",
                "time": "6:00 PM",
                "venue": "Equality Center - Room B",
                "description": "Help plan the 2026 Tulsa Pride celebration",
            },
        ],
        "arts": [
            {
                "name": "Drag Bingo Night",
                "date": "2026-04-03",
                "time": "8:00 PM",
                "venue": "Circle Cinema",
                "description": "Fabulous prizes and even more fabulous hosts",
            },
            {
                "name": "Queer Film Screening: Moonlight",
                "date": "2026-04-04",
                "time": "7:30 PM",
                "venue": "Circle Cinema",
            },
        ],
        "nightlife": [
            {
                "name": "Glow Party at Majestic",
                "date": "2026-04-05",
                "time": "10:00 PM",
                "venue": "Majestic Night Club",
                "description": "UV lights, glow paint, and great music all night",
            },
        ],
    }

    slides = create_carousel(sample_events, "weekday", "Mar 31 - Apr 4")
    out_dir = os.path.join(config.DATA_DIR, "sample_carousel")
    paths = save_carousel(slides, out_dir, prefix="sample")

    print(f"Saved {len(paths)} slides to {out_dir}")
    for p in paths:
        print(f"  {p}")
