"""Generate Instagram carousel images (1080x1080) for Tulsa Gays event posts.

Each carousel includes: cover slide, Homo Hotel Happy Hour slide, category
event slides (community, arts, nightlife), and a closing slide.  Uses
pride-themed design with dark backgrounds and rainbow accents.
"""

import sys
import os
import textwrap
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ── Project imports ──────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ── Constants ────────────────────────────────────────────────────────────
SIZE = (1080, 1080)

# Colors
BG_DARK = "#1a1a2e"
BG_DARK_RGB = (26, 26, 46)
BG_HOMO_HOTEL = "#2a1a0e"  # warm dark base for the HH slide
TEXT_WHITE = "#ffffff"
TEXT_LIGHT = "#e0e0e0"
TEXT_MUTED = "#aaaaaa"
GOLD_ACCENT = "#f0c040"
GOLD_DARK = "#c89b30"

# Pride rainbow colors (top-to-bottom gradient bar order)
PRIDE_COLORS = [
    (228, 3, 3),      # red
    (255, 140, 0),     # orange
    (255, 237, 0),     # yellow
    (0, 128, 38),      # green
    (0, 77, 255),      # blue
    (117, 7, 135),     # purple
]

# Extended pride palette for accent variety
ACCENT_PINK = "#ff6b9d"
ACCENT_PURPLE = "#c77dff"
ACCENT_BLUE = "#48bfe3"
ACCENT_GREEN = "#56e39f"

# Typography sizing
FONT_TITLE_SIZE = 72
FONT_SUBTITLE_SIZE = 42
FONT_HEADING_SIZE = 48
FONT_BODY_SIZE = 32
FONT_SMALL_SIZE = 26
FONT_TINY_SIZE = 22

RAINBOW_BAR_HEIGHT = 12
WATERMARK_SIZE = 80
SLIDE_PADDING = 60
MAX_EVENTS_PER_SLIDE = 5


# ── Font loading ─────────────────────────────────────────────────────────

def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a Windows system font by name, falling back to default."""
    search_paths = [
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    ]
    # Map friendly names to filenames
    font_map = {
        "impact": "impact.ttf",
        "arial": "arial.ttf",
        "arialbd": "arialbd.ttf",
        "ariali": "ariali.ttf",
    }
    filename = font_map.get(name.lower(), f"{name}.ttf")
    for directory in search_paths:
        path = os.path.join(directory, filename)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    # Last resort
    try:
        return ImageFont.truetype(filename, size)
    except OSError:
        return ImageFont.load_default()


def _font_impact(size: int) -> ImageFont.FreeTypeFont:
    return _load_font("impact", size)


def _font_arial(size: int) -> ImageFont.FreeTypeFont:
    return _load_font("arial", size)


def _font_arial_bold(size: int) -> ImageFont.FreeTypeFont:
    return _load_font("arialbd", size)


# ── Drawing helpers ──────────────────────────────────────────────────────

def _new_slide(bg_color: str = BG_DARK) -> Tuple[Image.Image, ImageDraw.Draw]:
    """Create a blank 1080x1080 slide with the given background."""
    img = Image.new("RGB", SIZE, bg_color)
    draw = ImageDraw.Draw(img)
    return img, draw


def _draw_rainbow_bar(draw: ImageDraw.Draw, y: int = 0,
                      height: int = RAINBOW_BAR_HEIGHT) -> int:
    """Draw a horizontal rainbow gradient bar across the top. Returns y after bar."""
    stripe_h = max(height // len(PRIDE_COLORS), 1)
    for i, color in enumerate(PRIDE_COLORS):
        y0 = y + i * stripe_h
        draw.rectangle([0, y0, SIZE[0], y0 + stripe_h], fill=color)
    return y + len(PRIDE_COLORS) * stripe_h


def _draw_rainbow_bar_thick(draw: ImageDraw.Draw, y: int = 0) -> int:
    """Draw a thicker rainbow bar (for cover slides)."""
    return _draw_rainbow_bar(draw, y, height=24)


def _add_watermark(img: Image.Image, logo_path: str,
                   position: str = "bottom_right") -> Image.Image:
    """Overlay the Tulsa Gays logo as a small semi-transparent watermark."""
    if not os.path.exists(logo_path):
        return img

    try:
        logo = Image.open(logo_path).convert("RGBA")
        logo = logo.resize((WATERMARK_SIZE, WATERMARK_SIZE), Image.LANCZOS)

        # Make semi-transparent
        alpha = logo.split()[3]
        alpha = alpha.point(lambda p: int(p * 0.5))
        logo.putalpha(alpha)

        margin = 20
        if position == "bottom_right":
            pos = (SIZE[0] - WATERMARK_SIZE - margin,
                   SIZE[1] - WATERMARK_SIZE - margin)
        elif position == "bottom_left":
            pos = (margin, SIZE[1] - WATERMARK_SIZE - margin)
        elif position == "top_right":
            pos = (SIZE[0] - WATERMARK_SIZE - margin, margin + RAINBOW_BAR_HEIGHT + 4)
        else:
            pos = (margin, margin + RAINBOW_BAR_HEIGHT + 4)

        img.paste(logo, pos, logo)
    except Exception:
        pass  # Gracefully skip if logo can't be loaded

    return img


def _draw_text_centered(draw: ImageDraw.Draw, text: str,
                        y: int, font: ImageFont.FreeTypeFont,
                        fill: str = TEXT_WHITE) -> int:
    """Draw centered text. Returns the y position after the text."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (SIZE[0] - tw) // 2
    draw.text((x, y), text, font=font, fill=fill)
    return y + th


