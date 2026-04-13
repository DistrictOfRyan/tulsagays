"""Slide posting safeguards.

Must be called before ANY social media post goes out.
Validates that the 10-slide set is complete, properly sized, and not blank.

Usage:
    from posting.validator import validate_before_post
    validate_before_post("/path/to/slides/dir")   # raises ValueError on failure
"""

import os
import logging
from typing import Tuple, List

logger = logging.getLogger(__name__)

REQUIRED_SLIDE_COUNT = 10
REQUIRED_WIDTH = 1080
REQUIRED_HEIGHT = 1080
MIN_FILE_SIZE_BYTES = 50 * 1024  # 50 KB
MAX_BLACK_RATIO = 0.40           # 40% black pixels in center region = likely blank


def validate_slides(slide_dir: str) -> Tuple[bool, List[str]]:
    """Check that all 10 slides exist, are the right size, and are not blank.

    Args:
        slide_dir: Path to the directory containing slide_01.png ... slide_10.png

    Returns:
        (passed, errors) where passed is True only if all checks clear.
        errors is a list of human-readable problem descriptions.
    """
    errors: List[str] = []

    # ── Check 1: All 10 slide files exist ─────────────────────────────────────
    missing = []
    for i in range(1, REQUIRED_SLIDE_COUNT + 1):
        filename = f"slide_{i:02d}.png"
        path = os.path.join(slide_dir, filename)
        if not os.path.exists(path):
            missing.append(filename)

    if missing:
        errors.append(f"Missing slides: {', '.join(missing)}")

    # ── Check 2: File size (not empty/corrupt) ─────────────────────────────────
    for i in range(1, REQUIRED_SLIDE_COUNT + 1):
        filename = f"slide_{i:02d}.png"
        path = os.path.join(slide_dir, filename)
        if not os.path.exists(path):
            continue  # Already flagged above
        size = os.path.getsize(path)
        if size < MIN_FILE_SIZE_BYTES:
            errors.append(
                f"{filename} is only {size / 1024:.1f} KB — likely empty or corrupt "
                f"(minimum {MIN_FILE_SIZE_BYTES // 1024} KB required)"
            )

    # ── Check 3 & 4: Dimensions and blank-slide detection ─────────────────────
    try:
        from PIL import Image
        import numpy as np

        for i in range(1, REQUIRED_SLIDE_COUNT + 1):
            filename = f"slide_{i:02d}.png"
            path = os.path.join(slide_dir, filename)
            if not os.path.exists(path):
                continue  # Already flagged above

            try:
                img = Image.open(path)
                w, h = img.size

                # Check 3: Exact 1080x1080 dimensions
                if w != REQUIRED_WIDTH or h != REQUIRED_HEIGHT:
                    errors.append(
                        f"{filename} is {w}x{h} — must be exactly "
                        f"{REQUIRED_WIDTH}x{REQUIRED_HEIGHT}"
                    )

                # Check 4: Black pixel ratio in center region
                # Use center 50% of the image to avoid borders affecting the score
                cx0 = w // 4
                cy0 = h // 4
                cx1 = w * 3 // 4
                cy1 = h * 3 // 4
                center_crop = img.convert("RGB").crop((cx0, cy0, cx1, cy1))
                arr = np.array(center_crop)

                # A pixel is "black" if all channels are <= 20
                black_pixels = np.all(arr <= 20, axis=2).sum()
                total_pixels = arr.shape[0] * arr.shape[1]
                black_ratio = black_pixels / total_pixels if total_pixels > 0 else 0

                if black_ratio > MAX_BLACK_RATIO:
                    errors.append(
                        f"{filename} center region is {black_ratio:.0%} black "
                        f"(threshold {MAX_BLACK_RATIO:.0%}) — slide may be blank or nearly empty"
                    )

            except Exception as e:
                errors.append(f"{filename} could not be opened/inspected: {e}")

    except ImportError:
        errors.append(
            "PIL (Pillow) and/or numpy are not installed — cannot check image dimensions or blank slides. "
            "Run: pip install Pillow numpy"
        )

    passed = len(errors) == 0
    if passed:
        logger.info("[validator] All %d slides passed validation in %s", REQUIRED_SLIDE_COUNT, slide_dir)
    else:
        for err in errors:
            logger.error("[validator] FAIL: %s", err)

    return passed, errors


def validate_before_post(slide_dir: str) -> bool:
    """Gate function — call this before any FB/IG API call.

    Args:
        slide_dir: Path to the directory containing the slide images.

    Returns:
        True if all checks pass.

    Raises:
        ValueError: With a detailed message if any check fails.
                    The post should NOT proceed if this is raised.
    """
    passed, errors = validate_slides(slide_dir)
    if not passed:
        summary = "\n".join(f"  - {e}" for e in errors)
        raise ValueError(
            f"Slide validation FAILED for '{slide_dir}' — do not post.\n"
            f"{len(errors)} issue(s) found:\n{summary}"
        )
    return True


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage: python validator.py <slide_dir>")
        sys.exit(1)

    target = sys.argv[1]
    try:
        validate_before_post(target)
        print(f"PASSED: All slides in '{target}' look good.")
    except ValueError as e:
        print(f"\n{e}")
        sys.exit(1)
