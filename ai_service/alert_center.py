"""
alert_center.py — Enterprise Alert Center (Part 12)
=====================================================

Collects, deduplicates, and routes alerts from all system components.

Alert levels:  INFO  |  WARNING  |  CRITICAL
Alert sources: camera, ai_worker, queue, disk, memory, ocr, network

Deduplication:
    Same (level + source + message) within DEDUP_SEC is suppressed.

Output channels:
    1. Structured print / logger
    2. In-memory history (queryable via recent())
    3. Optional webhook (ALERT_WEBHOOK_URL env var)
    4. Registered Python handlers (add_handler)

Usage:
    alerts = AlertCenter()
    alerts.warning("camera", "Camera disconnected", {"camera_id": 1})
    alerts.critical("disk",  "Disk 96% full")
    recent = alerts.recent(n=20, level="CRITICAL")
"""

from __future__ import annotations
import os
import time
import threading
from collections import deque
from typing import Callable, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
DEDUP_SEC   = int(os.getenv("ALERT_DEDUP_SEC",   "60"))
MAX_HISTORY = int(os.getenv("ALERT_HISTORY_MAX", "500"))
WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL",      "")

VALID_LEVELS = ("INFO", "WARNING", "CRITICAL")


# ─────────────────────────────────────────────────────────────────────────────
# Alert dataclass (slot-optimized)
# ─────────────────────────────────────────────────────────────────────────────
class Alert:
    __slots__ = ("ts", "level", "source", "message", "data")

    def __init__(
        self,
        level:   str,
        source:  str,
        message: str,
        data:    Optional[dict] = None,
    ):
        self.ts      = time.time()
        self.level   = level
        self.source  = source
        self.message = message
        self.data    = data or {}

    def to_dict(self) -> dict:
        return {
            "ts":      self.ts,
            "level":   self.level,
            "source":  self.source,
            "message": self.message,
            "data":    self.data,
        }

    def __str__(self) -> str:
        return f"[{self.level}] {self.source}: {self.message}"


# ─────────────────────────────────────────────────────────────────────────────
# AlertCenter
# ─────────────────────────────────────────────────────────────────────────────
class AlertCenter:
    """
    Centralized alert routing with deduplication and pluggable handlers.

    Thread-safe: all public methods can be called from any thread.
    """

    def __init__(self, log_fn: Optional[Callable[[Alert], None]] = None):
        self._lock    = threading.Lock()
        self._history: deque[Alert] = deque(maxlen=MAX_HISTORY)
        self._dedup:   dict[str, float] = {}    # key → last_emit_time
        self._handlers: list[Callable[[Alert], None]] = []
        self._log_fn  = log_fn or _default_log
        self._counts  = {"INFO": 0, "WARNING": 0, "CRITICAL": 0}

    # ── Handler registration ──────────────────────────────────────────────────

    def add_handler(self, fn: Callable[[Alert], None]):
        """Register an external handler (e.g. Socket.IO emit, Telegram, Slack)."""
        self._handlers.append(fn)

    # ── Emit ─────────────────────────────────────────────────────────────────

    def emit(
        self,
        level:   str,
        source:  str,
        message: str,
        data:    Optional[dict] = None,
    ):
        if level not in VALID_LEVELS:
            return

        dedup_key = f"{level}:{source}:{message}"
        now       = time.time()

        with self._lock:
            last = self._dedup.get(dedup_key)
            if last and (now - last) < DEDUP_SEC:
                return
            self._dedup[dedup_key] = now

        alert = Alert(level, source, message, data)

        with self._lock:
            self._history.append(alert)
            self._counts[level] += 1

        self._log_fn(alert)

        for fn in self._handlers:
            try:
                fn(alert)
            except Exception as e:
                print(f"[AlertCenter] Handler error: {e}")

        if WEBHOOK_URL:
            self._send_webhook(alert)

    def info(self, source: str, message: str, data: Optional[dict] = None):
        self.emit("INFO", source, message, data)

    def warning(self, source: str, message: str, data: Optional[dict] = None):
        self.emit("WARNING", source, message, data)

    def critical(self, source: str, message: str, data: Optional[dict] = None):
        self.emit("CRITICAL", source, message, data)

    # ── History ───────────────────────────────────────────────────────────────

    def recent(self, n: int = 50, level: Optional[str] = None) -> list[dict]:
        with self._lock:
            alerts = list(self._history)
        if level:
            alerts = [a for a in alerts if a.level == level]
        return [a.to_dict() for a in reversed(alerts[-n:])]

    def counts(self) -> dict:
        with self._lock:
            return dict(self._counts)

    def as_dict(self) -> dict:
        return {
            "counts": self.counts(),
            "recent": self.recent(20),
        }

    # ── Webhook ───────────────────────────────────────────────────────────────

    def _send_webhook(self, alert: Alert):
        """Best-effort webhook delivery in a daemon thread."""
        def _post():
            try:
                import requests
                requests.post(WEBHOOK_URL, json=alert.to_dict(), timeout=3)
            except Exception:
                pass

        threading.Thread(target=_post, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Default logger
# ─────────────────────────────────────────────────────────────────────────────
def _default_log(alert: Alert):
    from datetime import datetime
    ts  = datetime.fromtimestamp(alert.ts).strftime("%H:%M:%S")
    tag = {"INFO": "ℹ", "WARNING": "⚠", "CRITICAL": "✖"}.get(alert.level, "?")
    print(f"[{ts}] {tag} ALERT:{alert.level} [{alert.source}] {alert.message}")
