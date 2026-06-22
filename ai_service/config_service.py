"""
config_service.py — Remote Configuration Service (MEGA v6, Part 3)

Central config store. The dashboard pushes parameter updates via the backend;
edge devices poll GET /fleet/config/{device_id} to receive them without rebooting.

Supported parameters (all have safe defaults):
    fps_limit          float   FPS cap sent to adaptive_fps
    quality_threshold  float   minimum composite quality score
    blur_threshold     float   Laplacian variance floor
    gamma              float   plate brightness correction
    window_size        int     Best Frame Window size
    retention_days     int     evidence image lifetime
    profile            str     active preset name (day/night/rain/…)
    debug_images       bool    write pending/*.jpg for inspection
"""

from __future__ import annotations

import os
import json
import threading
import logging
from typing import Any, Dict

log = logging.getLogger(__name__)

CONFIG_FILE = os.getenv("CONFIG_STORE", "config_store.json")

_DEFAULTS: Dict[str, Any] = {
    "fps_limit":         11.0,
    "quality_threshold": 0.55,
    "blur_threshold":    40.0,
    "gamma":             1.0,
    "window_size":       5,
    "retention_days":    3,
    "profile":           "day",
    "debug_images":      True,
}


class ConfigService:
    """Per-device JSON-backed config with live reload."""

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock  = threading.RLock()
        self._load()

    # ── Public API ──────────────────────────────────────────────────────────

    def get_config(self, device_id: str) -> dict:
        """Return merged config (defaults + any device overrides)."""
        with self._lock:
            return {**_DEFAULTS, **self._store.get(device_id, {})}

    def update_config(self, device_id: str, patch: dict) -> dict:
        """Apply a partial update for one device. Unknown keys are silently ignored."""
        with self._lock:
            current = self._store.get(device_id, {})
            allowed = {k: v for k, v in patch.items() if k in _DEFAULTS}
            current.update(allowed)
            self._store[device_id] = current
            self._save()
            log.info("[Config] %s updated: %s", device_id, list(allowed.keys()))
            return {**_DEFAULTS, **current}

    def reset_config(self, device_id: str) -> dict:
        """Remove device overrides — device reverts to defaults on next poll."""
        with self._lock:
            self._store.pop(device_id, None)
            self._save()
        log.info("[Config] %s reset to defaults", device_id)
        return dict(_DEFAULTS)

    def list_devices(self) -> list:
        with self._lock:
            return list(self._store.keys())

    def defaults(self) -> dict:
        return dict(_DEFAULTS)

    # ── Persistence ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self._store = json.load(f)
                log.info("[Config] loaded %d device configs from %s",
                         len(self._store), CONFIG_FILE)
        except Exception as exc:
            log.warning("[Config] could not load %s: %s", CONFIG_FILE, exc)
            self._store = {}

    def _save(self) -> None:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._store, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            log.warning("[Config] could not save %s: %s", CONFIG_FILE, exc)