def _draw_text_wrapped(draw: ImageDraw.Draw, text: str,
                       x: int, y: int, max_width: int,
                       font: ImageFont.FreeTypeFont,
                       fill: str = TEXT_WHITE,
                       line_spacing: int = 6) -> int:
    """Draw word-wrapped text within max_width. Returns y after last line."""
    # Estimate chars per line from average char width
    avg_char_w = draw.textlength("M", font=font)
    chars_per_line = max(int(max_width / avg_char_w), 10)
    lines = textwrap.wrap(text, width=chars_per_line)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_h = bbox[3] - bbox[1]
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h + line_spacing
    return y


def _draw_divider(draw: ImageDraw.Draw, y: int,
                  color: str = "#444466", margin: int = SLIDE_PADDING) -> int:
    """Draw a subtle horizontal divider line."""
    draw.line([(margin, y), (SIZE[0] - margin, y)], fill=color, width=1)
    return y + 12


def _draw_event_block(draw: ImageDraw.Draw, event: Dict,
                      x: int, y: int, max_width: int,
                      name_color: str = ACCENT_PINK) -> int:
    """Draw a single event block (name, date/time, venue, url). Returns y after block."""
    font_name = _font_arial_bold(FONT_BODY_SIZE)
    font_detail = _font_arial(FONT_SMALL_SIZE)

    # Event name
    name = event.get("name", "Untitled Event")
    y = _draw_text_wrapped(draw, name, x, y, max_width, font_name, fill=name_color)
    y += 2

    # Date & time
    date_str = event.get("date", "")
    time_str = event.get("time", "")
    dt_line = " | ".join(filter(None, [date_str, time_str]))
    if dt_line:
        draw.text((x, y), dt_line, font=font_detail, fill=TEXT_LIGHT)
        bbox = draw.textbbox((0, 0), dt_line, font=font_detail)
        y += (bbox[3] - bbox[1]) + 4

    # Venue / location
    venue = event.get("venue", event.get("location", ""))
    if venue:
        venue_icon = f"@ {venue}"
        draw.text((x, y), venue_icon, font=font_detail, fill=TEXT_MUTED)
        bbox = draw.textbbox((0, 0), venue_icon, font=font_detail)
        y += (bbox[3] - bbox[1]) + 4

    # Description / pitch (brief exciting blurb)
    desc = event.get("description", "")
    if desc:
        # Truncate to ~80 chars for slide readability
        if len(desc) > 85:
            desc = desc[:82].rsplit(" ", 1)[0] + "..."
        font_desc = _font_arial(FONT_SMALL_SIZE)
        y = _draw_text_wrapped(draw, desc, x, y, max_width, font_desc, fill=TEXT_LIGHT)
        y += 4

    # URL
    url = event.get("url", event.get("link", ""))
    if url:
        # Shorten long URLs for readability
        display_url = url
        if len(display_url) > 50:
            display_url = display_url[:47] + "..."
        font_url = _font_arial(FONT_TINY_SIZE)
        draw.text((x, y), display_url, font=font_url, fill=ACCENT_BLUE)
        bbox = draw.textbbox((0, 0), display_url, font=font_url)
        y += (bbox[3] - bbox[1]) + 4

    return y + 10  # padding after block


