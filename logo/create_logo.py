"""Generate Tulsa Gays branding assets in Art Deco / Mid-Century Modern style.

Matches the carousel DESIGN_STANDARD.md:
- Dark bg (#0a0a0a), dark gold (#8B7234), deep peacock (#00838F)
- Burnt orange (#BF5700), hunter green (#355E3B)
- Impact font for titles
"""
from PIL import Image, ImageDraw, ImageFont
import os

# ── Design Standard Colors ──────────────────────────────────────────────
BG = (10, 10, 10)
DARK_GOLD = "#8B7234"
GOLD_RGB = (139, 114, 52)
MCM_GOLD_LIGHT = "#A89050"
PEACOCK = "#00838F"
PEACOCK_RGB = (0, 131, 143)
BURNT_ORANGE = "#BF5700"
BURNT_ORANGE_RGB = (191, 87, 0)
HUNTER_GREEN = "#355E3B"
HUNTER_RGB = (53, 94, 59)
CREAM = "#F5E6C8"
DARK_GRAY = "#555555"
GRAY = "#999999"


def _font(name, size):
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    mapping = {
        "impact": "impact.ttf",
        "segoe-bold": "segoeuib.ttf",
        "segoe-light": "segoeuil.ttf",
        "segoe-semibold": "seguisb.ttf",
        "segoe": "segoeui.ttf",
    }
    path = os.path.join(fonts_dir, mapping.get(name, f"{name}.ttf"))
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _centered(draw, text, y, font, fill, width):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (width - tw) // 2
    draw.text((x, y), text, font=font, fill=fill)
    return y + (bbox[3] - bbox[1])


def _deco_double(draw, y, width, color=DARK_GOLD, margin=0):
    draw.rectangle([margin, y, width - margin, y], fill=color)
    draw.rectangle([margin, y + 4, width - margin, y + 4], fill=color)


def _diamond(draw, cx, cy, size=6, color=DARK_GOLD):
    draw.polygon([(cx, cy - size), (cx + size, cy),
                  (cx, cy + size), (cx - size, cy)], fill=color)


def create_profile_pic(size=1080):
    """Square profile picture — HUGE bold TG, nothing else. Must read at 110px."""
    img = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(img)

    # Just a massive TG centered — this is all that matters at badge size
    t_font = _font("impact", 480)

    # Measure T and G separately
    t_bbox = draw.textbbox((0, 0), "T", font=t_font)
    g_bbox = draw.textbbox((0, 0), "G", font=t_font)
    t_w = t_bbox[2] - t_bbox[0]
    g_w = g_bbox[2] - g_bbox[0]
    total_w = t_w + g_w + 10
    th = t_bbox[3] - t_bbox[1]

    tx = (size - total_w) // 2
    ty = (size - th) // 2 - 20

    # T in gold, G in peacock
    draw.text((tx, ty), "T", font=t_font, fill=DARK_GOLD)
    draw.text((tx + t_w + 10, ty), "G", font=t_font, fill=PEACOCK)

    # Gold underline just wider than the letters
    line_y = ty + th + 120
    line_pad = 30  # extend this much beyond each side of the text
    line_x1 = tx - line_pad
    line_x2 = tx + total_w + line_pad
    draw.rectangle([line_x1, line_y, line_x2, line_y + 8], fill=DARK_GOLD)

    # Thick burnt orange bar at very bottom (visible even tiny)
    draw.rectangle([0, size - 30, size, size], fill=BURNT_ORANGE)

    return img


def create_cover_image(width=1500, height=500):
    """Facebook/banner cover image — wide deco style."""
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    # Top accent bar
    draw.rectangle([0, 0, width, 4], fill=BURNT_ORANGE)

    # Deco double line
    _deco_double(draw, 80, width, DARK_GOLD, margin=200)

    # "TULSA GAYS" centered
    tulsa_font = _font("impact", 120)
    gays_font = _font("impact", 120)

    # Measure for centering as one unit
    t_bbox = draw.textbbox((0, 0), "TULSA ", font=tulsa_font)
    g_bbox = draw.textbbox((0, 0), "GAYS", font=gays_font)
    total_w = (t_bbox[2] - t_bbox[0]) + (g_bbox[2] - g_bbox[0])
    start_x = (width - total_w) // 2
    y = 130

    draw.text((start_x, y), "TULSA ", font=tulsa_font, fill=DARK_GOLD)
    draw.text((start_x + t_bbox[2] - t_bbox[0], y), "GAYS", font=gays_font, fill=PEACOCK)

    # Deco double line below title
    title_h = t_bbox[3] - t_bbox[1]
    _deco_double(draw, y + title_h + 30, width, DARK_GOLD, margin=200)

    # Tagline
    tag_font = _font("segoe-semibold", 36)
    _centered(draw, "YOUR WEEKLY LGBTQ+ EVENT GUIDE FOR TULSA", y + title_h + 60,
              tag_font, CREAM, width)

    # Deco divider: line — diamond — line (wider spacing)
    div_y = y + title_h + 115
    cx = width // 2
    line_len = 120
    draw.rectangle([cx - line_len - 15, div_y, cx - 15, div_y + 1], fill=DARK_GOLD)
    _diamond(draw, cx, div_y, 6, DARK_GOLD)
    draw.rectangle([cx + 15, div_y, cx + line_len + 15, div_y + 1], fill=DARK_GOLD)

    # Sassy subtitle — more breathing room
    sub_font = _font("segoe", 26)
    _centered(draw, "Nothing to do in Tulsa? Sounds like a straight person problem.",
              div_y + 25, sub_font, GRAY, width)

    # Bottom accent
    draw.rectangle([0, height - 4, width, height], fill=HUNTER_GREEN)

    return img


def create_story_highlight_cover(label, size=1080):
    """Instagram story highlight cover — small deco circle style."""
    img = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(img)

    # Gold circle border
    center = size // 2
    radius = 400
    draw.ellipse([center - radius, center - radius,
                  center + radius, center + radius],
                 outline=DARK_GOLD, width=3)
    draw.ellipse([center - radius + 12, center - radius + 12,
                  center + radius - 12, center + radius - 12],
                 outline=DARK_GOLD, width=1)

    # Label text centered
    font = _font("impact", 80)
    _centered(draw, label.upper(), center - 30, font, CREAM, size)

    return img


if __name__ == "__main__":
    output_dir = os.path.dirname(os.path.abspath(__file__))

    # Profile picture
    profile = create_profile_pic(1080)
    profile_path = os.path.join(output_dir, "tulsagays_profile.png")
    profile.save(profile_path, "PNG", optimize=True)
    # Small version
    small = profile.resize((320, 320), Image.LANCZOS)
    small.save(os.path.join(output_dir, "tulsagays_profile_320.png"), "PNG")
    print(f"Profile: {profile_path}")

    # Cover image
    cover = create_cover_image(1500, 500)
    cover_path = os.path.join(output_dir, "tulsagays_cover.png")
    cover.save(cover_path, "PNG", optimize=True)
    print(f"Cover: {cover_path}")

    # Story highlight covers
    highlights = ["Events", "HHHH", "Nightlife", "Arts", "Community"]
    for h in highlights:
        hi = create_story_highlight_cover(h)
        hi_path = os.path.join(output_dir, f"highlight_{h.lower()}.png")
        hi.save(hi_path, "PNG", optimize=True)
        print(f"Highlight: {hi_path}")

    print("\nAll branding assets generated!")
