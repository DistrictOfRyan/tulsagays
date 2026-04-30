"""Generate 1200x630 og:image banners for each Tulsa Gays blog article.

Run standalone:
    python tools/gen_blog_og_images.py

Output: docs/blog/og/<slug>.png (one per article)

Design language matches image_maker.py:
  - Background: #0a0a0a (same as BG in image_maker.py)
  - Top accent bar: Neon Pink #FF1493 (4px, matches pink bars throughout)
  - Headline: white, Poiret One (or Segoe UI / Arial fallback), large, word-wrapped
  - Site name strip: "tulsagays.com" in Neon Pink, bottom center
  - Bottom accent bar: Neon Pink 4px
  - Logo: placed top-right if tulsagays_profile.png exists in logo/
  - Subtle dark purple mid-band for visual depth (#110a0f)
"""

import os
import sys
import textwrap

# ── Dependency check ──────────────────────────────────────────────────────
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("ERROR: Pillow is not installed.")
    print("Install it with:  pip install Pillow")
    sys.exit(1)

# ── Paths ─────────────────────────────────────────────────────────────────
_HERE        = os.path.dirname(os.path.abspath(__file__))
_ROOT        = os.path.dirname(_HERE)
FONTS_DIR    = os.path.join(_ROOT, "fonts")
LOGO_DIR     = os.path.join(_ROOT, "logo")
OUTPUT_DIR   = os.path.join(_ROOT, "docs", "blog", "og")

# ── Canvas ────────────────────────────────────────────────────────────────
W, H = 1200, 630
PAD  = 80          # horizontal side padding for text

# ── Brand Colors (match image_maker.py exactly) ───────────────────────────
BG         = (10, 10, 10)      # #0a0a0a
MID_BAND   = (17, 10, 15)      # #110a0f  subtle dark-purple warmth
NEON_PINK  = "#FF1493"
WHITE      = "#FFFFFF"
LIGHT_GRAY = "#CCCCCC"
DARK_GRAY  = "#333333"

# ── Articles ──────────────────────────────────────────────────────────────
ARTICLES = [
    {
        "slug":     "gay-tulsa-travel-guide",
        "headline": "Gay Tulsa Travel Guide: Is Tulsa LGBTQ+ Friendly?",
        "tag":      "TRAVEL GUIDE",
    },
    {
        "slug":     "new-to-tulsa-queer-starter-pack",
        "headline": "New to Tulsa? Here's Your Queer Starter Pack",
        "tag":      "RELOCATION GUIDE",
    },
    {
        "slug":     "how-we-find-every-queer-event",
        "headline": "How We Find Every Queer Event in Tulsa",
        "tag":      "BEHIND THE SITE",
    },
    {
        "slug":     "date-night-queer-tulsa",
        "headline": "Date Night Ideas for Queer Couples in Tulsa",
        "tag":      "DATE NIGHT",
    },
    {
        "slug":     "lgbtq-sports-tulsa",
        "headline": "LGBTQ+ Sports in Tulsa: Bowling, Kickball, Softball, and More",
        "tag":      "SPORTS + COMMUNITY",
    },
    {
        "slug":     "gilcrease-uncrease-free-arts-series",
        "headline": "Gilcrease UnCrease: Free Arts Events All Spring",
        "tag":      "ARTS + CULTURE",
    },
]

# ── Font Loading ──────────────────────────────────────────────────────────

