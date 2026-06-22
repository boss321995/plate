"""
quality_engine.py — Smart Quality Score Engine (6-Component)
=============================================================

Replaces the old 4-component static score.

Formula (Part 5):
    quality = (
        size_score        * 0.25 +
        blur_score        * 0.20 +
        brightness_score  * 0.15 +
        center_score      * 0.10 +
        reflection_score  * 0.15 +
        plate_size_score  * 0.15
    ) * 100

Component Details:
    size_score       vehicle width / frame width, saturates at 50%
    blur_score       Laplacian variance, saturates at 500
    brightness_score closeness to target 80-180, peak 1.0 at midpoint
    center_score     1 - horizontal distance from frame center
    reflection_score 1 - overexposed_ratio penalty (from reflection_detector)
    plate_size_score pixel score from plate_validator (0 if no plate crop given)

Minimum to accept: quality >= MIN_QUALITY (default 75)
"""

from __future__ import annotations
from typing import NamedTuple, Optional

import cv2
import numpy as np

import reflection_detector
import plate_validator

MIN_QUALITY      = 75.0
MIN_LAP_VAR      = 100.0     # Blur gate: Laplacian variance
MIN_VEHICLE_RATIO = 0.20     # Minimum vehicle width / frame width


class QualityResult(NamedTuple):
    score:        float   # 0-100
    components:   dict
    acceptable:   bool


def compute(
    frame:       np.ndarray,
    x1: int, y1: int, x2: int, y2: int,
    plate_crop:  Optional[np.ndarray] = None,
) -> QualityResult:
    """
    Compute 6-component quality score for a vehicle detection.

    Args:
        frame:      Full BGR frame
        x1,y1,x2,y2: Vehicle bounding box in frame
        plate_crop: Optional plate region crop (enables plate_size + reflection checks)

    Returns:
        QualityResult(score, components, acceptable)
    """
    frame_h, frame_w = frame.shape[:2]
    vehicle_crop = frame[y1:y2, x1:x2]
    if vehicle_crop.size == 0:
        return QualityResult(0.0, {}, False)

    vehicle_w = x2 - x1
    gray      = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2GRAY)

    # ── 1. Size Score ────────────────────────────────────────────────────────
    size_score = min((vehicle_w / frame_w) / 0.5, 1.0)

    # ── 2. Blur Score (Laplacian variance) ──────────────────────────────────
    lap_var    = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    blur_score = min(lap_var / 500.0, 1.0)

    # ── 3. Brightness Score (target 80-180) ──────────────────────────────────
    mean_br = float(np.mean(gray))
    if 80 <= mean_br <= 180:
        brightness_score = 1.0
    elif mean_br < 80:
        brightness_score = max(0.0, mean_br / 80.0)
    else:
        brightness_score = max(0.0, 1.0 - (mean_br - 180.0) / 75.0)

    # ── 4. Center Score ──────────────────────────────────────────────────────
    veh_cx       = (x1 + x2) / 2.0
    center_dist  = abs(veh_cx - frame_w / 2.0) / (frame_w / 2.0)
    center_score = max(0.0, 1.0 - center_dist)

    # ── 5. Reflection Score ──────────────────────────────────────────────────
    ref_crop = plate_crop if plate_crop is not None else vehicle_crop
    ref_result  = reflection_detector.detect(ref_crop)
    reflection_score = ref_result.penalty_factor  # 0-1 (0 = fully rejected)

    # ── 6. Plate Size Score ──────────────────────────────────────────────────
    if plate_crop is not None and plate_crop.size > 0:
        pv = plate_validator.validate(plate_crop)
        plate_size_score = pv.pixel_score
    else:
        plate_size_score = 0.5   # Unknown — neutral weight when no plate yet

    # ── Composite ────────────────────────────────────────────────────────────
    raw = (
        size_score       * 0.25 +
        blur_score       * 0.20 +
        brightness_score * 0.15 +
        center_score     * 0.10 +
        reflection_score * 0.15 +
        plate_size_score * 0.15
    )
    quality = round(raw * 100.0, 1)

    acceptable = (
        quality    >= MIN_QUALITY
        and lap_var >= MIN_LAP_VAR
        and (vehicle_w / frame_w) >= MIN_VEHICLE_RATIO
        and ref_result.status != "reject"
    )

    components = {
        "size_score":        round(size_score        * 100, 1),
        "blur_score":        round(blur_score        * 100, 1),
        "brightness_score":  round(brightness_score  * 100, 1),
        "center_score":      round(center_score      * 100, 1),
        "reflection_score":  round(reflection_score  * 100, 1),
        "plate_size_score":  round(plate_size_score  * 100, 1),
        "lap_var":           round(lap_var,           1),
        "mean_brightness":   round(mean_br,           1),
        "reflection_ratio":  ref_result.ratio,
        "reflection_status": ref_result.status,
    }

    return QualityResult(quality, components, acceptable)
