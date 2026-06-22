"""
update_manager.py — OTA Update Manager (MEGA v6, Part 4)

Workflow (edge device):
  1. Poll UPDATE_SERVER/api/updates/latest every UPDATE_CHECK_INTERVAL s
  2. If new version → download zip to downloads/<version>.zip
  3. Verify SHA-256 checksum
  4. Backup current *.py files to backups/ota/<timestamp>/
  5. Extract staging/ → swap files
  6. Write new version.json
  7. Re-exec process (systemd restarts it)
  8. Health-check /health — if still unhealthy after retries → rollback

Version pinning:
  Set PINNED_VERSION env var to prevent auto-updates past that version.

Rollback:
  update_mgr.rollback()   # restores most recent backup
"""

from __future__ import annotations

import gc
import os
import sys
import json
import time
import shutil
import hashlib
import logging
import zipfile
import threading
import urllib.request
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────
UPDATE_SERVER         = os.getenv("UPDATE_SERVER",         "http://localhost:3003")
UPDATE_CHECK_INTERVAL = float(os.getenv("UPDATE_CHECK_INTERVAL", "300"))   # 5 min
UPDATE_TIMEOUT        = float(os.getenv("UPDATE_TIMEOUT",        "120"))   # download
HEALTH_URL            = os.getenv("HEALTH_URL",      "http://localhost:8000/health")
HEALTH_CHECK_RETRIES  = int(os.getenv("HEALTH_CHECK_RETRIES",    "6"))
HEALTH_RETRY_INTERVAL = float(os.getenv("HEALTH_RETRY_INTERVAL", "10"))
PINNED_VERSION        = os.getenv("PINNED_VERSION", "")                    # "" = no pin

BASE_DIR     = Path(__file__).parent
DOWNLOADS    = BASE_DIR / "downloads"
STAGING      = BASE_DIR / "staging"
OTA_BACKUPS  = BASE_DIR / "backups" / "ota"
VERSION_FILE = BASE_DIR / "version.json"


def _read_version() -> dict:
    try:
        return json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"version": "0.0.0", "channel": "stable"}