# ── Slide generators ─────────────────────────────────────────────────────

def make_cover_slide(post_type: str, date_range: str) -> Image.Image:
    """Create the cover slide for a carousel.

    Args:
        post_type: "weekday" or "weekend"
        date_range: e.g. "Mar 31 - Apr 2"
    """
    img, draw = _new_slide(BG_DARK)
    y = _draw_rainbow_bar_thick(draw, 0)

    # Large centered title
    title_font = _font_impact(FONT_TITLE_SIZE)
    label = "WEEKDAY EVENTS" if post_type == "weekday" else "WEEKEND EVENTS"

    y += 180
    y = _draw_text_centered(draw, label, y, title_font, TEXT_WHITE)

    # Date range
    y += 30
    range_font = _font_arial_bold(FONT_SUBTITLE_SIZE)
    y = _draw_text_centered(draw, date_range, y, range_font, ACCENT_PURPLE)

    # Decorative rainbow stripe in the middle area
    y += 50
    _draw_rainbow_bar(draw, y, height=6)
    y += 30

    # Branding
    brand_font = _font_impact(FONT_SUBTITLE_SIZE)
    y = _draw_text_centered(draw, "TULSA GAYS", y + 20, brand_font, ACCENT_PINK)
    y += 10
    tagline_font = _font_arial(FONT_SMALL_SIZE)
    _draw_text_centered(draw, "Your Weekly LGBTQ+ Event Guide", y,
                        tagline_font, TEXT_MUTED)

    # Bottom rainbow bar
    _draw_rainbow_bar(draw, SIZE[1] - RAINBOW_BAR_HEIGHT, RAINBOW_BAR_HEIGHT)

    img = _add_watermark(img, config.LOGO_PATH, "bottom_right")
    return img


def make_homo_hotel_slide(event: Dict) -> Image.Image:
    """Create the Homo Hotel Happy Hour feature slide (always slide 2).

    Uses warm gold/amber tones to make it visually distinct.
    """
    img, draw = _new_slide(BG_HOMO_HOTEL)

    # Gold-toned rainbow bar
    y = _draw_rainbow_bar(draw, 0)

    # Gold accent line
    draw.rectangle([0, y, SIZE[0], y + 4], fill=GOLD_ACCENT)
    y += 4

    y += 60

    # Title
    title_font = _font_impact(60)
    y = _draw_text_centered(draw, "HOMO HOTEL", y, title_font, GOLD_ACCENT)
    y += 5
    y = _draw_text_centered(draw, "HAPPY HOUR", y, title_font, GOLD_ACCENT)

    # Decorative gold divider
    y += 25
    bar_w = 300
    bar_x = (SIZE[0] - bar_w) // 2
    draw.rectangle([bar_x, y, bar_x + bar_w, y + 3], fill=GOLD_DARK)
    y += 30

    # Event details
    detail_font = _font_arial_bold(FONT_BODY_SIZE)
    small_font = _font_arial(FONT_BODY_SIZE)
    label_font = _font_arial(FONT_SMALL_SIZE)

    date_str = event.get("date", "")
    time_str = event.get("time", "")
    venue = event.get("venue", event.get("location", ""))
    description = event.get("description", "")

    if date_str:
        y = _draw_text_centered(draw, date_str, y, detail_font, TEXT_WHITE)
        y += 12
    if time_str:
        y = _draw_text_centered(draw, time_str, y, small_font, TEXT_LIGHT)
        y += 12
    if venue:
        y += 8
        y = _draw_text_centered(draw, venue, y, detail_font, GOLD_ACCENT)
        y += 12
    if description:
        y += 10
        desc_font = _font_arial(FONT_SMALL_SIZE)
        center_x = SLIDE_PADDING + 20
        max_w = SIZE[0] - 2 * (SLIDE_PADDING + 20)
        y = _draw_text_wrapped(draw, description, center_x, y, max_w,
                               desc_font, TEXT_LIGHT)

    # URL if present
    url = event.get("url", event.get("link", ""))
    if url:
        y += 16
        url_font = _font_arial(FONT_TINY_SIZE)
        y = _draw_text_centered(draw, url, y, url_font, ACCENT_BLUE)

    # Bottom gold accent
    draw.rectangle([0, SIZE[1] - 6, SIZE[0], SIZE[1]], fill=GOLD_DARK)
    _draw_rainbow_bar(draw, SIZE[1] - 6 - RAINBOW_BAR_HEIGHT, RAINBOW_BAR_HEIGHT)

    img = _add_watermark(img, config.LOGO_PATH, "bottom_right")
    return img


