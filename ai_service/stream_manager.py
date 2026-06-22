"""
stream_manager.py — Dual Stream Manager for Hikvision (MEGA v7, Parts 19-21)

Architecture:
  Sub Stream (102/202/…):  Always-on, low-res, used for:
    • Vehicle detection + ByteTrack
    • LiveView (640×360, served via /snapshot)
    • Camera diagnostics + motion detection
    • Health monitoring

  Main Stream (101/201/…): On-demand, high-res, used for:
    • Best-frame snapshot when window is full
    • Plate detection crop
    • PaddleOCR input
    • Fingerprint extraction
    Never kept open continuously.

Watchdog (Part 20):
  If no sub-stream frame received for WATCHDOG_TIMEOUT seconds:
    release → sleep 2s → reconnect
  Tracks: reconnect_count, last_successful_frame

LiveView (Part 21):
  Always uses sub stream at 640×360, never main stream.
"""

from __future__ import annotations

import os
import time
import logging
import threading
import numpy as np
from typing import Optional

import cv2

log = logging.getLogger(__name__)

WATCHDOG_TIMEOUT  = float(os.getenv("WATCHDOG_TIMEOUT",    "5.0"))
RECONNECT_DELAY   = float(os.getenv("CAM_RECONNECT_DELAY", "2.0"))
CAM_MAX_RETRY     = int(os.getenv("CAM_MAX_RETRY",         "30"))
LIVEVIEW_W        = int(os.getenv("LIVEVIEW_WIDTH",        "640"))
LIVEVIEW_H        = int(os.getenv("LIVEVIEW_HEIGHT",       "360"))

# Main-stream skips initial buffered frames before grabbing the real frame
MAIN_SKIP_FRAMES  = int(os.getenv("MAIN_SKIP_FRAMES", "3"))


