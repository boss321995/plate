"""
ocr_analyzer.py — OCR Performance Analyzer (Part 10)
=====================================================

Tracks OCR quality metrics in a sliding time window:

    success_rate        fraction of OCR calls that produced usable text
    avg_confidence      mean OCR confidence score
    top_confusions      most common character-level mistakes
    province_confusion  most confused province pairs

When a confirmed plate is available (backend fuzzy match), call
record_correction(ocr, confirmed) to learn the mistake.

Usage:
    analyzer = OCRAnalyzer()
    analyzer.record(ocr_text="กข1234", confidence=0.91, success=True)
    analyzer.record_correction("8กข123", "3กข123")
    print(analyzer.as_dict())
"""

from __future__ import annotations
import time
import threading
from collections import Counter, deque
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
WINDOW_SEC    = float(600)   # 10-minute sliding window
MAX_HISTORY   = int(5_000)   # Hard cap on result entries in memory


# ─────────────────────────────────────────────────────────────────────────────
# OCRAnalyzer
# ─────────────────────────────────────────────────────────────────────────────
class OCRAnalyzer:
    """
    Thread-safe OCR performance tracker.

    record()             — called for every OCR attempt
    record_correction()  — called when the confirmed plate differs from OCR
    as_dict()            — returns full stats snapshot
    """

    def __init__(self):
        self._lock          = threading.Lock()
        self._results: deque = deque(maxlen=MAX_HISTORY)
        # (success: bool, confidence: float, timestamp: float)

        self._char_confuse  = Counter()    # (ocr_char, correct_char) → count
        self._prov_confuse  = Counter()    # (ocr_province, correct_province) → count

        # Trend: list of (avg_conf, timestamp) for last N windows
        self._conf_trend: deque = deque(maxlen=60)

    # ── Public API ────────────────────────────────────────────────────────────

    def record(
        self,
        ocr_text:    str,
        confidence:  float,
        success:     bool,
    ):
        """Log one OCR attempt result."""
        now = time.time()
        with self._lock:
            self._results.append((success, confidence, now))
            self._prune(now)

    def record_correction(
        self,
        ocr_text:      str,
        confirmed:     str,
        province_ocr:  Optional[str] = None,
        province_real: Optional[str] = None,
    ):
        """
        Record a confirmed correction (backend fuzzy match or manual override).
        Feeds character-level confusion table.
        """
        if ocr_text == confirmed:
            return
        with self._lock:
            self._analyze_char_confusion(ocr_text, confirmed)
            if province_ocr and province_real and province_ocr != province_real:
                self._prov_confuse[(province_ocr, province_real)] += 1

    # ── Stats ─────────────────────────────────────────────────────────────────

    def success_rate(self) -> float:
        with self._lock:
            self._prune(time.time())
            data = list(self._results)
        if not data:
            return 0.0
        return round(sum(1 for s, _, _ in data if s) / len(data), 4)

    def avg_confidence(self) -> float:
        with self._lock:
            self._prune(time.time())
            data = list(self._results)
        if not data:
            return 0.0
        return round(sum(c for _, c, _ in data) / len(data), 4)

    def top_confusions(self, n: int = 10) -> list[dict]:
        with self._lock:
            items = self._char_confuse.most_common(n)
        return [{"wrong": k[0], "correct": k[1], "count": v} for k, v in items]

    def top_province_confusions(self, n: int = 5) -> list[dict]:
        with self._lock:
            items = self._prov_confuse.most_common(n)
        return [{"ocr": k[0], "correct": k[1], "count": v} for k, v in items]

    def sample_count(self) -> int:
        with self._lock:
            return len(self._results)

    def as_dict(self) -> dict:
        return {
            "success_rate":         self.success_rate(),
            "avg_confidence":       self.avg_confidence(),
            "sample_count":         self.sample_count(),
            "top_confusions":       self.top_confusions(10),
            "province_confusions":  self.top_province_confusions(5),
            "window_sec":           WINDOW_SEC,
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _prune(self, now: float):
        """Remove entries older than WINDOW_SEC. Must be called with lock held."""
        cutoff = now - WINDOW_SEC
        while self._results and self._results[0][2] < cutoff:
            self._results.popleft()

    def _analyze_char_confusion(self, wrong: str, correct: str):
        """
        Align OCR text vs confirmed text character-by-character.
        Works best when the strings are the same length (common case:
        single-character substitutions like 8→3 or ข→ช).
        """
        if len(wrong) == len(correct):
            for wc, cc in zip(wrong, correct):
                if wc != cc:
                    self._char_confuse[(wc, cc)] += 1
        else:
            # For length mismatches just record the pair as a whole
            self._char_confuse[(wrong[:3], correct[:3])] += 1