def make_category_slide(category_name: str, events: List[Dict]) -> Image.Image:
    """Create a slide showing events for one category.

    Args:
        category_name: e.g. "Community Events", "Arts & Culture", "Nightlife"
        events: list of event dicts with keys: name, date, time, venue, url
    """
    img, draw = _new_slide(BG_DARK)
    y = _draw_rainbow_bar(draw, 0)

    # Category header
    y += 30
    header_font = _font_impact(FONT_HEADING_SIZE)

    # Pick accent color based on category
    cat_lower = category_name.lower()
    if "community" in cat_lower:
        header_color = ACCENT_GREEN
        event_name_color = ACCENT_GREEN
    elif "art" in cat_lower or "culture" in cat_lower:
        header_color = ACCENT_PURPLE
        event_name_color = ACCENT_PURPLE
    elif "nightlife" in cat_lower or "bar" in cat_lower:
        header_color = ACCENT_PINK
        event_name_color = ACCENT_PINK
    else:
        header_color = ACCENT_BLUE
        event_name_color = ACCENT_BLUE

    y = _draw_text_centered(draw, category_name.upper(), y, header_font, header_color)
    y += 15
    y = _draw_divider(draw, y, color=header_color)
    y += 10

    # Render events (cap at MAX_EVENTS_PER_SLIDE)
    x = SLIDE_PADDING
    max_w = SIZE[0] - 2 * SLIDE_PADDING
    displayed = events[:MAX_EVENTS_PER_SLIDE]

    for i, event in enumerate(displayed):
        y = _draw_event_block(draw, event, x, y, max_w,
                              name_color=event_name_color)
        if i < len(displayed) - 1:
            y = _draw_divider(draw, y, color="#333355")

        # Safety: stop if we're running out of vertical space
        if y > SIZE[1] - 120:
            break

    # If events were truncated, note it
    if len(events) > MAX_EVENTS_PER_SLIDE:
        note_font = _font_arial(FONT_TINY_SIZE)
        note = f"+{len(events) - MAX_EVENTS_PER_SLIDE} more - see blog for full list"
        _draw_text_centered(draw, note, SIZE[1] - 80, note_font, TEXT_MUTED)

    # Bottom bar
    _draw_rainbow_bar(draw, SIZE[1] - RAINBOW_BAR_HEIGHT, RAINBOW_BAR_HEIGHT)

    img = _add_watermark(img, config.LOGO_PATH, "bottom_right")
    return img


def make_closing_slide() -> Image.Image:
    """Create the closing CTA slide with follow prompt and hashtags."""
    img, draw = _new_slide(BG_DARK)
    y = _draw_rainbow_bar_thick(draw, 0)

    y += 160

    # Follow CTA
    cta_font = _font_impact(FONT_TITLE_SIZE)
    y = _draw_text_centered(draw, "FOLLOW", y, cta_font, TEXT_WHITE)
    y += 10

    handle_font = _font_impact(64)
    y = _draw_text_centered(draw, f"@{config.IG_HANDLE}", y, handle_font, ACCENT_PINK)
    y += 15

    sub_font = _font_arial(FONT_SUBTITLE_SIZE)
    y = _draw_text_centered(draw, "for weekly updates", y, sub_font, TEXT_LIGHT)

    # Decorative divider
    y += 40
    _draw_rainbow_bar(draw, y, height=6)
    y += 30

    # Blog URL
    url_font = _font_arial_bold(FONT_BODY_SIZE)
    y = _draw_text_centered(draw, config.BLOG_URL, y, url_font, ACCENT_BLUE)

    # Hashtags (pick a subset to fit)
    y += 40
    tag_font = _font_arial(FONT_TINY_SIZE)
    tag_line = " ".join(config.HASHTAGS[:8])
    _draw_text_wrapped(draw, tag_line, SLIDE_PADDING, y,
                       SIZE[0] - 2 * SLIDE_PADDING, tag_font, TEXT_MUTED)

    # Bottom bar
    _draw_rainbow_bar(draw, SIZE[1] - RAINBOW_BAR_HEIGHT, RAINBOW_BAR_HEIGHT)

    img = _add_watermark(img, config.LOGO_PATH, "bottom_right")
    return img


