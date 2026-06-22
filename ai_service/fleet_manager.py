"""
fleet_manager.py — Central Fleet Manager (MEGA v6, Parts 1+2)

In-memory registry of all edge devices. Each device registers on boot and
sends heartbeats every 30 s. Devices missing > HEARTBEAT_TIMEOUT s → OFFLINE.

Usage (inside api_server.py):
    fleet_mgr = FleetManager()
    fleet_mgr.start()

    # Edge device boots
    fleet_mgr.register("cam-01", {"hostname": "rpi4-gate1", "site_id": "hq", ...})

    # Every 30 s
    fleet_mgr.heartbeat("cam-01", {"cpu": 42.1, "memory": 61.3, ...})
"""

from __future__ import annotations

import os
import time
import threading
import logging
from typing import Dict, Optional

log = logging.getLogger(__name__)

HEARTBEAT_TIMEOUT = float(os.getenv("FLEET_HB_TIMEOUT",  "90"))   # s → OFFLINE
WATCHDOG_INTERVAL = float(os.getenv("FLEET_WATCHDOG",    "15"))   # check period


# ─── Device record ────────────────────────────────────────────────────────────

class DeviceRecord:
    __slots__ = (
        "device_id", "hostname", "site_id", "camera_count",
        "software_version", "uptime", "cpu", "memory", "disk",
        "camera_status", "fps", "latency",
        "registered_at", "last_seen", "status",
    )

    def __init__(self, device_id: str, payload: dict) -> None:
        self.device_id        = device_id
        self.hostname         = payload.get("hostname",         device_id)
        self.site_id          = payload.get("site_id",          "default")
        self.camera_count     = int(payload.get("camera_count", 1))
        self.software_version = payload.get("software_version", "unknown")
        self.uptime           = 0.0
        self.cpu              = 0.0
        self.memory           = 0.0
        self.disk             = 0.0
        self.camera_status    = {}
        self.fps              = 0.0
        self.latency          = 0.0
        self.registered_at    = time.time()
        self.last_seen        = time.time()
        self.status           = "ONLINE"

    def apply_heartbeat(self, payload: dict) -> None:
        self.uptime        = float(payload.get("uptime",  self.uptime))
        self.cpu           = float(payload.get("cpu",     self.cpu))
        self.memory        = float(payload.get("memory",  self.memory))
        self.disk          = float(payload.get("disk",    self.disk))
        self.camera_status = payload.get("camera_status", self.camera_status)
        self.fps           = float(payload.get("fps",     self.fps))
        self.latency       = float(payload.get("latency", self.latency))
        self.last_seen     = time.time()
        self._refresh_status()

    def _refresh_status(self) -> None:
        age = time.time() - self.last_seen
        if age > HEARTBEAT_TIMEOUT:
            self.status = "OFFLINE"
        elif self.cpu > 85 or self.memory > 85 or self.disk > 90:
            self.status = "WARNING"
        else:
            self.status = "ONLINE"

    def as_dict(self) -> dict:
        return {
            "device_id":        self.device_id,
            "hostname":         self.hostname,
            "site_id":          self.site_id,
            "camera_count":     self.camera_count,
            "software_version": self.software_version,
            "uptime":           round(self.uptime,   1),
            "cpu":              round(self.cpu,      1),
            "memory":           round(self.memory,   1),
            "disk":             round(self.disk,     1),
            "camera_status":    self.camera_status,
            "fps":              round(self.fps,      1),
            "latency":          round(self.latency,  1),
            "registered_at":    self.registered_at,
            "last_seen":        self.last_seen,
            "age_sec":          round(time.time() - self.last_seen, 1),
            "status":           self.status,
        }


# ─── Fleet Manager ────────────────────────────────────────────────────────────

class FleetManager:
    """Thread-safe in-memory device registry with watchdog."""

    def __init__(self) -> None:
        self._devices: Dict[str, DeviceRecord] = {}
        self._lock    = threading.Lock()
        self._running = False

    # ── Public API ──────────────────────────────────────────────────────────

    def register(self, device_id: str, payload: dict) -> dict:
        with self._lock:
            if device_id in self._devices:
                self._devices[device_id].apply_heartbeat(payload)
                log.info("[Fleet] re-registered %s", device_id)
            else:
                self._devices[device_id] = DeviceRecord(device_id, payload)
                log.info("[Fleet] new device %s (site=%s)", device_id,
                         payload.get("site_id", "?"))
            return self._devices[device_id].as_dict()

    def heartbeat(self, device_id: str, payload: dict) -> bool:
        with self._lock:
            if device_id not in self._devices:
                self._devices[device_id] = DeviceRecord(device_id, payload)
                log.warning("[Fleet] heartbeat from unregistered %s — auto-added", device_id)
            self._devices[device_id].apply_heartbeat(payload)
        return True

    def get_device(self, device_id: str) -> Optional[dict]:
        with self._lock:
            rec = self._devices.get(device_id)
            return rec.as_dict() if rec else None

    def get_fleet(self, site_id: Optional[str] = None) -> list:
        with self._lock:
            recs = list(self._devices.values())
        if site_id:
            recs = [r for r in recs if r.site_id == site_id]
        return [r.as_dict() for r in recs]

    def get_stats(self) -> dict:
        with self._lock:
            total   = len(self._devices)
            online  = sum(1 for d in self._devices.values() if d.status == "ONLINE")
            warning = sum(1 for d in self._devices.values() if d.status == "WARNING")
            offline = sum(1 for d in self._devices.values() if d.status == "OFFLINE")
        return {
            "total":      total,
            "online":     online,
            "warning":    warning,
            "offline":    offline,
            "health_pct": round(online / total * 100 if total else 0.0, 1),
        }

    # ── Watchdog thread ─────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        t = threading.Thread(target=self._watchdog, daemon=True, name="fleet-watchdog")
        t.start()
        log.info("[Fleet] watchdog started (timeout=%.0f s)", HEARTBEAT_TIMEOUT)

    def _watchdog(self) -> None:
        while self._running:
            time.sleep(WATCHDOG_INTERVAL)
            with self._lock:
                for dev in self._devices.values():
                    prev = dev.status
                    dev._refresh_status()
                    if dev.status != prev:
                        log.warning("[Fleet] %s: %s → %s",
                                    dev.device_id, prev, dev.status)
