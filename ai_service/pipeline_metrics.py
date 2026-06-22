"""
pipeline_metrics.py — Stage-by-Stage Pipeline Counters (Part 7)
================================================================

Tracks every stage from raw frame to saved detection.

Stages:
    vehicle_seen        Vehicle box detected by YOLO
    best_frame_selected Quality score passed threshold
    plate_detected      Plate crop found in best frame
    ocr_success         OCR returned a usable plate text
    backend_saved       Backend API accepted the detection
    dashboard_sent      Socket.IO event emitted to dashboard
    rejected_blur       Rejected: Laplacian variance too low
    rejected_reflection Rejected: overexposed pixel ratio too high
    rejected_plate_size Rejected: plate crop too small (< 80x25)
    duplicate_suppressed Cooldown hit — same plate:camera pair
"""

from __future__ import annotations
import threading
from typing import Iterator


# ─────────────────────────────────────────────────────────────────────────────
# Counter names
# ─────────────────────────────────────────────────────────────────────────────
COUNTER_NAMES = (
    "vehicle_seen",
    "best_frame_selected",
    "plate_detected",
    "ocr_success",
    "backend_saved",
    "dashboard_sent",
    "rejected_blur",
    "rejected_reflection",
    "rejected_plate_size",
    "duplicate_suppressed",
)


class PipelineMetrics:
    """
    Thread-safe integer counters for each pipeline stage.

    Usage:
        pm = PipelineMetrics()
        pm.vehicle_seen += 1      # NOT thread-safe; use inc() instead
        pm.inc("vehicle_seen")    # Thread-safe
    """

    def __init__(self):
        self._lock    = threading.Lock()
        self._counts: dict[str, int] = {name: 0 for name in COUNTER_NAMES}

    # ── Increment ─────────────────────────────────────────────────────────────

    def inc(self, name: str, amount: int = 1):
        """Increment counter by `amount`."""
        with self._lock:
            if name in self._counts:
                self._counts[name] += amount

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, name: str) -> int:
        with self._lock:
            return self._counts.get(name, 0)

    def as_dict(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def __iter__(self) -> Iterator[tuple[str, int]]:
        return iter(self.as_dict().items())

    # ── Reset ─────────────────────────────────────────────────────────────────

    def reset(self):
        with self._lock:
            for k in self._counts:
                self._counts[k] = 0

    def reset_one(self, name: str):
        with self._lock:
            if name in self._counts:
                self._counts[name] = 0

    # ── Derived stats ─────────────────────────────────────────────────────────

    def yield_rate(self) -> float:
        """Fraction of vehicle_seen that reached backend_saved."""
        seen  = self.get("vehicle_seen")
        saved = self.get("backend_saved")
        return round(saved / seen, 4) if seen else 0.0

    def ocr_success_rate(self) -> float:
        """Fraction of plate_detected that produced usable OCR."""
        plates = self.get("plate_detected")
        ocr    = self.get("ocr_success")
        return round(ocr / plates, 4) if plates else 0.0

    def summary(self) -> dict:
        d = self.as_dict()
        d["yield_rate"]       = self.yield_rate()
        d["ocr_success_rate"] = self.ocr_success_rate()
        return d
