"""Generate a cover photo with recognizable Tulsa skyline in pride rainbow colors."""
from PIL import Image, ImageDraw, ImageFont
import os
import random

WIDTH, HEIGHT = 820, 312
PRIDE_COLORS = [
    (228, 3, 3),      # Red
    (255, 140, 0),     # Orange
    (255, 237, 0),     # Yellow
    (0, 128, 38),      # Green
    (0, 77, 255),      # Blue
    (117, 7, 135),     # Purple
]

def draw_text_outline(draw, pos, text, font, fill, outline, w=2):
    x, y = pos
    for dx in range(-w, w + 1):
        for dy in range(-w, w + 1):
            if dx*dx + dy*dy <= w*w:
                draw.text((x+dx, y+dy), text, font=font, fill=outline)
    draw.text(pos, text, font=font, fill=fill)

def draw_windows(draw, x, y_top, w, ground_y, color):
    """Draw lit windows on a building."""
    random.seed(hash((x, w)))
    bright = tuple(min(255, v + 100) for v in color)
    for wy in range(y_top + 6, ground_y - 4, 10):
        for wx in range(x + 3, x + w - 3, 6):
            if random.random() > 0.25:
                draw.rectangle([wx, wy, wx+2, wy+4], fill=bright)

def create_cover():
    img = Image.new('RGB', (WIDTH, HEIGHT), (18, 18, 30))
    draw = ImageDraw.Draw(img)
    random.seed(42)

    # Gradient sky
    for y in range(HEIGHT):
        r = int(8 + (20 - 8) * y / HEIGHT)
        g = int(8 + (12 - 8) * y / HEIGHT)
        b = int(30 + (45 - 30) * y / HEIGHT)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))

    # Stars
    for _ in range(80):
        sx, sy = random.randint(0, WIDTH), random.randint(0, int(HEIGHT * 0.45))
        s = random.choice([1, 1, 2])
        b = random.randint(140, 255)
        draw.ellipse([sx, sy, sx+s, sy+s], fill=(b, b, b))

    ground_y = HEIGHT - 30

    # ═══════════════════════════════════════════════════════════════
    # ACTUAL TULSA SKYLINE BUILDINGS (left to right, west to east)
    # Each tuple: (color_index, draw_function)
    # ═══════════════════════════════════════════════════════════════

    def darken(color, factor=0.85):
        return tuple(int(v * factor) for v in color)

    # --- Far left: smaller buildings ---
    c = PRIDE_COLORS[0]  # Red
    # Small office building
    draw.rectangle([30, ground_y - 55, 60, ground_y], fill=darken(c))
    draw_windows(draw, 30, ground_y - 55, 30, ground_y, c)

    # --- CityPlex Towers (3 connected towers) ---
    c = PRIDE_COLORS[1]  # Orange
    # Left tower
    draw.rectangle([80, ground_y - 130, 108, ground_y], fill=c)
    draw.rectangle([85, ground_y - 140, 103, ground_y - 130], fill=darken(c))
    # Center tower (tallest of the 3)
    draw.rectangle([112, ground_y - 150, 140, ground_y], fill=darken(c, 0.9))
    draw.rectangle([118, ground_y - 160, 134, ground_y - 150], fill=darken(c, 0.8))
    # Right tower
    draw.rectangle([144, ground_y - 125, 172, ground_y], fill=c)
    draw.rectangle([149, ground_y - 135, 167, ground_y - 125], fill=darken(c))
    draw_windows(draw, 80, ground_y - 130, 28, ground_y, c)
    draw_windows(draw, 112, ground_y - 150, 28, ground_y, c)
    draw_windows(draw, 144, ground_y - 125, 28, ground_y, c)

    # --- Mid-Continent Tower (Art Deco with stepped top) ---
    c = PRIDE_COLORS[2]  # Yellow
    base_x = 195
    draw.rectangle([base_x, ground_y - 140, base_x + 40, ground_y], fill=c)
    # Art deco stepped crown
    draw.rectangle([base_x + 5, ground_y - 155, base_x + 35, ground_y - 140], fill=darken(c))
    draw.rectangle([base_x + 10, ground_y - 165, base_x + 30, ground_y - 155], fill=darken(c, 0.8))
    draw.rectangle([base_x + 14, ground_y - 175, base_x + 26, ground_y - 165], fill=darken(c, 0.7))
    # Spire
    draw.polygon([(base_x + 17, ground_y - 175), (base_x + 20, ground_y - 195), (base_x + 23, ground_y - 175)], fill=darken(c, 0.6))
    draw_windows(draw, base_x, ground_y - 140, 40, ground_y, c)

    # --- Philtower (ornate Art Deco) ---
    c = PRIDE_COLORS[3]  # Green
    base_x = 260
    draw.rectangle([base_x, ground_y - 120, base_x + 35, ground_y], fill=c)
    # Stepped top
    draw.rectangle([base_x + 3, ground_y - 130, base_x + 32, ground_y - 120], fill=darken(c))
    draw.rectangle([base_x + 8, ground_y - 140, base_x + 27, ground_y - 130], fill=darken(c, 0.8))
    # Small ornamental peak
    draw.polygon([(base_x + 12, ground_y - 140), (base_x + 17, ground_y - 152), (base_x + 22, ground_y - 140)], fill=darken(c, 0.7))
    draw_windows(draw, base_x, ground_y - 120, 35, ground_y, c)

    # --- BOK Tower (tallest, distinctive slanted top) ---
    c = PRIDE_COLORS[4]  # Blue
    base_x = 330
    # Main tower body
    draw.rectangle([base_x, ground_y - 200, base_x + 50, ground_y], fill=c)
    # BOK's distinctive angled/sloped crown
    draw.polygon([
        (base_x, ground_y - 200),
        (base_x + 15, ground_y - 230),
        (base_x + 35, ground_y - 230),
        (base_x + 50, ground_y - 200),
    ], fill=darken(c, 0.8))
    # Antenna/spire
    draw.line([(base_x + 25, ground_y - 230), (base_x + 25, ground_y - 250)], fill=darken(c, 0.6), width=2)
    draw_windows(draw, base_x, ground_y - 200, 50, ground_y, c)

    # --- 110 W 7th (Williams Tower area) ---
    c = PRIDE_COLORS[5]  # Purple
    base_x = 405
    draw.rectangle([base_x, ground_y - 135, base_x + 38, ground_y], fill=c)
    draw.rectangle([base_x + 5, ground_y - 145, base_x + 33, ground_y - 135], fill=darken(c))
    draw_windows(draw, base_x, ground_y - 135, 38, ground_y, c)

    # --- First Place Tower ---
    c = PRIDE_COLORS[0]  # Red again
    base_x = 465
    draw.rectangle([base_x, ground_y - 155, base_x + 42, ground_y], fill=c)
    # Flat top with small mechanical penthouse
    draw.rectangle([base_x + 8, ground_y - 165, base_x + 34, ground_y - 155], fill=darken(c))
    draw_windows(draw, base_x, ground_y - 155, 42, ground_y, c)

    # --- Bank of America (320 S Boston) ---
    c = PRIDE_COLORS[1]  # Orange
    base_x = 530
    draw.rectangle([base_x, ground_y - 110, base_x + 35, ground_y], fill=c)
    draw.rectangle([base_x + 5, ground_y - 118, base_x + 30, ground_y - 110], fill=darken(c))
    draw_windows(draw, base_x, ground_y - 110, 35, ground_y, c)

    # --- Oklahoma Natural Gas building ---
    c = PRIDE_COLORS[2]  # Yellow
    base_x = 585
    draw.rectangle([base_x, ground_y - 90, base_x + 32, ground_y], fill=c)
    draw_windows(draw, base_x, ground_y - 90, 32, ground_y, c)

    # --- Civic Center area ---
    c = PRIDE_COLORS[3]  # Green
    base_x = 635
    draw.rectangle([base_x, ground_y - 70, base_x + 40, ground_y], fill=c)
    draw_windows(draw, base_x, ground_y - 70, 40, ground_y, c)

    # --- University Club Tower ---
    c = PRIDE_COLORS[4]  # Blue
    base_x = 695
    draw.rectangle([base_x, ground_y - 100, base_x + 30, ground_y], fill=c)
    draw.rectangle([base_x + 5, ground_y - 108, base_x + 25, ground_y - 100], fill=darken(c))
    draw_windows(draw, base_x, ground_y - 100, 30, ground_y, c)

    # --- Far right smaller ---
    c = PRIDE_COLORS[5]  # Purple
    draw.rectangle([745, ground_y - 60, 775, ground_y], fill=c)
    draw_windows(draw, 745, ground_y - 60, 30, ground_y, c)

    c = PRIDE_COLORS[0]  # Red
    draw.rectangle([785, ground_y - 45, 810, ground_y], fill=c)
    draw_windows(draw, 785, ground_y - 45, 25, ground_y, c)

    # Ground line
    draw.rectangle([0, ground_y, WIDTH, ground_y + 2], fill=(40, 40, 60))

    # Subtle reflections
    for x in range(0, WIDTH, 3):
        y_ref = ground_y + 3 + random.randint(0, 15)
        pixel = img.getpixel((x, ground_y - 5))
        ref = tuple(int(v * 0.12) for v in pixel)
        draw.line([(x, ground_y + 3), (x, y_ref)], fill=ref)

    # Text
    try:
        font_big = ImageFont.truetype("C:/Windows/Fonts/impact.ttf", 50)
        font_sm = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 16)
    except (OSError, IOError):
        font_big = ImageFont.load_default()
        font_sm = font_big

    text = "TULSA GAYS"
    bbox = draw.textbbox((0, 0), text, font=font_big)
    tw = bbox[2] - bbox[0]
    tx = (WIDTH - tw) // 2
    draw_text_outline(draw, (tx, 8), text, font_big, (255, 255, 255), (0, 0, 0), 3)

    tag = "YOUR WEEKLY LGBTQ+ EVENT GUIDE  |  TULSA, OK"
    bbox = draw.textbbox((0, 0), tag, font=font_sm)
    tw = bbox[2] - bbox[0]
    tx = (WIDTH - tw) // 2
    draw_text_outline(draw, (tx, HEIGHT - 20), tag, font_sm, (180, 180, 200), (0, 0, 0), 1)

    # Save
    output_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(output_dir, "tulsagays_cover.png")
    img.save(path, "PNG", quality=95)
    print(f"Cover photo saved to: {path}")
    return path

if __name__ == "__main__":
    create_cover()
