"""
logger_lpr.py — Shared Structured Logger for LPR Services

Format: [Timestamp] [CAM_ID] [TRK_id] [Step] [Status] [Extra]

Usage:
    from logger_lpr import get_logger
    log = get_logger("CLIENT", camera_id="CAM01")
    log.event("TRK_321", "Vehicle Detected", status="OK", conf=0.92)
"""

import logging
import os
from datetime import datetime

# ─────────────────────────────────────────────
# File paths
# ─────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

SYSTEM_LOG_PATH = os.path.join(LOG_DIR, "system.log")
LPR_LOG_PATH    = os.path.join(LOG_DIR, "lpr.log")


class StructuredFormatter(logging.Formatter):
    """Multi-line structured log: one event = 4–6 lines for readability."""

    def format(self, record):
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        camera   = getattr(record, "camera",   "SYS")
        track_id = getattr(record, "track_id", "-")
        step     = getattr(record, "step",     record.getMessage())
        status   = getattr(record, "status",   "")
        extra    = getattr(record, "extra",     "")

        lines = [
            f"[{ts}]",
            f"  {camera}",
            f"  {track_id}",
            f"  {step}",
        ]
        if status:
            lines.append(f"  → {status}")
        if extra:
            lines.append(f"  {extra}")
        lines.append("")   # blank separator
        return "\n".join(lines)


class LPRLogger:
    """Thin wrapper that adds structured fields to every log call."""

    def __init__(self, service_name: str, camera_id: str = "CAM01"):
        self.camera    = camera_id
        self._service  = service_name
        self._raw      = logging.getLogger(f"lpr.{service_name}")

        if not self._raw.handlers:
            # Console handler (plain one-liner)
            ch = logging.StreamHandler()
            ch.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s][%(name)s] %(message)s",
                datefmt="%H:%M:%S"
            ))
            # File handler (structured multi-line)
            fh = logging.FileHandler(SYSTEM_LOG_PATH, encoding="utf-8")
            fh.setFormatter(StructuredFormatter())

            lpr_fh = logging.FileHandler(LPR_LOG_PATH, encoding="utf-8")
            lpr_fh.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s"
            ))

            self._raw.addHandler(ch)
            self._raw.addHandler(fh)
            self._raw.addHandler(lpr_fh)
            self._raw.setLevel(logging.DEBUG)
            self._raw.propagate = False

    def _make_extra(self, track_id: str, step: str, status: str, extra_str: str):
        return {
            "camera":   self.camera,
            "track_id": track_id,
            "step":     step,
            "status":   status,
            "extra":    extra_str,
        }

    def event(self, track_id: str, step: str, status: str = "", **kwargs):
        """Log a pipeline event."""
        extra_parts = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        extra = self._make_extra(track_id, step, status, extra_parts)
        msg = f"[{track_id}] {step}" + (f" → {status}" if status else "")
        if extra_parts:
            msg += f" | {extra_parts}"
        self._raw.info(msg, extra=extra)

    def warn(self, track_id: str, step: str, reason: str = "", **kwargs):
        extra_parts = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        extra = self._make_extra(track_id, step, "WARN", f"{reason} {extra_parts}".strip())
        msg = f"[{track_id}] {step} ⚠ {reason}"
        if extra_parts:
            msg += f" | {extra_parts}"
        self._raw.warning(msg, extra=extra)

    def error(self, track_id: str, step: str, reason: str = "", **kwargs):
        extra_parts = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        extra = self._make_extra(track_id, step, "ERROR", f"{reason} {extra_parts}".strip())
        self._raw.error(f"[{track_id}] {step} ✗ {reason}", extra=extra)

    def debug(self, msg: str):
        self._raw.debug(msg)

    def info(self, msg: str):
        self._raw.info(msg)

    def critical(self, msg: str):
        self._raw.critical(msg)


def get_logger(service_name: str, camera_id: str = "CAM01") -> LPRLogger:
    return LPRLogger(service_name, camera_id)
