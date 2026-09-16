"""
Signet classifier — pixel-based icon recognition.
==================================================
Classifies embedded menu icons (Vegan/Vegetarisch/Schwein/Rind/Geflügel/Fisch/
Nachhaltig) from their pixel data via aspect ratio and color distribution.

All thresholds were calibrated empirically against the DB casino menu PDFs
(icons are ~17x61 px primary signets and ~12.8 px secondary badges). They are
grouped as named constants below so a layout change only needs recalibration
in one place — if classification silently degrades to UNKNOWN(...), start here.
"""
from io import BytesIO

import numpy as np
from PIL import Image

# --- Cropping -----------------------------------------------------------------
# A pixel counts as "content" (non-white) if any channel is below this value.
WHITE_THRESHOLD = 240
# Minimum content bounding box (px) to treat an image as a real icon, not noise.
MIN_CONTENT_SIZE = 3

# --- Oversized images ---------------------------------------------------------
# Images larger than this in either dimension are page logos, not signets.
LOGO_MAX_SIZE = 500

# --- Color detection (per-pixel channel rules, results as % of content area) --
RED_MIN = 120            # red channel value for a "red" pixel
RED_DOMINANCE = 60       # red must exceed green/blue by this much
GREEN_MIN = 60           # green channel value for a "green" pixel
GREEN_DOMINANCE = 20     # green must exceed red/blue by this much
BLACK_MAX = 80           # all channels below this = "black" (outline detail)

# --- Classification thresholds (aspect = width / height) ----------------------
NACHHALTIG_GREEN_PCT = 30        # large green+black badge
NACHHALTIG_MIN_WIDTH = 200
NACHHALTIG_SMALL_GREEN_PCT = 20  # fallback for the small 12.8 px badge

VEGAN_MIN_ASPECT = 1.55          # tall, narrow, tiny green, no red (two leaves)
VEGAN_MAX_GREEN_PCT = 4
VEGAN_MAX_RED_PCT = 0.5

VEGETARISCH_MIN_ASPECT = 1.35    # broad sweeping leaf, more green
VEGETARISCH_MAX_ASPECT = 1.6
VEGETARISCH_MIN_GREEN_PCT = 4
VEGETARISCH_MAX_RED_PCT = 0.5

SCHWEIN_RIND_MIN_ASPECT = 1.0    # wide, lots of red (two animals)
SCHWEIN_RIND_MIN_RED_PCT = 8

RIND_MIN_ASPECT = 1.1            # medium aspect, moderate red, tall
RIND_MAX_ASPECT = 1.3
RIND_MIN_RED_PCT = 0.8
RIND_MIN_HEIGHT = 55

SCHWEIN_MIN_ASPECT = 1.2         # wider than tall, some red
SCHWEIN_MIN_RED_PCT = 1.5

FISCH_MIN_ASPECT = 0.8           # roughly square, detailed outline (high black)
FISCH_MAX_ASPECT = 1.05
FISCH_MIN_BLACK_PCT = 14
FISCH_MIN_RED_PCT = 1.8

GEFLÜGEL_MIN_ASPECT = 0.7        # taller than wide, moderate outline, low red
GEFLÜGEL_MAX_ASPECT = 0.95
GEFLÜGEL_MIN_BLACK_PCT = 8
GEFLÜGEL_MAX_RED_PCT = 2