def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a font by logical name.  Mirrors image_maker._font() lookup order."""
    project_map = {
        "poiret":   "PoiretOne-Regular.ttf",
        "cinzel":   "Cinzel.ttf",
        "playfair": "PlayfairDisplay.ttf",
    }
    if name.lower() in project_map:
        path = os.path.join(FONTS_DIR, project_map[name.lower()])
        if os.path.exists(path):
            return ImageFont.truetype(path, size)

    win_fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    system_map = {
        "segoe":      "segoeui.ttf",
        "segoe-light":"segoeuil.ttf",
        "segoe-bold": "segoeuib.ttf",
        "segoe-semi": "seguisb.ttf",
        "arial":      "arial.ttf",
        "arial-bold": "arialbd.ttf",
    }
    filename = system_map.get(name.lower(), f"{name}.ttf")
    path = os.path.join(win_fonts, filename)
    if os.path.exists(path):
        return ImageFont.truetype(path, size)

    # Fallback chain
    for fallback in ["segoeuil.ttf", "segoeui.ttf", "arial.ttf"]:
        fb = os.path.join(win_fonts, fallback)
        if os.path.exists(fb):
            return ImageFont.truetype(fb, size)

    return ImageFont.load_default()


# ── Drawing helpers ───────────────────────────────────────────────────────

def _text_size(draw: ImageDraw.Draw, text: str,
               font: ImageFont.FreeTypeFont) -> tuple:
    """Return (width, height) of text using textbbox."""
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _draw_centered(draw: ImageDraw.Draw, text: str, y: int,
                   font: ImageFont.FreeTypeFont, fill: str) -> int:
    """Draw text horizontally centered. Returns y after text."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    # Offset by bbox[1] so the visual top of the ink lands at y
    draw.text(((W - tw) // 2, y - bbox[1]), text, font=font, fill=fill)
    return y + (bbox[3] - bbox[1])


def _wrap_headline(draw: ImageDraw.Draw, text: str,
                   font: ImageFont.FreeTypeFont,
                   max_px: int) -> list:
    """Word-wrap headline to fit within max_px. Returns list of lines."""
    words  = text.split()
    lines  = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if (bbox[2] - bbox[0]) <= max_px:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def _load_logo() -> Image.Image | None:
    """Try to load tulsagays_profile.png from the logo directory.
    Returns a resized (80x80) RGBA image, or None if not found."""
    candidates = [
        os.path.join(LOGO_DIR, "tulsagays_profile.png"),
        os.path.join(LOGO_DIR, "profile.png"),
        os.path.join(LOGO_DIR, "tulsagays_profile_320.png"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                logo = Image.open(path).convert("RGBA")
                # Resize to 72x72 for corner placement
                logo = logo.resize((72, 72), Image.LANCZOS)
                return logo
            except Exception:
                pass
    return None


# ── Banner Generator ──────────────────────────────────────────────────────

def make_og_banner(headline: str, tag: str,
                   logo: Image.Image | None = None) -> Image.Image:
    """
    Render a 1200x630 og:image banner.

    Layout (top to bottom):
      4px  neon-pink top bar
      ~60px  top zone: logo top-right, tag label top-left
      ~380px mid zone: dark-purple mid band, headline centered
      ~120px bottom zone: "tulsagays.com" gold/pink, subtle site line
      4px  neon-pink bottom bar
    """
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # ── Mid-band (subtle warm dark-purple rectangle) ──────────────────────
    band_top    = 90
    band_bottom = H - 110
    draw.rectangle([0, band_top, W, band_bottom], fill=MID_BAND)

    # Thin accent lines bordering the mid-band
    draw.rectangle([0, band_top,     W, band_top + 1],     fill=DARK_GRAY)
    draw.rectangle([0, band_bottom,  W, band_bottom + 1],  fill=DARK_GRAY)

    # ── Top bar (neon pink, 4px) ──────────────────────────────────────────
    draw.rectangle([0, 0, W, 3], fill=NEON_PINK)

    # ── Bottom bar (neon pink, 4px) ───────────────────────────────────────
    draw.rectangle([0, H - 4, W, H - 1], fill=NEON_PINK)

    # ── Logo (top-right corner) ────────────────────────────────────────────
    if logo is not None:
        logo_x = W - logo.width - 28
        logo_y = 12
        img.paste(logo, (logo_x, logo_y), logo)

    # ── Tag label (top-left, small caps style) ────────────────────────────
    f_tag = _font("segoe-semi", 22)
    draw.text((PAD, 18), tag, font=f_tag, fill=NEON_PINK)

    # Thin pink divider under tag
    draw.rectangle([PAD, 50, W - PAD, 52], fill=NEON_PINK)

    # ── Headline (centered in mid-band) ───────────────────────────────────
    # Try Poiret first (matches carousel style), fall back to Segoe
    headline_max_px = W - PAD * 2

    # Pick font size: try 82px down to 52px until it wraps to 3 lines or fewer
    headline_font = None
    headline_lines = []
    for size in [82, 72, 64, 56, 50]:
        f = _font("poiret", size)
        lines = _wrap_headline(draw, headline, f, headline_max_px)
        if len(lines) <= 3:
            headline_font = f
            headline_lines = lines
            break
    if not headline_font:
        headline_font = _font("poiret", 50)
        headline_lines = _wrap_headline(draw, headline, headline_font, headline_max_px)

    # Measure total headline block height
    line_gap    = 12
    _, line_h   = _text_size(draw, "Hy", headline_font)
    total_text_h = len(headline_lines) * line_h + (len(headline_lines) - 1) * line_gap

    # Vertical center in the mid band
    mid_center_y = (band_top + band_bottom) // 2
    y = mid_center_y - total_text_h // 2

    for line in headline_lines:
        y = _draw_centered(draw, line, y, headline_font, WHITE)
        y += line_gap

    # ── Bottom strip: "tulsagays.com" ─────────────────────────────────────
    f_site      = _font("poiret", 38)
    f_site_sub  = _font("segoe", 18)

    site_y = H - 98
    _draw_centered(draw, "tulsagays.com", site_y, f_site, NEON_PINK)
    _draw_centered(draw, "Your source for queer life in Tulsa, Oklahoma",
                   site_y + 46, f_site_sub, LIGHT_GRAY)

    return img


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR}")

    logo = _load_logo()
    if logo:
        print("Logo loaded: using tulsagays_profile.png")
    else:
        print("Logo not found: generating without logo")

    for article in ARTICLES:
        slug     = article["slug"]
        headline = article["headline"]
        tag      = article["tag"]

        out_path = os.path.join(OUTPUT_DIR, f"{slug}.png")
        banner   = make_og_banner(headline, tag, logo)
        banner.save(out_path, "PNG", optimize=True)
        print(f"  Saved: {os.path.relpath(out_path, _ROOT)}")

    print(f"\nGenerated {len(ARTICLES)} og:image banners.")


if __name__ == "__main__":
    main()
