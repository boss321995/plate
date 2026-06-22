"""
auto_calibration.py — Auto-Calibration Engine (Part 1)
=======================================================

Runs in a background thread every CALIBRATION_INTERVAL seconds.
Analyzes a rolling 5-minute window of frame metrics and adjusts:

    BLUR_THRESHOLD      min Laplacian variance to accept
    QUALITY_THRESHOLD   min 6-component quality score (0-100)
    GAMMA               brightness correction factor applied to plate crops
    WINDOW_SIZE         Best Frame Window size (3-8 frames)
    FPS_LIMIT           target capture FPS

Dynamic profile selection:
    Conditions are also matched to preset profiles in profiles/ folder.
    Auto-calibration fine-tunes on top of the selected preset.

Usage:
    cal = AutoCalibration()
    cal.start()
    ...
    cal.record_frame(blur=312.5, brightness=127.3, quality=82.1, speed=15.0)
    ...
    threshold = cal.blur_threshold   # read calibrated value
"""

from __future__ import annotations
import os
import json
import time
import threading
from pathlib import Path
from collections import deque
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
CALIBRATION_INTERVAL = float(os.getenv("CALIBRATION_INTERVAL", "300"))   # 5 min
PROFILES_DIR         = Path(os.getenv("PROFILES_DIR", "profiles"))
CURRENT_PROFILE_PATH = PROFILES_DIR / "current.json"
EMA_ALPHA            = 0.25   # How quickly calibration adapts (0=never, 1=instant)
METRIC_WINDOW_SEC    = 300.0  # Rolling window for metric collection (5 min)

DEFAULT_PROFILE: dict = {
    "blur_threshold":    100.0,
    "quality_threshold":  75.0,
    "gamma":               1.0,
    "window_size":           5,
    "fps_limit":           9.0,
    "mode":           "default",
    "updated_at":         None,
}


class _FrameMetric:
    __slots__ = ("blur", "brightness", "quality", "speed", "ts")

    def __init__(self, blur: float, brightness: float, quality: float, speed: float = 0.0):
        self.blur       = blur
        self.brightness = brightness
        self.quality    = quality
        self.speed      = speed
        self.ts         = time.time()


