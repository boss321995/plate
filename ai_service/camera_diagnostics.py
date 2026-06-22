"""
camera_diagnostics.py — Camera Self-Diagnostics (Part 2)
=========================================================

Analyzes frames to detect common camera/environmental problems.

Detects:
    dirty_lens      — low edge density in corners vs center
    out_of_focus    — Laplacian variance below threshold
    camera_shift    — >40% of pixels changed between consecutive frames
    rain_detected   — dominant horizontal Sobel energy (streaking)
    over_exposure   — mean brightness > 225
    under_exposure  — mean brightness < 30
    vibration       — high variance in inter-frame differences
    blockage        — near-zero frame variance (lens covered)

Status:
    OK / WARNING / CRITICAL

Usage:
    diag = CameraDiagnostics()
    result = diag.update(frame)
    print(result.status, result.recommendation)
"""

from __future__ import annotations
import cv2
import numpy as np
import time
import threading
from typing import Optional, NamedTuple
from collections import deque


class DiagnosticResult(NamedTuple):
    status:        str    # "OK" | "WARNING" | "CRITICAL"
    focus_score:   float  # 0-100 (Laplacian-based)
    brightness:    float  # 0-255
    lens_dirty:    bool
    rain_detected: bool
    camera_shift:  bool
    vibration:     bool
    blockage:      bool
    over_exposure: bool
    under_exposure:bool
    recommendation:str


