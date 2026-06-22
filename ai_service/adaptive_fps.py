"""
adaptive_fps.py — Adaptive FPS Engine
======================================

State machine with 3 operating modes:

  idle             →  3 FPS   (no vehicles, save CPU)
  vehicle_detected →  8 FPS   (vehicle approaching)
  tracking_active  → 11 FPS   (actively tracking ≥1 vehicle)

Transitions:
  any tracks active          → tracking_active
  tracks lost < 5s           → vehicle_detected  (hysteresis)
  no tracks for ≥ 5s         → idle
"""

import time


class AdaptiveFPSEngine:

    # FPS per state
    FPS_IDLE     = 3
    FPS_DETECTED = 8
    FPS_TRACKING = 11

    # How long (seconds) without tracks before returning to idle
    IDLE_TIMEOUT = 5.0
    # Brief hysteresis: keep DETECTED state for 1s after tracks vanish
    HYSTERESIS   = 1.0

    def __init__(self):
        self._state         = "idle"
        self._fps           = self.FPS_IDLE
        self._last_track_ts = 0.0   # Last time we saw ≥1 active track
        self._track_count   = 0

    # ── Public ───────────────────────────────────────────────────────────────

    def update(self, active_track_count: int) -> float:
        """
        Call every processed frame with the number of active ByteTrack tracks.
        Returns the current target FPS after the state transition.
        """
        now = time.time()
        self._track_count = active_track_count

        if active_track_count > 0:
            self._last_track_ts = now
            if self._state != "tracking_active":
                self._state = "tracking_active"
                self._fps   = self.FPS_TRACKING
        else:
            idle_for = now - self._last_track_ts
            if idle_for < self.HYSTERESIS:
                # Stay at current FPS briefly
                pass
            elif idle_for < self.IDLE_TIMEOUT:
                if self._state == "tracking_active":
                    self._state = "vehicle_detected"
                    self._fps   = self.FPS_DETECTED
            else:
                if self._state != "idle":
                    self._state = "idle"
                    self._fps   = self.FPS_IDLE

        return self._fps

    def get_interval(self) -> float:
        """Seconds between processed frames."""
        return 1.0 / self._fps

    def get_fps(self) -> float:
        return float(self._fps)

    def get_state(self) -> str:
        return self._state

    def get_track_count(self) -> int:
        return self._track_count

    def get_status(self) -> dict:
        return {
            "state":       self._state,
            "fps":         self._fps,
            "track_count": self._track_count,
        }