# ── Main carousel builders ───────────────────────────────────────────────

def create_carousel(events_by_category: Dict[str, List[Dict]],
                    post_type: str,
                    date_range: str,
                    logo_path: Optional[str] = None) -> List[Image.Image]:
    """Build a full carousel of slides from categorized events.

    Args:
        events_by_category: dict mapping category keys to lists of event dicts.
            Expected keys: "homo_hotel", "community", "arts", "nightlife"
            Each event dict should have: name, date, time, venue, url
            The "homo_hotel" value should be a single-item list.
        post_type: "weekday" or "weekend"
        date_range: human-readable date range, e.g. "Mar 31 - Apr 4"
        logo_path: path to logo PNG (defaults to config.LOGO_PATH)

    Returns:
        List of PIL Image objects (one per slide).
    """
    if logo_path:
        # Temporarily override for this run
        original = config.LOGO_PATH
        config.LOGO_PATH = logo_path

    slides: List[Image.Image] = []

    # 1. Cover slide
    slides.append(make_cover_slide(post_type, date_range))

    # 2. Homo Hotel Happy Hour (ALWAYS second)
    hh_events = events_by_category.get("homo_hotel", [])
    if hh_events:
        slides.append(make_homo_hotel_slide(hh_events[0]))
    else:
        # Create a placeholder HH slide even if no event data yet
        placeholder = {
            "name": "Homo Hotel Happy Hour",
            "date": "Check @tulsagays for details",
            "time": "",
            "venue": "TBA",
            "description": "The signature weekly happy hour for the Tulsa LGBTQ+ community.",
        }
        slides.append(make_homo_hotel_slide(placeholder))

    # 3. Community Events
    community = events_by_category.get("community", [])
    if community:
        slides.append(make_category_slide("Community Events", community))

    # 4. Arts & Culture
    arts = events_by_category.get("arts", [])
    if arts:
        slides.append(make_category_slide("Arts & Culture", arts))

    # 5. Nightlife (only if special events exist)
    nightlife = events_by_category.get("nightlife", [])
    if nightlife:
        slides.append(make_category_slide("Nightlife", nightlife))

    # 6. Closing slide
    slides.append(make_closing_slide())

    if logo_path:
        config.LOGO_PATH = original

    return slides


def save_carousel(images: List[Image.Image], output_dir: str,
                  prefix: str = "slide") -> List[str]:
    """Save a list of PIL Images to disk as numbered PNGs.

    Args:
        images: list of PIL Image objects
        output_dir: directory to save into (created if needed)
        prefix: filename prefix, e.g. "weekday_2026w13"

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


# ── CLI quick test ───────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Generating sample carousel...")

    sample_events = {
        "homo_hotel": [{
            "name": "Homo Hotel Happy Hour",
            "date": "Wednesday, Apr 2",
            "time": "5:00 PM - 8:00 PM",
            "venue": "The Venue, 123 Main St",
            "description": "Join us for the weekly happy hour!",
            "url": "https://tulsagays.github.io/events",
        }],
        "community": [
            {
                "name": "OKEQ Support Group",
                "date": "Tuesday, Apr 1",
                "time": "6:30 PM",
                "venue": "Dennis R. Neill Equality Center",
                "url": "https://www.okeq.org/events",
            },
            {
                "name": "All Souls LGBTQ Fellowship",
                "date": "Wednesday, Apr 2",
                "time": "7:00 PM",
                "venue": "All Souls Unitarian Church",
                "url": "https://www.allsoulschurch.org",
            },
        ],
        "arts": [
            {
                "name": "Drag Bingo Night",
                "date": "Thursday, Apr 3",
                "time": "8:00 PM",
                "venue": "Twisted Arts Tulsa",
                "url": "https://www.twistedartstulsa.com",
            },
        ],
        "nightlife": [],
    }

    slides = create_carousel(sample_events, "weekday", "Mar 31 - Apr 4")
    out_dir = os.path.join(config.DATA_DIR, "sample_carousel")
    paths = save_carousel(slides, out_dir, prefix="sample")
    print(f"Saved {len(paths)} slides to {out_dir}/")
    for p in paths:
        print(f"  {p}")
