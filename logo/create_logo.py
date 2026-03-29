"""Generate the Tulsa Gays logo - fun/quirky style with Tulsa skyline + pride elements."""
from PIL import Image, ImageDraw, ImageFont
import math
import os

WIDTH, HEIGHT = 1080, 1080
PRIDE_COLORS = [
    (228, 3, 3),      # Red
    (255, 140, 0),     # Orange
    (255, 237, 0),     # Yellow
    (0, 128, 38),      # Green
    (0, 77, 255),      # Blue
    (117, 7, 135),     # Purple
]

def draw_rainbow_background(draw, width, height):
    """Draw diagonal rainbow stripes as background."""
    stripe_width = width // 4
    for i, color in enumerate(PRIDE_COLORS):
        points = []
        offset = i * stripe_width - width
        points = [
            (offset, 0),
            (offset + stripe_width, 0),
            (offset + stripe_width + height, height),
            (offset + height, height),
        ]
        draw.polygon(points, fill=color)
        # Second set to fill the canvas
        offset2 = offset + len(PRIDE_COLORS) * stripe_width
        draw.polygon([
            (offset2, 0),
            (offset2 + stripe_width, 0),
            (offset2 + stripe_width + height, height),
            (offset2 + height, height),
        ], fill=color)

def draw_tulsa_skyline(draw, y_base, width):
    """Draw a simplified Tulsa skyline silhouette."""
    dark = (30, 30, 30)
    # BOK Tower (tallest)
    draw.rectangle([width//2 - 40, y_base - 280, width//2 + 40, y_base], fill=dark)
    draw.polygon([(width//2 - 40, y_base - 280), (width//2, y_base - 310), (width//2 + 40, y_base - 280)], fill=dark)

    # Cityplex Tower
    draw.rectangle([width//2 - 150, y_base - 220, width//2 - 90, y_base], fill=dark)
    draw.rectangle([width//2 - 135, y_base - 240, width//2 - 105, y_base - 220], fill=dark)

    # Mid-Continent Tower
    draw.rectangle([width//2 + 80, y_base - 200, width//2 + 140, y_base], fill=dark)
    draw.polygon([(width//2 + 80, y_base - 200), (width//2 + 110, y_base - 230), (width//2 + 140, y_base - 200)], fill=dark)

    # Smaller buildings left
    draw.rectangle([width//2 - 280, y_base - 140, width//2 - 210, y_base], fill=dark)
    draw.rectangle([width//2 - 340, y_base - 100, width//2 - 290, y_base], fill=dark)
    draw.rectangle([width//2 - 200, y_base - 170, width//2 - 155, y_base], fill=dark)

    # Smaller buildings right
    draw.rectangle([width//2 + 150, y_base - 150, width//2 + 220, y_base], fill=dark)
    draw.rectangle([width//2 + 230, y_base - 110, width//2 + 300, y_base], fill=dark)
    draw.rectangle([width//2 + 170, y_base - 100, width//2 + 210, y_base], fill=dark)

    # Far edge buildings
    draw.rectangle([width//2 - 420, y_base - 70, width//2 - 350, y_base], fill=dark)
    draw.rectangle([width//2 + 310, y_base - 80, width//2 + 400, y_base], fill=dark)

    # Ground bar
    draw.rectangle([0, y_base, width, y_base + 10], fill=dark)

def draw_golden_driller(draw, x, y_base):
    """Draw a simplified, fun Golden Driller figure holding a pride flag."""
    gold = (218, 165, 32)
    dark_gold = (184, 134, 11)

    # Body
    draw.ellipse([x - 15, y_base - 120, x + 15, y_base - 90], fill=gold)  # Head
    draw.rectangle([x - 20, y_base - 90, x + 20, y_base - 30], fill=gold)  # Torso
    # Legs
    draw.rectangle([x - 18, y_base - 30, x - 5, y_base], fill=dark_gold)
    draw.rectangle([x + 5, y_base - 30, x + 18, y_base], fill=dark_gold)
    # Arm holding flag
    draw.line([(x + 15, y_base - 80), (x + 50, y_base - 110)], fill=dark_gold, width=6)

    # Pride flag on a pole
    pole_x = x + 50
    draw.line([(pole_x, y_base - 150), (pole_x, y_base - 70)], fill=(100, 100, 100), width=3)
    flag_h = 10
    for i, color in enumerate(PRIDE_COLORS):
        draw.rectangle([pole_x, y_base - 150 + i * flag_h, pole_x + 45, y_base - 150 + (i + 1) * flag_h], fill=color)

def draw_text_with_outline(draw, position, text, font, fill, outline_color, outline_width=3):
    """Draw text with an outline for readability."""
    x, y = position
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx * dx + dy * dy <= outline_width * outline_width:
                draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
    draw.text(position, text, font=font, fill=fill)

def create_logo():
    img = Image.new('RGB', (WIDTH, HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Rainbow diagonal stripes background
    draw_rainbow_background(draw, WIDTH, HEIGHT)

    # Semi-transparent dark circle in center for text contrast
    overlay = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.ellipse([90, 90, WIDTH - 90, HEIGHT - 90], fill=(0, 0, 0, 140))
    img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
    draw = ImageDraw.Draw(img)

    # Skyline in the center-bottom area
    draw_tulsa_skyline(draw, 680, WIDTH)

    # Golden Driller with pride flag
    draw_golden_driller(draw, 350, 680)

    # Fun sparkles / stars
    star_positions = [(200, 250), (850, 300), (750, 200), (300, 800), (780, 780), (180, 600)]
    for sx, sy in star_positions:
        for angle in range(0, 360, 45):
            ex = sx + int(12 * math.cos(math.radians(angle)))
            ey = sy + int(12 * math.sin(math.radians(angle)))
            draw.line([(sx, sy), (ex, ey)], fill=(255, 255, 255), width=2)

    # Main text - TULSA
    try:
        font_large = ImageFont.truetype("C:/Windows/Fonts/impact.ttf", 140)
        font_small = ImageFont.truetype("C:/Windows/Fonts/impact.ttf", 120)
        font_tag = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 36)
    except (OSError, IOError):
        font_large = ImageFont.load_default()
        font_small = font_large
        font_tag = font_large

    # "TULSA" text
    tulsa_text = "TULSA"
    bbox = draw.textbbox((0, 0), tulsa_text, font=font_large)
    tw = bbox[2] - bbox[0]
    tx = (WIDTH - tw) // 2
    draw_text_with_outline(draw, (tx, 300), tulsa_text, font_large, (255, 255, 255), (0, 0, 0), 4)

    # "GAYS" text with rainbow coloring
    gays_text = "GAYS"
    bbox = draw.textbbox((0, 0), gays_text, font=font_small)
    tw = bbox[2] - bbox[0]
    gx = (WIDTH - tw) // 2
    draw_text_with_outline(draw, (gx, 430), gays_text, font_small, (255, 237, 0), (0, 0, 0), 4)

    # Tagline
    tagline = "YOUR WEEKLY LGBTQ+ EVENT GUIDE"
    bbox = draw.textbbox((0, 0), tagline, font=font_tag)
    tw = bbox[2] - bbox[0]
    ttx = (WIDTH - tw) // 2
    draw_text_with_outline(draw, (ttx, 750), tagline, font_tag, (255, 255, 255), (0, 0, 0), 2)

    # Hearts scattered
    heart_positions = [(160, 380), (900, 450), (130, 500), (920, 600)]
    for hx, hy in heart_positions:
        size = 15
        draw.ellipse([hx - size, hy - size, hx, hy], fill=(255, 105, 180))
        draw.ellipse([hx, hy - size, hx + size, hy], fill=(255, 105, 180))
        draw.polygon([(hx - size, hy - 3), (hx + size, hy - 3), (hx, hy + size)], fill=(255, 105, 180))

    # Save
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(output_dir, "tulsagays_logo.png")
    img.save(output_path, "PNG", quality=95)
    print(f"Logo saved to: {output_path}")

    # Also save a smaller version for profile pic (320x320)
    small = img.resize((320, 320), Image.LANCZOS)
    small_path = os.path.join(output_dir, "tulsagays_profile.png")
    small.save(small_path, "PNG", quality=95)
    print(f"Profile pic saved to: {small_path}")

    return output_path

if __name__ == "__main__":
    create_logo()
