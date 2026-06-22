"""
reflection_detector.py — Overexposure / Sun-Reflection Detection
=================================================================

Detects blown-out highlights that destroy OCR accuracy.

Algorithm:
    overexposed_ratio = count(pixels > 245) / total_pixels

Results:
    ratio ≤ 0.30 → "ok"      (no action)
    ratio > 0.30 → "reduce"  (reduce quality score)
    ratio > 0.50 → "reject"  (discard image)

Returns a namedtuple (status, ratio, penalty_factor):
    status         "ok" | "reduce" | "reject"
    ratio          float 0-1
    penalty_factor float 0-1  (multiply by quality component)
"""

from typing import NamedTuple
import cv2
import numpy as np

REJECT_THRESHOLD = 0.50
REDUCE_THRESHOLD = 0.30


class ReflectionResult(NamedTuple):
    status:         str    # "ok" | "reduce" | "reject"
    ratio:          float  # overexposed pixel ratio 0-1
    penalty_factor: float  # multiply quality by this (1.0 = no penalty)


def detect(img: np.ndarray) -> ReflectionResult:
    """
    Detect overexposure in a BGR or grayscale image.

    Args:
        img: BGR (H,W,3) or grayscale (H,W) numpy array

    Returns:
        ReflectionResult
    """
    if img is None or img.size == 0:
        return ReflectionResult("ok", 0.0, 1.0)

    gray   = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
    total  = gray.size
    bright = int(np.sum(gray > 245))
    ratio  = bright / total

    if ratio > REJECT_THRESHOLD:
        return ReflectionResult("reject", round(ratio, 4), 0.0)
    elif ratio > REDUCE_THRESHOLD:
        # Linear penalty: at ratio=0.30 → factor=1.0, at ratio=0.50 → factor=0.0
        factor = 1.0 - (ratio - REDUCE_THRESHOLD) / (REJECT_THRESHOLD - REDUCE_THRESHOLD)
        return ReflectionResult("reduce", round(ratio, 4), round(max(0.0, factor), 4))
    else:
        return ReflectionResult("ok", round(ratio, 4), 1.0)
