"""
health_monitor.py — FastAPI /health Endpoint (Part 6)
======================================================

Exposes system + pipeline health via a lightweight HTTP server.

Metrics returned:
    camera_status, fps_current, cpu_percent, memory_percent,
    queue_size, network_latency_ms, last_detection_at,
    uptime_sec, pipeline_metrics

Designed to run as a background thread alongside client.py.
Call HealthMonitor.update_*() from the main capture loop to keep
metrics fresh.
"""

from __future__ import annotations
import time
import threading
import os
from typing import Optional

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

try:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    import uvicorn
    _FASTAPI = True
except ImportError:
    _FASTAPI = False


# ─────────────────────────────────────────────────────────────────────────────
# HealthMonitor — shared state, updated by capture loop
# ─────────────────────────────────────────────────────────────────────────────
class HealthMonitor:
    """
    Singleton-style shared metrics store.

    The capture loop calls update_* methods; the /health endpoint reads them.
    """

    def __init__(self, camera_ids: list[str], host: str = "0.0.0.0", port: int = 8880):
        self._lock          = threading.Lock()
        self._start_time    = time.time()

        # Mutable metrics
        self._camera_status: dict[str, str] = {cid: "unknown" for cid in camera_ids}
        self._fps_current:   float = 0.0
        self._queue_size:    int   = 0
        self._last_detect:   Optional[float] = None
        self._network_ms:    float = 0.0

        self.host = host
        self.port = port
        self._server_thread: Optional[threading.Thread] = None

    # ── Update methods (called from capture loop) ─────────────────────────────

    def set_camera_status(self, camera_id: str, status: str):
        """status: 'ok' | 'reconnecting' | 'lost'"""
        with self._lock:
            self._camera_status[camera_id] = status

    def set_fps(self, fps: float):
        with self._lock:
            self._fps_current = round(fps, 2)

    def set_queue_size(self, size: int):
        with self._lock:
            self._queue_size = size

    def record_detection(self):
        with self._lock:
            self._last_detect = time.time()

    def set_network_latency(self, ms: float):
        with self._lock:
            self._network_ms = round(ms, 1)

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def snapshot(self, pipeline_metrics: Optional[dict] = None) -> dict:
        with self._lock:
            cam_status = dict(self._camera_status)
            fps        = self._fps_current
            q_size     = self._queue_size
            last_det   = self._last_detect
            net_ms     = self._network_ms

        cpu_pct = psutil.cpu_percent(interval=None) if _PSUTIL else -1
        mem_pct = psutil.virtual_memory().percent    if _PSUTIL else -1
        disk_gb = _disk_free_gb()

        status = "ok"
        if any(v != "ok" for v in cam_status.values()):
            status = "degraded"
        if disk_gb < 1.0:
            status = "critical"

        return {
            "status":              status,
            "uptime_sec":          round(time.time() - self._start_time, 1),
            "camera_status":       cam_status,
            "fps_current":         fps,
            "cpu_percent":         cpu_pct,
            "memory_percent":      mem_pct,
            "disk_free_gb":        disk_gb,
            "queue_size":          q_size,
            "network_latency_ms":  net_ms,
            "last_detection_at":   last_det,
            "last_detection_ago":  round(time.time() - last_det, 1) if last_det else None,
            "pipeline_metrics":    pipeline_metrics or {},
        }

    # ── HTTP Server ───────────────────────────────────────────────────────────

    def start(self, pipeline_metrics_ref=None):
        """
        Start /health HTTP server in a daemon thread.
        pipeline_metrics_ref: a PipelineMetrics instance (optional).
        """
        if not _FASTAPI:
            print("[HealthMonitor] fastapi/uvicorn not installed — /health disabled")
            return

        monitor = self
        pm_ref   = pipeline_metrics_ref

        app = FastAPI(title="LPR Health")

        @app.get("/health")
        def health():
            pm_dict = pm_ref.as_dict() if pm_ref else {}
            return JSONResponse(monitor.snapshot(pm_dict))

        def _run():
            uvicorn.run(
                app,
                host=monitor.host,
                port=monitor.port,
                log_level="warning",
            )

        self._server_thread = threading.Thread(target=_run, daemon=True, name="health-monitor")
        self._server_thread.start()
        print(f"[HealthMonitor] /health serving on http://{self.host}:{self.port}/health")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _disk_free_gb() -> float:
    try:
        if _PSUTIL:
            usage = psutil.disk_usage("/")
            return round(usage.free / 1024 ** 3, 2)
    except Exception:
        pass
    return -1.0
