"""
plate_validator.py — Plate Region Size Validation
==================================================

Rejects plate crops that are too small to yield usable OCR.

Minimum requirements (Part 3):
    plate_width  >= 80 px
    plate_height >= 25 px

Returns a namedtuple (valid, reason, pixel_score):
    valid        bool
    reason       "OK" | "PLATE_TOO_SMALL" | "EMPTY_CROP"
    pixel_score  float 0-1  (how well the plate satisfies the size requirement)
"""

from typing import NamedTuple
import numpy as np

MIN_WIDTH  = 80
MIN_HEIGHT = 25
# "ideal" plate size for full score (pixels)
IDEAL_WIDTH  = 220
IDEAL_HEIGHT = 60


class PlateValidationResult(NamedTuple):
    valid:       bool
    reason:      str
    pixel_score: float   # 0-1, used in quality_engine plate_size component


def validate(plate_crop: np.ndarray) -> PlateValidationResult:
    """
    Validate a plate crop by pixel dimensions.

    Args:
        plate_crop: BGR or grayscale numpy array (plate region only)

    Returns:
        PlateValidationResult
    """
    if plate_crop is None or plate_crop.size == 0:
        return PlateValidationResult(False, "EMPTY_CROP", 0.0)

    h, w = plate_crop.shape[:2]

    if w < MIN_WIDTH or h < MIN_HEIGHT:
        return PlateValidationResult(
            False, "PLATE_TOO_SMALL",
            round(min(w / MIN_WIDTH, h / MIN_HEIGHT), 4)
        )

    # Score: how close to ideal plate size (saturates at ideal)
    w_score = min(w / IDEAL_WIDTH,  1.0)
    h_score = min(h / IDEAL_HEIGHT, 1.0)
    pixel_score = (w_score * 0.7 + h_score * 0.3)

    return PlateValidationResult(True, "OK", round(pixel_score, 4))
