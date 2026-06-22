"""
direction_engine.py — Virtual Line Direction Detector
======================================================

Tracks vehicle centroid movement across a virtual horizontal line.

  Centroid moves DOWN through line → IN
  Centroid moves UP   through line → OUT

Usage:
    engine = DirectionEngine(line_y_ratio=0.5)
    direction = engine.update(track_id, cx, cy, frame_h)
    # Returns "IN" | "OUT" | None
"""

import time
from typing import Optional


class DirectionEngine:
    """Per-track centroid history → direction detection."""

    # Require at least this many consecutive points for reliable crossing
    MIN_HISTORY    = 3
    LOOK_BACK      = 6     # Use last N points for crossing detection
    STALE_AGE_SEC  = 60.0  # Forget history older than this

    def __init__(self, line_y_ratio: float = 0.5):
        """
        Args:
            line_y_ratio: Vertical position of virtual line (0.0=top, 1.0=bottom)
        """
        self.line_y_ratio = line_y_ratio
        # track_id → list of (cx, cy, timestamp)
        self._history: dict[int, list] = {}

    # ── Public ───────────────────────────────────────────────────────────────

    def update(self, track_id: int, cx: float, cy: float, frame_h: int) -> Optional[str]:
        """
        Record centroid position and detect line crossing.

        Returns:
            "IN"  if centroid crossed downward,
            "OUT" if centroid crossed upward,
            None  if no crossing detected yet.
        """
        hist = self._history.setdefault(track_id, [])
        hist.append((cx, cy, time.time()))

        if len(hist) < self.MIN_HISTORY:
            return None

        line_y = frame_h * self.line_y_ratio
        recent = hist[-self.LOOK_BACK:]
        prev_cy = recent[0][1]
        last_cy = recent[-1][1]

        if prev_cy < line_y <= last_cy:
            return "IN"    # Centroid moved DOWN through line
        if prev_cy > line_y >= last_cy:
            return "OUT"   # Centroid moved UP through line
        return None

    def infer_direction(self, track_id: int) -> str:
        """
        Determine overall movement direction when a track ends
        without ever crossing the line.
        """
        hist = self._history.get(track_id, [])
        if len(hist) < 2:
            return "IN"
        return "IN" if hist[-1][1] > hist[0][1] else "OUT"

    def get_speed(self, track_id: int) -> float:
        """
        Estimate vehicle speed as pixel distance between the last two points.
        Used by WindowManager to determine dynamic window size.
        """
        hist = self._history.get(track_id, [])
        if len(hist) < 2:
            return 0.0
        x1, y1, _ = hist[-2]
        x2, y2, _ = hist[-1]
        return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

    def cleanup(self, track_id: int):
        """Remove history for a finished track."""
        self._history.pop(track_id, None)

    def cleanup_stale(self, max_age_sec: Optional[float] = None):
        """Remove history entries older than max_age_sec."""
        age = max_age_sec or self.STALE_AGE_SEC
        now = time.time()
        stale = [
            tid for tid, h in self._history.items()
            if h and now - h[-1][2] > age
        ]
        for tid in stale:
            del self._history[tid]