class AutoCalibration:
    """
    Background calibration engine.

    Call record_frame() on every processed frame to feed metrics.
    Read calibrated thresholds via properties (blur_threshold, etc.).
    Call start() to launch the background calibration thread.
    """

    def __init__(self):
        self._lock    = threading.Lock()
        self._metrics: deque[_FrameMetric] = deque()
        self._profile = dict(DEFAULT_PROFILE)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._load_saved_profile()

    # ── Frame recording ───────────────────────────────────────────────────────

    def record_frame(
        self,
        blur:       float,
        brightness: float,
        quality:    float,
        speed:      float = 0.0,
    ):
        """Feed one frame's metrics into the rolling calibration window."""
        now = time.time()
        with self._lock:
            self._metrics.append(_FrameMetric(blur, brightness, quality, speed))
            while self._metrics and now - self._metrics[0].ts > METRIC_WINDOW_SEC:
                self._metrics.popleft()

    # ── Calibrated threshold properties ───────────────────────────────────────

    @property
    def blur_threshold(self) -> float:
        return float(self._profile["blur_threshold"])

    @property
    def quality_threshold(self) -> float:
        return float(self._profile["quality_threshold"])

    @property
    def gamma(self) -> float:
        return float(self._profile["gamma"])

    @property
    def window_size(self) -> int:
        return int(self._profile["window_size"])

    @property
    def fps_limit(self) -> float:
        return float(self._profile["fps_limit"])

    @property
    def profile(self) -> dict:
        with self._lock:
            return dict(self._profile)

    # ── Background loop ───────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="auto-calibration"
        )
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            time.sleep(CALIBRATION_INTERVAL)
            try:
                self._calibrate()
            except Exception as e:
                print(f"[AutoCalibration] Calibration error: {e}")

    def _calibrate(self):
        with self._lock:
            if len(self._metrics) < 10:
                return
            metrics = list(self._metrics)

        blurs       = [m.blur       for m in metrics]
        brightnesses = [m.brightness for m in metrics]
        qualities   = [m.quality    for m in metrics]
        speeds      = [m.speed      for m in metrics]

        mean_blur  = sum(blurs)        / len(blurs)
        mean_br    = sum(brightnesses) / len(brightnesses)
        mean_qual  = sum(qualities)    / len(qualities)
        mean_speed = sum(speeds)       / len(speeds)

        # Automatically select a base preset based on current conditions
        preset = self._select_preset(mean_br, mean_speed, len(metrics))

        old = dict(self._profile)
        new = dict(preset)

        # Fine-tune on top of preset using EMA (do not hard-override preset)

        # ── BLUR_THRESHOLD ────────────────────────────────────────────────────
        if mean_blur < new["blur_threshold"] * 1.2:
            # Scene consistently blurry → loosen threshold
            new["blur_threshold"] = _ema(new["blur_threshold"], max(40.0, mean_blur * 0.80), EMA_ALPHA)
        elif mean_blur > new["blur_threshold"] * 3.0:
            # Scene very sharp → tighten
            new["blur_threshold"] = _ema(new["blur_threshold"], min(200.0, mean_blur * 0.50), EMA_ALPHA)
        else:
            # Smooth toward preset
            new["blur_threshold"] = _ema(old["blur_threshold"], new["blur_threshold"], EMA_ALPHA)

        # ── QUALITY_THRESHOLD ─────────────────────────────────────────────────
        if mean_qual < new["quality_threshold"] * 1.05:
            new["quality_threshold"] = _ema(new["quality_threshold"], max(50.0, mean_qual * 0.88), EMA_ALPHA)
        elif mean_qual > 92:
            new["quality_threshold"] = _ema(new["quality_threshold"], min(85.0, mean_qual * 0.92), EMA_ALPHA)
        else:
            new["quality_threshold"] = _ema(old["quality_threshold"], new["quality_threshold"], EMA_ALPHA)

        # ── GAMMA ─────────────────────────────────────────────────────────────
        if mean_br < 55:
            target_gamma = 0.65
        elif mean_br > 195:
            target_gamma = 1.6
        else:
            target_gamma = 1.0
        new["gamma"] = round(_ema(old["gamma"], target_gamma, EMA_ALPHA), 2)

        # ── WINDOW_SIZE (speed-based) ─────────────────────────────────────────
        if mean_speed < 20:
            new["window_size"] = 8
        elif mean_speed < 50:
            new["window_size"] = 5
        else:
            new["window_size"] = 3

        # ── FPS: scale with traffic volume ─────────────────────────────────────
        frames_per_min = len(metrics) / (METRIC_WINDOW_SEC / 60.0)
        if frames_per_min > 25:
            target_fps = 11.0
        elif frames_per_min < 5:
            target_fps = 3.0
        else:
            target_fps = float(new.get("fps_limit", 9.0))
        new["fps_limit"]    = round(_ema(old["fps_limit"], target_fps, EMA_ALPHA), 1)
        new["updated_at"]   = time.time()

        with self._lock:
            self._profile = new

        self._save_profile()
        print(
            f"[AutoCalibration] mode={new['mode']} "
            f"blur={new['blur_threshold']:.0f} quality={new['quality_threshold']:.0f} "
            f"gamma={new['gamma']:.2f} window={new['window_size']} fps={new['fps_limit']:.0f}"
        )

    # ── Preset selection ──────────────────────────────────────────────────────

    def _select_preset(
        self, mean_br: float, mean_speed: float, frame_count: int
    ) -> dict:
        """Choose the best preset profile for current conditions."""
        frames_per_min = frame_count / (METRIC_WINDOW_SEC / 60.0)

        if mean_br < 60:
            mode = "night"
        elif frames_per_min > 20:
            mode = "high_traffic"
        elif frames_per_min < 4:
            mode = "low_traffic"
        else:
            mode = "day"

        return self._load_preset(mode)

    def _load_preset(self, mode: str) -> dict:
        path = PROFILES_DIR / f"{mode}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text())
                data.setdefault("mode", mode)
                return data
            except Exception:
                pass
        # Inline fallbacks if profile files missing
        fallbacks = {
            "night":        {"blur_threshold": 60,  "quality_threshold": 65, "gamma": 0.7,  "window_size": 8, "fps_limit": 8},
            "high_traffic": {"blur_threshold": 80,  "quality_threshold": 70, "gamma": 1.0,  "window_size": 3, "fps_limit": 11},
            "low_traffic":  {"blur_threshold": 120, "quality_threshold": 80, "gamma": 1.0,  "window_size": 8, "fps_limit": 3},
            "rain":         {"blur_threshold": 50,  "quality_threshold": 60, "gamma": 0.8,  "window_size": 8, "fps_limit": 11},
            "day":          {"blur_threshold": 100, "quality_threshold": 75, "gamma": 1.0,  "window_size": 5, "fps_limit": 9},
        }
        base = dict(DEFAULT_PROFILE)
        base.update(fallbacks.get(mode, {}))
        base["mode"] = mode
        return base

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_profile(self):
        try:
            PROFILES_DIR.mkdir(parents=True, exist_ok=True)
            CURRENT_PROFILE_PATH.write_text(
                json.dumps(self._profile, indent=2, ensure_ascii=False)
            )
        except Exception as e:
            print(f"[AutoCalibration] Failed to save profile: {e}")

    def _load_saved_profile(self):
        try:
            if CURRENT_PROFILE_PATH.exists():
                data = json.loads(CURRENT_PROFILE_PATH.read_text())
                for k in DEFAULT_PROFILE:
                    if k in data:
                        self._profile[k] = data[k]
                self._profile.setdefault("mode", "loaded")
                print(f"[AutoCalibration] Restored profile: mode={self._profile.get('mode')}")
        except Exception as e:
            print(f"[AutoCalibration] Failed to load saved profile: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────
def _ema(old: float, new: float, alpha: float) -> float:
    return round(alpha * new + (1.0 - alpha) * old, 2)