def crop_to_content(pixels, threshold=WHITE_THRESHOLD):
    """Crop a HxWx3 pixel array to its non-white bounding box.

    Returns (cropped_pixels, content_width, content_height).
    """
    non_white = np.any(pixels < threshold, axis=2)
    if not non_white.any():
        return pixels, 0, 0
    rows = np.where(non_white.any(axis=1))[0]
    cols = np.where(non_white.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        return pixels, 0, 0
    cropped = pixels[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    return cropped, cols[-1] - cols[0] + 1, rows[-1] - rows[0] + 1


def classify_signet(image_bytes):
    """Classify a signet image based on aspect ratio and color distribution."""
    try:
        image = Image.open(BytesIO(image_bytes)).convert('RGB')
    except Exception:
        return 'UNKNOWN'

    pixels = np.array(image)
    full_width, full_height = pixels.shape[1], pixels.shape[0]

    if full_width > LOGO_MAX_SIZE or full_height > LOGO_MAX_SIZE:
        return 'LOGO'

    cropped, content_width, content_height = crop_to_content(pixels)
    if content_width < MIN_CONTENT_SIZE or content_height < MIN_CONTENT_SIZE:
        return 'SPACER'

    pixel_count = content_height * content_width
    red = cropped[:, :, 0].astype(float)
    green = cropped[:, :, 1].astype(float)
    blue = cropped[:, :, 2].astype(float)

    red_pct = ((red > RED_MIN) & (red - green > RED_DOMINANCE)
               & (red - blue > RED_DOMINANCE)).sum() / pixel_count * 100
    green_pct = ((green > GREEN_MIN) & (green - red > GREEN_DOMINANCE)
                 & (green - blue > GREEN_DOMINANCE)).sum() / pixel_count * 100
    black_pct = ((red < BLACK_MAX) & (green < BLACK_MAX)
                 & (blue < BLACK_MAX)).sum() / pixel_count * 100
    aspect = content_width / content_height

    # Classification rules (ordered by specificity):
    # Large green+black = Nachhaltig badge
    if green_pct > NACHHALTIG_GREEN_PCT and full_width > NACHHALTIG_MIN_WIDTH:
        return 'NACHHALTIG'

    # VEGAN: tall narrow, tiny green, no red (two small leaves)
    if aspect > VEGAN_MIN_ASPECT and green_pct < VEGAN_MAX_GREEN_PCT and red_pct < VEGAN_MAX_RED_PCT:
        return 'VEGAN'

    # VEGETARISCH: slightly less narrow, more green (broad sweeping leaf)
    if (VEGETARISCH_MIN_ASPECT <= aspect <= VEGETARISCH_MAX_ASPECT
            and green_pct > VEGETARISCH_MIN_GREEN_PCT and red_pct < VEGETARISCH_MAX_RED_PCT):
        return 'VEGETARISCH'

    # SCHWEIN+RIND: wide, lots of red (two animals)
    if aspect > SCHWEIN_RIND_MIN_ASPECT and red_pct > SCHWEIN_RIND_MIN_RED_PCT:
        return 'SCHWEIN+RIND'

    # RIND: medium aspect, moderate red, taller than schwein
    if (RIND_MIN_ASPECT <= aspect <= RIND_MAX_ASPECT
            and red_pct > RIND_MIN_RED_PCT and content_height > RIND_MIN_HEIGHT):
        return 'RIND'

    # SCHWEIN: wider than tall, some red
    if aspect > SCHWEIN_MIN_ASPECT and red_pct > SCHWEIN_MIN_RED_PCT:
        return 'SCHWEIN'

    # FISCH: roughly square, high black (detailed outline), red > 2%
    # Must come BEFORE Geflügel (overlapping aspect range)
    if (FISCH_MIN_ASPECT <= aspect <= FISCH_MAX_ASPECT
            and black_pct > FISCH_MIN_BLACK_PCT and red_pct > FISCH_MIN_RED_PCT):
        return 'FISCH'

    # GEFLÜGEL: taller than wide, moderate black outline, low red (<2%)
    if (GEFLÜGEL_MIN_ASPECT <= aspect <= GEFLÜGEL_MAX_ASPECT
            and black_pct > GEFLÜGEL_MIN_BLACK_PCT and red_pct < GEFLÜGEL_MAX_RED_PCT):
        return 'GEFLÜGEL'

    # Fallback: small Nachhaltig badge (12.8x12.8)
    if green_pct > NACHHALTIG_SMALL_GREEN_PCT:
        return 'NACHHALTIG'

    return f'UNKNOWN(a={aspect:.2f},r={red_pct:.1f},g={green_pct:.1f},b={black_pct:.1f})'