class DualStreamCapture:
    """
    Manages one camera's sub stream (always-on) and main stream (on-demand).

    Thread-safe for read_sub() + grab_main_frame() called from different contexts.
    """

    def __init__(
        self,
        camera_id: str,
        sub_url:   str,
        main_url:  str,
    ) -> None:
        self.camera_id       = camera_id
        self.sub_url         = sub_url
        self.main_url        = main_url

        self._sub_cap:  Optional[cv2.VideoCapture] = None
        self._sub_lock  = threading.Lock()
        self._main_lock = threading.Lock()

        # Stats
        self.reconnect_count      = 0
        self.last_frame_ts        = time.time()
        self.sub_fps              = 0.0
        self.sub_online           = False
        self.main_online          = False
        self._fps_cnt             = 0
        self._fps_t               = time.time()

        # LiveView (latest sub-stream frame resized to 640×360, as JPEG bytes)
        self._liveview_jpeg: Optional[bytes] = None
        self._lv_lock        = threading.Lock()

    # ── Sub stream ─────────────────────────────────────────────────────────

    def open_sub(self, max_attempts: int = 5) -> bool:
        """Open sub stream. Returns True on success."""
        for attempt in range(1, max_attempts + 1):
            cap = cv2.VideoCapture(self.sub_url)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                with self._sub_lock:
                    self._sub_cap = cap
                self.sub_online    = True
                self.last_frame_ts = time.time()
                log.info("[Stream] %s sub stream opened (attempt %d): %s",
                         self.camera_id, attempt, self._safe_url(self.sub_url))
                return True
            log.warning("[Stream] %s sub open failed (%d/%d)",
                        self.camera_id, attempt, max_attempts)
            time.sleep(RECONNECT_DELAY)
        self.sub_online = False
        log.error("[Stream] %s sub stream could not be opened after %d attempts",
                  self.camera_id, max_attempts)
        return False

    def read_sub(self) -> tuple[bool, Optional[np.ndarray]]:
        """
        Read one frame from sub stream.
        Updates last_frame_ts and FPS counter on success.
        """
        with self._sub_lock:
            if self._sub_cap is None:
                return False, None
            ret, frame = self._sub_cap.read()

        if ret and frame is not None:
            now = time.time()
            self.last_frame_ts  = now
            self._fps_cnt      += 1
            # Update FPS every 5 seconds
            if now - self._fps_t >= 5.0:
                self.sub_fps    = self._fps_cnt / (now - self._fps_t)
                self._fps_cnt   = 0
                self._fps_t     = now
            # Update LiveView
            self._update_liveview(frame)

        return ret, frame

    def needs_reconnect(self) -> bool:
        """True when watchdog timeout exceeded."""
        return time.time() - self.last_frame_ts > WATCHDOG_TIMEOUT

    def reconnect_sub(self) -> bool:
        """Release sub stream, wait, then re-open. Returns True on success."""
        log.warning("[Stream] %s watchdog triggered — reconnecting sub stream",
                    self.camera_id)
        with self._sub_lock:
            if self._sub_cap:
                self._sub_cap.release()
            self._sub_cap = None
        self.sub_online = False
        time.sleep(RECONNECT_DELAY)
        ok = self.open_sub()
        if ok:
            self.reconnect_count += 1
            log.info("[Stream] %s reconnected (total reconnects: %d)",
                     self.camera_id, self.reconnect_count)
        return ok

    # ── Main stream (on-demand snapshot) ──────────────────────────────────

    def grab_main_frame(self) -> Optional[np.ndarray]:
        """
        Open main stream, skip buffered frames, grab ONE frame, close.
        Always use with care — takes ~1-3 seconds.
        Never call from hot loop; only on best-frame flush.
        """
        with self._main_lock:
            self.main_online = True
            try:
                cap = cv2.VideoCapture(self.main_url)
                if not cap.isOpened():
                    log.warning("[Stream] %s main stream open failed", self.camera_id)
                    return None
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                # Drain stale buffer frames
                for _ in range(MAIN_SKIP_FRAMES):
                    cap.grab()

                ret, frame = cap.read()
                cap.release()

                if ret and frame is not None:
                    log.debug("[Stream] %s main stream snapshot grabbed (%dx%d)",
                              self.camera_id, frame.shape[1], frame.shape[0])
                    return frame
                return None
            except Exception as exc:
                log.error("[Stream] %s main stream grab error: %s", self.camera_id, exc)
                return None
            finally:
                self.main_online = False

    # ── LiveView ───────────────────────────────────────────────────────────

    def _update_liveview(self, frame: np.ndarray) -> None:
        """Resize and JPEG-encode the latest sub-stream frame for LiveView."""
        try:
            thumb = cv2.resize(frame, (LIVEVIEW_W, LIVEVIEW_H),
                               interpolation=cv2.INTER_LINEAR)
            _, buf = cv2.imencode(".jpg", thumb,
                                  [cv2.IMWRITE_JPEG_QUALITY, 65])
            with self._lv_lock:
                self._liveview_jpeg = buf.tobytes()
        except Exception:
            pass

    def get_liveview_jpeg(self) -> Optional[bytes]:
        """Return latest LiveView JPEG (sub stream, 640×360). Thread-safe."""
        with self._lv_lock:
            return self._liveview_jpeg

    # ── Release ────────────────────────────────────────────────────────────

    def release(self) -> None:
        with self._sub_lock:
            if self._sub_cap:
                self._sub_cap.release()
            self._sub_cap = None
        self.sub_online = False
        log.info("[Stream] %s released", self.camera_id)

    # ── Stats (for dashboard + fleet heartbeat) ────────────────────────────

    def stats(self) -> dict:
        return {
            "camera_id":       self.camera_id,
            "sub_online":      self.sub_online,
            "main_online":     self.main_online,
            "reconnect_count": self.reconnect_count,
            "last_frame_age":  round(time.time() - self.last_frame_ts, 2),
            "fps":             round(self.sub_fps, 1),
            "sub_url_safe":    self._safe_url(self.sub_url),
            "main_url_safe":   self._safe_url(self.main_url),
        }

    @staticmethod
    def _safe_url(url: str) -> str:
        """Mask password in URL — safe for logs and API responses."""
        import re
        return re.sub(r"(rtsp://[^:]+:)[^@]+(@)", r"\1***\2", str(url))


# ─── Multi-camera registry ────────────────────────────────────────────────────

class StreamRegistry:
    """
    Manages DualStreamCapture instances for all configured cameras.
    Provides a global lookup by camera_id.
    """

    def __init__(self) -> None:
        self._streams: dict[str, DualStreamCapture] = {}
        self._lock    = threading.Lock()

    def register(self, camera_id: str, sub_url: str, main_url: str) -> DualStreamCapture:
        ds = DualStreamCapture(camera_id, sub_url, main_url)
        with self._lock:
            self._streams[camera_id] = ds
        return ds

    def get(self, camera_id: str) -> Optional[DualStreamCapture]:
        with self._lock:
            return self._streams.get(camera_id)

    def all_stats(self) -> list[dict]:
        with self._lock:
            return [s.stats() for s in self._streams.values()]

    def release_all(self) -> None:
        with self._lock:
            for s in self._streams.values():
                s.release()


# Module-level singleton — imported by api_server.py for /cameras/status
stream_registry = StreamRegistry()
