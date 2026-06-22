"""
track_manager.py — Vehicle Track State Registry
================================================

Manages per-track state (candidates, direction, save status).
Provides LRU eviction and stale-track cleanup.

TrackState owns the Best Frame Window (list of FrameCandidate).
TrackManager is the registry: get_or_create / cleanup.
"""

from __future__ import annotations
import time
from typing import Optional

from window_manager import FrameCandidate

# ─────────────────────────────────────────────────────────────────────────────
# Config (can be overridden via env in client.py)
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_FORGET_SEC  = 30.0
DEFAULT_MAX_TRACKS  = 500


# ─────────────────────────────────────────────────────────────────────────────
# TrackState
# ─────────────────────────────────────────────────────────────────────────────
class TrackState:
    """All mutable state for a single vehicle track."""

    __slots__ = (
        "track_id", "candidates", "saved",
        "first_seen", "last_seen", "direction",
    )

    def __init__(self, track_id: int):
        self.track_id:   int              = track_id
        self.candidates: list[FrameCandidate] = []
        self.saved:      bool             = False
        self.first_seen: float            = time.time()
        self.last_seen:  float            = time.time()
        self.direction:  str              = "IN"

    # ── Candidate management ──────────────────────────────────────────────────

    def add_candidate(
        self,
        frame,                # np.ndarray
        score:      float,
        components: dict,
        max_window: int,
    ):
        """
        Add a quality-passing frame to the Best Frame Window.
        When the window overflows, keep only the top-scoring frames.
        """
        self.candidates.append(FrameCandidate(frame, score, components))
        if len(self.candidates) > max_window:
            # Prune: keep the best max_window candidates by score
            self.candidates.sort(key=lambda c: c.score, reverse=True)
            self.candidates = self.candidates[:max_window]

    def is_window_full(self, window_size: int) -> bool:
        return len(self.candidates) >= window_size

    def best_candidate(self) -> Optional[FrameCandidate]:
        if not self.candidates:
            return None
        return max(self.candidates, key=lambda c: c.score)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def touch(self):
        self.last_seen = time.time()

    def is_stale(self, forget_sec: float = DEFAULT_FORGET_SEC) -> bool:
        return time.time() - self.last_seen > forget_sec

    def age_sec(self) -> float:
        return time.time() - self.first_seen


# ─────────────────────────────────────────────────────────────────────────────
# TrackManager (Registry)
# ─────────────────────────────────────────────────────────────────────────────
class TrackManager:
    """
    Thread-safe-ish registry of TrackState objects.
    Provides LRU eviction when size > max_tracks.
    """

    def __init__(
        self,
        forget_sec: float = DEFAULT_FORGET_SEC,
        max_tracks: int   = DEFAULT_MAX_TRACKS,
    ):
        self.forget_sec = forget_sec
        self.max_tracks = max_tracks
        self._tracks: dict[int, TrackState] = {}

    # ── Access ────────────────────────────────────────────────────────────────

    def get_or_create(self, track_id: int) -> TrackState:
        if track_id not in self._tracks:
            self._tracks[track_id] = TrackState(track_id)
        state = self._tracks[track_id]
        state.touch()
        return state

    def get(self, track_id: int) -> Optional[TrackState]:
        return self._tracks.get(track_id)

    def all_tracks(self) -> list[TrackState]:
        return list(self._tracks.values())

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self) -> list[TrackState]:
        """
        Remove stale tracks. Returns the list of removed TrackState objects
        so the caller can flush any unsaved candidates.
        """
        stale_ids = [
            tid for tid, ts in self._tracks.items()
            if ts.is_stale(self.forget_sec)
        ]
        removed = [self._tracks.pop(tid) for tid in stale_ids]

        # LRU eviction if registry is still too large
        if len(self._tracks) > self.max_tracks:
            oldest = sorted(
                self._tracks.keys(),
                key=lambda k: self._tracks[k].last_seen,
            )
            for tid in oldest[: len(oldest) // 2]:
                removed.append(self._tracks.pop(tid))

        return removed

    # ── Stats ─────────────────────────────────────────────────────────────────

    def active_count(self) -> int:
        return len(self._tracks)

    def saved_count(self) -> int:
        return sum(1 for s in self._tracks.values() if s.saved)

    def __len__(self):
        return len(self._tracks)