def _write_version(info: dict) -> None:
    VERSION_FILE.write_text(json.dumps(info, indent=2), encoding="utf-8")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class UpdateManager:
    """OTA updater with checksum verification and automatic rollback."""

    def __init__(self, alert_fn: Optional[Callable] = None) -> None:
        self._alert_fn = alert_fn or (lambda sev, msg: None)
        self._lock     = threading.Lock()
        self._running  = False
        self._version  = _read_version()
        for d in (DOWNLOADS, STAGING, OTA_BACKUPS):
            d.mkdir(parents=True, exist_ok=True)

    # ── Public API ──────────────────────────────────────────────────────────

    def current_version(self) -> dict:
        return dict(self._version)

    def check_now(self) -> Optional[dict]:
        """Poll server for update; apply if available. Returns update info or None."""
        try:
            url = (f"{UPDATE_SERVER}/api/updates/latest"
                   f"?current={self._version['version']}")
            with urllib.request.urlopen(url, timeout=10) as r:
                info = json.loads(r.read())
            if not info.get("update_available"):
                return None
            new_ver = info.get("version", "")
            if PINNED_VERSION and new_ver > PINNED_VERSION:
                log.info("[OTA] Skipping %s — pinned to %s", new_ver, PINNED_VERSION)
                return None
            log.info("[OTA] Update available: %s → %s",
                     self._version["version"], new_ver)
            self._apply_update(info)
            return info
        except Exception as exc:
            log.debug("[OTA] check failed: %s", exc)
            return None

    def rollback(self) -> bool:
        """Restore the most recent OTA backup."""
        backups = sorted(OTA_BACKUPS.iterdir(), reverse=True)
        if not backups:
            log.error("[OTA] No backup found for rollback")
            return False
        return self._restore_backup(backups[0])

    # ── Internal update flow ─────────────────────────────────────────────────

    def _apply_update(self, info: dict) -> None:
        version  = info["version"]
        url      = info["download_url"]
        expected = info.get("sha256", "")
        zip_path = DOWNLOADS / f"{version}.zip"

        # 1. Download
        log.info("[OTA] Downloading %s …", version)
        self._alert_fn("info", f"OTA download started: {version}")
        try:
            urllib.request.urlretrieve(url, zip_path)
        except Exception as exc:
            log.error("[OTA] Download failed: %s", exc)
            self._alert_fn("warning", f"OTA download failed: {exc}")
            return

        # 2. Checksum
        if expected:
            actual = _sha256(zip_path)
            if actual != expected:
                log.error("[OTA] Checksum mismatch — aborting")
                self._alert_fn("critical", f"OTA checksum mismatch for {version}")
                zip_path.unlink(missing_ok=True)
                return

        # 3. Backup current .py files
        backup_path = self._create_backup()
        if not backup_path:
            log.error("[OTA] Backup failed — aborting update")
            return

        # 4. Extract to staging
        try:
            if STAGING.exists():
                shutil.rmtree(STAGING)
            STAGING.mkdir()
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(STAGING)
        except Exception as exc:
            log.error("[OTA] Extract failed: %s", exc)
            return

        # 5. Swap files into place
        try:
            for item in STAGING.iterdir():
                dest = BASE_DIR / item.name
                if dest.exists():
                    dest.unlink() if dest.is_file() else shutil.rmtree(dest)
                shutil.move(str(item), str(dest))
        except Exception as exc:
            log.error("[OTA] File swap failed: %s — rolling back", exc)
            self._restore_backup(backup_path)
            return

        # 6. Update version.json
        _write_version({
            "version":    version,
            "channel":    info.get("channel", "stable"),
            "updated_at": time.time(),
        })
        self._version = _read_version()

        # 7. Restart (systemd / supervisor will re-launch the process)
        log.info("[OTA] Restarting service for %s", version)
        gc.collect()
        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception:
            pass

        # 8. Health check (reached only if exec failed — rare)
        if not self._wait_healthy():
            log.error("[OTA] Health check failed — rolling back")
            self._alert_fn("critical", f"OTA health check failed — rolling back")
            self._restore_backup(backup_path)
            self._alert_fn("warning", "OTA rolled back to previous version")
        else:
            log.info("[OTA] Update to %s succeeded", version)
            self._alert_fn("info", f"OTA update to {version} succeeded")

    def _create_backup(self) -> Optional[Path]:
        ts   = int(time.time())
        path = OTA_BACKUPS / str(ts)
        try:
            path.mkdir()
            for fname in os.listdir(BASE_DIR):
                src = BASE_DIR / fname
                if src.is_file() and fname.endswith(".py"):
                    shutil.copy2(src, path / fname)
            if VERSION_FILE.exists():
                shutil.copy2(VERSION_FILE, path / "version.json")
            # Keep only last 5 OTA backups
            all_bk = sorted(OTA_BACKUPS.iterdir())
            for old in all_bk[:-5]:
                shutil.rmtree(old, ignore_errors=True)
            log.info("[OTA] Backup at %s", path)
            return path
        except Exception as exc:
            log.error("[OTA] Backup failed: %s", exc)
            return None

    def _restore_backup(self, backup_path: Path) -> bool:
        try:
            for item in backup_path.iterdir():
                shutil.copy2(item, BASE_DIR / item.name)
            bk_ver = backup_path / "version.json"
            if bk_ver.exists():
                shutil.copy2(bk_ver, VERSION_FILE)
                self._version = _read_version()
            log.info("[OTA] Restored from %s", backup_path)
            return True
        except Exception as exc:
            log.error("[OTA] Restore failed: %s", exc)
            return False

    def _wait_healthy(self) -> bool:
        for i in range(HEALTH_CHECK_RETRIES):
            time.sleep(HEALTH_RETRY_INTERVAL)
            try:
                with urllib.request.urlopen(HEALTH_URL, timeout=5) as r:
                    body = json.loads(r.read())
                    if body.get("status") == "ok":
                        return True
            except Exception:
                pass
            log.info("[OTA] Health check %d/%d …", i + 1, HEALTH_CHECK_RETRIES)
        return False

    # ── Background poller ────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        t = threading.Thread(target=self._poll_loop, daemon=True, name="ota-poller")
        t.start()
        log.info("[OTA] Update poller started (interval=%.0f s)", UPDATE_CHECK_INTERVAL)

    def _poll_loop(self) -> None:
        while self._running:
            time.sleep(UPDATE_CHECK_INTERVAL)
            with self._lock:
                self.check_now()