# ─────────────────────────────────────────────────────────────────────────────
# CameraDiagnostics
# ─────────────────────────────────────────────────────────────────────────────
class CameraDiagnostics:
    """
    Stateful per-camera diagnostics engine.

    Call update(frame) periodically (every 1-5 seconds is sufficient).
    get_result() returns the latest DiagnosticResult without recomputing.
    """

    # Thresholds
    FOCUS_LAP_CRITICAL     = 20.0    # Laplacian var → focus 0-100 scale
    FOCUS_LAP_WARNING      = 60.0
    SHIFT_DIFF_THRESHOLD   = 0.40    # >40% pixels changed → camera moved
    BLOCKAGE_VAR_THRESHOLD = 8.0     # Very low variance = lens covered
    DIRTY_CORNER_RATIO     = 0.18    # Corner edge density / center edge density
    RAIN_HORIZONTAL_RATIO  = 0.22    # Horizontal Sobel fraction
    VIBRATION_HISTORY      = 12      # Inter-frame diffs to keep
    VIBRATION_VAR_LIMIT    = 120.0
    BRIGHTNESS_LOW         = 30.0
    BRIGHTNESS_HIGH        = 225.0

    def __init__(self):
        self._lock:   threading.Lock   = threading.Lock()
        self._prev:   Optional[np.ndarray] = None
        self._diffs:  deque[float]     = deque(maxlen=self.VIBRATION_HISTORY)
        self._result: Optional[DiagnosticResult] = None
        self._ts:     float            = 0.0

    # ── Public ────────────────────────────────────────────────────────────────

    def update(self, frame: np.ndarray) -> DiagnosticResult:
        """Analyze frame and return DiagnosticResult."""
        gray = (
            cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if len(frame.shape) == 3 else frame.copy()
        )

        brightness    = float(np.mean(gray))
        focus_score   = self._focus(gray)
        blockage      = self._blockage(gray)
        lens_dirty    = self._dirty_lens(gray) and not blockage
        rain          = self._rain(gray)
        camera_shift  = self._shift(gray)
        vibration     = self._vibration(gray)
        over_exp      = brightness > self.BRIGHTNESS_HIGH
        under_exp     = brightness < self.BRIGHTNESS_LOW

        # Severity
        if blockage or camera_shift or under_exp or focus_score < self.FOCUS_LAP_CRITICAL:
            status = "CRITICAL"
        elif (
            over_exp or focus_score < self.FOCUS_LAP_WARNING
            or lens_dirty or rain or vibration
        ):
            status = "WARNING"
        else:
            status = "OK"

        rec = _recommend(
            focus_score, lens_dirty, rain, camera_shift,
            over_exp, under_exp, vibration, blockage,
        )

        result = DiagnosticResult(
            status=status,
            focus_score=round(focus_score, 1),
            brightness=round(brightness, 1),
            lens_dirty=lens_dirty,
            rain_detected=rain,
            camera_shift=camera_shift,
            vibration=vibration,
            blockage=blockage,
            over_exposure=over_exp,
            under_exposure=under_exp,
            recommendation=rec,
        )

        with self._lock:
            self._prev   = gray
            self._result = result
            self._ts     = time.time()

        return result

    def get_result(self) -> Optional[DiagnosticResult]:
        with self._lock:
            return self._result

    def as_dict(self) -> dict:
        r = self.get_result()
        if r is None:
            return {"status": "unknown", "recommendation": "No data yet"}
        return {
            "status":          r.status,
            "focus_score":     r.focus_score,
            "brightness":      r.brightness,
            "lens_dirty":      r.lens_dirty,
            "rain_detected":   r.rain_detected,
            "camera_shift":    r.camera_shift,
            "vibration":       r.vibration,
            "blockage":        r.blockage,
            "over_exposure":   r.over_exposure,
            "under_exposure":  r.under_exposure,
            "recommendation":  r.recommendation,
            "updated_at":      self._ts,
        }

    # ── Individual checks ─────────────────────────────────────────────────────

    def _focus(self, gray: np.ndarray) -> float:
        """Laplacian variance → 0-100 focus score."""
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        return min(lap_var / 5.0, 100.0)

    def _blockage(self, gray: np.ndarray) -> bool:
        """Blocked lens has near-zero pixel variance."""
        return float(np.var(gray)) < self.BLOCKAGE_VAR_THRESHOLD

    def _dirty_lens(self, gray: np.ndarray) -> bool:
        """
        Dirty lens: corners have much lower edge density than center.
        A clean lens has similar edge distribution throughout the frame.
        """
        h, w = gray.shape
        qh, qw = max(1, h // 4), max(1, w // 4)

        corners = [
            gray[:qh, :qw],
            gray[:qh, w - qw:],
            gray[h - qh:, :qw],
            gray[h - qh:, w - qw:],
        ]
        center = gray[qh:h - qh, qw:w - qw]
        if center.size == 0:
            return False

        center_edges = float(np.mean(cv2.Canny(center, 50, 150))) + 1e-6
        corner_means = [float(np.mean(cv2.Canny(c, 50, 150))) for c in corners if c.size > 0]
        if not corner_means:
            return False
        avg_corner = sum(corner_means) / len(corner_means)
        return (avg_corner / center_edges) < self.DIRTY_CORNER_RATIO

    def _rain(self, gray: np.ndarray) -> bool:
        """
        Rain produces horizontal streaks.
        Measure ratio of horizontal vs total Sobel energy.
        """
        sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        h_energy = float(np.mean(np.abs(sobel_y)))
        v_energy = float(np.mean(np.abs(sobel_x)))
        total    = h_energy + v_energy
        if total < 1.0:
            return False
        return (h_energy / total) > self.RAIN_HORIZONTAL_RATIO

    def _shift(self, gray: np.ndarray) -> bool:
        """Camera shifted: >40% of pixels differ significantly from last frame."""
        with self._lock:
            prev = self._prev
        if prev is None or prev.shape != gray.shape:
            return False
        diff  = cv2.absdiff(prev, gray)
        ratio = float(np.count_nonzero(diff > 30)) / diff.size
        return ratio > self.SHIFT_DIFF_THRESHOLD

    def _vibration(self, gray: np.ndarray) -> bool:
        """
        Vibration: high variance in the sequence of inter-frame mean differences.
        """
        with self._lock:
            prev  = self._prev
            diffs = self._diffs

        if prev is not None and prev.shape == gray.shape:
            diff_val = float(np.mean(cv2.absdiff(prev, gray)))
            self._diffs.append(diff_val)

        if len(self._diffs) < self.VIBRATION_HISTORY:
            return False

        d_list = list(self._diffs)
        mean   = sum(d_list) / len(d_list)
        var    = sum((d - mean) ** 2 for d in d_list) / len(d_list)
        return var > self.VIBRATION_VAR_LIMIT


# ─────────────────────────────────────────────────────────────────────────────
# Recommendation builder
# ─────────────────────────────────────────────────────────────────────────────
def _recommend(
    focus: float, dirty: bool, rain: bool, shift: bool,
    over: bool, under: bool, vibration: bool, blockage: bool,
) -> str:
    if blockage:
        return "CRITICAL: Camera blocked — check physically"
    if shift:
        return "Adjust Camera Angle — camera has moved"
    if under:
        return "Increase Lighting — scene too dark"
    if over:
        return "Reduce Exposure — scene overexposed"
    if dirty:
        return "Clean Lens — debris detected on lens"
    if focus < 20:
        return "CRITICAL: Focus very poor — clean/refocus camera"
    if vibration:
        return "Camera Vibration — secure the mounting bracket"
    if rain:
        return "Rain detected — monitor OCR accuracy"
    if focus < 60:
        return "Focus degraded — clean or refocus lens"
    return "OK"
