"""
window_manager.py — Dynamic Best Frame Window Manager
======================================================

Determines window size dynamically from vehicle speed.

Speed tiers (Part 1):
    speed < 20 px/frame  → window = 8  (slow / parked)
    speed < 50 px/frame  → window = 5  (medium speed)
    speed >= 50 px/frame → window = 3  (fast-moving)

Also owns FrameCandidate — the per-frame quality snapshot stored in memory
until the window is flushed to pending_frames/.
"""

from __future__ import annotations
import time
import numpy as np
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Speed thresholds (pixels per frame)
# ─────────────────────────────────────────────────────────────────────────────
SPEED_SLOW   = 20.0   # px/frame
SPEED_MEDIUM = 50.0   # px/frame

WINDOW_SLOW   = 8
WINDOW_MEDIUM = 5
WINDOW_FAST   = 3


class FrameCandidate:
    """Single candidate frame stored in the Best Frame Window."""
    __slots__ = ("frame", "score", "components", "ts")

    def __init__(self, frame: np.ndarray, score: float, components: dict):
        self.frame      = frame.copy()
        self.score      = score
        self.components = components
        self.ts         = time.time()


# ─────────────────────────────────────────────────────────────────────────────
# WindowManager
# ─────────────────────────────────────────────────────────────────────────────
class WindowManager:
    """
    Manages per-track speed history and the dynamic window size calculation.
    Works together with TrackManager: the window size returned here tells
    TrackState how many candidates to keep.
    """

    # Number of past frames used to smooth speed estimate
    SPEED_HISTORY = 5

    def __init__(self):
        # track_id → deque of (cx, cy) centroids (last SPEED_HISTORY frames)
        self._centroids: dict[int, list] = {}

    # ── Speed ─────────────────────────────────────────────────────────────────

    def update_centroid(self, track_id: int, cx: float, cy: float):
        """Record new centroid position."""
        hist = self._centroids.setdefault(track_id, [])
        hist.append((cx, cy))
        if len(hist) > self.SPEED_HISTORY:
            del hist[0]

    def get_speed(self, track_id: int) -> float:
        """
        Estimate speed as mean pixel distance between consecutive centroid
        positions over the last SPEED_HISTORY frames.
        """
        hist = self._centroids.get(track_id, [])
        if len(hist) < 2:
            return 0.0
        distances = [
            ((hist[i][0] - hist[i - 1][0]) ** 2 +
             (hist[i][1] - hist[i - 1][1]) ** 2) ** 0.5
            for i in range(1, len(hist))
        ]
        return sum(distances) / len(distances)

    # ── Dynamic Window Size ───────────────────────────────────────────────────

    @staticmethod
    def get_window_size(speed: float) -> int:
        """
        Map vehicle speed → Best Frame Window size.

        speed < 20  → 8 frames (slow/stopped — collect more for better OCR)
        speed < 50  → 5 frames (medium speed)
        speed >= 50 → 3 frames (fast — fewer frames available)
        """
        if speed < SPEED_SLOW:
            return WINDOW_SLOW
        elif speed < SPEED_MEDIUM:
            return WINDOW_MEDIUM
        else:
            return WINDOW_FAST

    def get_window_size_for_track(self, track_id: int) -> int:
        return self.get_window_size(self.get_speed(track_id))

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self, track_id: int):
        self._centroids.pop(track_id, None)

    def cleanup_all(self, active_ids: set):
        stale = [tid for tid in self._centroids if tid not in active_ids]
        for tid in stale:
            del self._centroids[tid]
