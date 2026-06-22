"""
camera_config.py — Camera Configuration Manager (MEGA v7, Part 17)

Loads cameras.json and generates RTSP URLs from environment variables.
Credentials are NEVER stored in cameras.json — they come from env vars only.

Usage:
    from camera_config import CameraConfig
    cfg = CameraConfig()
    for cam in cfg.enabled_cameras():
        print(cam.sub_url)   # rtsp://admin:***@192.168.1.50:554/...
"""

from __future__ import annotations

import os
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from hikvision_rtsp import build_sub_rtsp, build_main_rtsp, mask_rtsp_url

log = logging.getLogger(__name__)

CONFIG_FILE = Path(os.getenv("CAMERAS_JSON", Path(__file__).parent / "cameras.json"))

# ─── Credentials from environment ────────────────────────────────────────────
# These are NEVER in cameras.json — only in .env / docker env vars
_HKVISION_USER = os.getenv("HIKVISION_USERNAME", "admin")
_HIKVISION_PASS = os.getenv("HIKVISION_PASSWORD", "")
_HIKVISION_IP   = os.getenv("HIKVISION_IP",       "192.168.1.50")
_HIKVISION_PORT = int(os.getenv("HIKVISION_PORT",  "554"))

# Fallback for non-Hikvision / generic RTSP
_CAMERA_SOURCE  = os.getenv("CAMERA_SOURCE", "0")


@dataclass
class CameraEntry:
    camera_id:    str
    name:         str
    vendor:       str
    channel:      int
    use_substream: bool
    enabled:      bool
    notes:        str
    # Generated — not from JSON
    sub_url:      str = field(default="", repr=False)
    main_url:     str = field(default="", repr=False)
    sub_url_safe: str = field(default="", repr=False)   # password masked
    main_url_safe: str = field(default="", repr=False)

    def as_dict(self, include_urls: bool = False) -> dict:
        d = {
            "camera_id":    self.camera_id,
            "name":         self.name,
            "vendor":       self.vendor,
            "channel":      self.channel,
            "use_substream": self.use_substream,
            "enabled":      self.enabled,
            "notes":        self.notes,
        }
        if include_urls:
            d["sub_url_safe"]  = self.sub_url_safe
            d["main_url_safe"] = self.main_url_safe
        return d


class CameraConfig:
    """Loads cameras.json + injects credentials from env vars."""

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self._path    = config_path or CONFIG_FILE
        self._cameras: list[CameraEntry] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            log.warning("[CameraConfig] %s not found — falling back to CAMERA_SOURCE env var",
                        self._path)
            self._cameras = [self._fallback_entry()]
            return

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.error("[CameraConfig] Failed to parse %s: %s — using fallback", self._path, exc)
            self._cameras = [self._fallback_entry()]
            return

        cameras = raw.get("cameras", [])
        entries: list[CameraEntry] = []

        for cam in cameras:
            vendor  = cam.get("vendor", "generic").lower()
            channel = int(cam.get("channel", 1))
            enabled = bool(cam.get("enabled", True))

            if vendor == "hikvision":
                sub_url  = build_sub_rtsp(
                    _HKVISION_USER, _HIKVISION_PASS, _HIKVISION_IP, channel, _HIKVISION_PORT
                )
                main_url = build_main_rtsp(
                    _HKVISION_USER, _HIKVISION_PASS, _HIKVISION_IP, channel, _HIKVISION_PORT
                )
            else:
                # Generic / non-Hikvision: use CAMERA_SOURCE as-is for first cam
                sub_url  = _CAMERA_SOURCE
                main_url = _CAMERA_SOURCE

            entry = CameraEntry(
                camera_id    = cam["camera_id"],
                name         = cam.get("name", cam["camera_id"]),
                vendor       = vendor,
                channel      = channel,
                use_substream = bool(cam.get("use_substream", True)),
                enabled      = enabled,
                notes        = cam.get("notes", ""),
                sub_url      = sub_url,
                main_url     = main_url,
                sub_url_safe = mask_rtsp_url(sub_url),
                main_url_safe = mask_rtsp_url(main_url),
            )
            entries.append(entry)
            log.info("[CameraConfig] Loaded %s (%s ch%d) sub=%s",
                     entry.camera_id, vendor, channel, entry.sub_url_safe)

        self._cameras = entries
        log.info("[CameraConfig] %d camera(s) loaded from %s", len(entries), self._path)

    def _fallback_entry(self) -> CameraEntry:
        """Single-camera fallback using CAMERA_SOURCE env var."""
        src = _CAMERA_SOURCE
        return CameraEntry(
            camera_id    = "CAM01",
            name         = "Default Camera",
            vendor       = "generic",
            channel      = 0,
            use_substream = False,
            enabled      = True,
            notes        = f"Fallback from CAMERA_SOURCE={src}",
            sub_url      = src,
            main_url     = src,
            sub_url_safe = mask_rtsp_url(str(src)) if str(src).startswith("rtsp") else str(src),
            main_url_safe = mask_rtsp_url(str(src)) if str(src).startswith("rtsp") else str(src),
        )

    def all_cameras(self) -> list[CameraEntry]:
        return list(self._cameras)

    def enabled_cameras(self) -> list[CameraEntry]:
        return [c for c in self._cameras if c.enabled]

    def get(self, camera_id: str) -> Optional[CameraEntry]:
        for c in self._cameras:
            if c.camera_id == camera_id:
                return c
        return None

    def reload(self) -> None:
        """Hot-reload cameras.json without restarting."""
        self._load()

    def as_dict_list(self) -> list[dict]:
        return [c.as_dict(include_urls=False) for c in self._cameras]
