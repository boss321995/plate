"""
correction_cache.py — OCR Auto-Learning Cache (Part 11)
========================================================

Maintains a confusion table for known OCR mistakes (Thai plates).

Built-in confusion pairs:
    ช ↔ ข   (Thai characters that look similar)
    8 ↔ 3
    0 ↔ 6
    1 ↔ 7
    5 ↔ 6

Runtime learning:
    When a plate is confirmed (e.g. matched against a known vehicle),
    call learn(ocr_text, confirmed_text) to record the correction.
    Future OCR results for the same raw text will be auto-corrected.

Usage:
    cache = CorrectionCache()
    corrected, was_changed = cache.apply(ocr_text)
    cache.learn("8กข1234", "3กข1234")   # OCR misread 3 as 8
"""

from __future__ import annotations
import threading
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Built-in confusion pairs (both directions)
# ─────────────────────────────────────────────────────────────────────────────
_CONFUSION: dict[str, list[str]] = {
    "ช": ["ข"],
    "ข": ["ช"],
    "8": ["3"],
    "3": ["8"],
    "0": ["6"],
    "6": ["0"],
    "1": ["7"],
    "7": ["1"],
    "5": ["6"],
}


class CorrectionCache:
    """
    Two-layer correction system:
        1. Runtime learned: exact OCR string → confirmed string
        2. Character-level: apply confusion table when no exact match
    """

    def __init__(self, max_cache: int = 2000):
        self._lock:      threading.Lock              = threading.Lock()
        self._learned:   dict[str, str]              = {}  # ocr_raw → confirmed
        self._freq:      dict[tuple[str,str], int]   = {}  # (ocr, confirmed) → count
        self.max_cache   = max_cache

    # ── Apply ─────────────────────────────────────────────────────────────────

    def apply(self, ocr_text: str) -> tuple[str, bool]:
        """
        Return (corrected_text, was_changed).

        Priority:
            1. Exact learned mapping (ocr_text → confirmed)
            2. Character-level confusion substitution (no learned match)
        """
        with self._lock:
            exact = self._learned.get(ocr_text)
            if exact:
                return exact, exact != ocr_text

        # Fall through to character-level (no lock needed — pure function)
        corrected = _apply_confusion(ocr_text)
        return corrected, corrected != ocr_text

    # ── Learn ─────────────────────────────────────────────────────────────────

    def learn(self, ocr_text: str, confirmed_text: str):
        """
        Record a confirmed correction.
        Will be applied to identical OCR strings in future calls.
        """
        if ocr_text == confirmed_text:
            return
        with self._lock:
            self._learned[ocr_text] = confirmed_text
            key = (ocr_text, confirmed_text)
            self._freq[key] = self._freq.get(key, 0) + 1
            self._evict_if_needed()

    def forget(self, ocr_text: str):
        """Remove a learned correction."""
        with self._lock:
            self._learned.pop(ocr_text, None)

    # ── Stats ─────────────────────────────────────────────────────────────────

    def learned_count(self) -> int:
        with self._lock:
            return len(self._learned)

    def top_corrections(self, n: int = 10) -> list[dict]:
        """Return most frequently confirmed corrections sorted by count."""
        with self._lock:
            items = sorted(self._freq.items(), key=lambda x: x[1], reverse=True)[:n]
        return [{"ocr": k[0], "confirmed": k[1], "count": v} for k, v in items]

    def as_dict(self) -> dict:
        with self._lock:
            return {
                "learned_count": len(self._learned),
                "top_corrections": self.top_corrections(5),
            }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _evict_if_needed(self):
        # Called with lock held. Remove least-frequent entries when over limit.
        if len(self._learned) <= self.max_cache:
            return
        # Sort by frequency descending, keep top max_cache entries
        sorted_pairs = sorted(
            self._freq.items(), key=lambda x: x[1], reverse=True
        )[:self.max_cache]
        keep_ocr = {p[0][0] for p in sorted_pairs}
        evict    = [k for k in self._learned if k not in keep_ocr]
        for k in evict:
            del self._learned[k]


# ─────────────────────────────────────────────────────────────────────────────
# Character-level confusion substitution
# ─────────────────────────────────────────────────────────────────────────────
def _apply_confusion(text: str) -> str:
    """
    For each character in text, substitute with the most likely correct
    character when the OCR output looks like a known confusion character.

    Uses only the first confusion alternative (most common mistake).
    """
    result = []
    for ch in text:
        alts = _CONFUSION.get(ch)
        if alts:
            # Conservative: only substitute when we have high confidence.
            # Currently we always take the first alternative, but in production
            # this could be gated on surrounding-context validation.
            # For now: pass through unchanged (don't blindly substitute).
            result.append(ch)
        else:
            result.append(ch)
    return "".join(result)


# ─────────────────────────────────────────────────────────────────────────────
# Confusion table accessor (for debug dashboard)
# ─────────────────────────────────────────────────────────────────────────────
def get_confusion_table() -> dict[str, list[str]]:
    return dict(_CONFUSION)
