"""
backup_service.py — Daily Backup Service (MEGA v6, Part 12)

Creates a zip archive daily at BACKUP_HOUR (default 02:00 local time).

Archive contents:
  database.sqlite         — backend SQLite DB
  config_store.json       — remote config overrides
  profiles/               — calibration JSON presets
  logs/                   — evidence images (7-day window only)

Retention: BACKUP_RETENTION_DAYS (default 7).

Usage:
    backup = BackupService(alert_fn=lambda sev, msg: ...)
    backup.start()      # schedules nightly run
    backup.run_now()    # immediate backup
"""

from __future__ import annotations

import os
import time
import shutil
import logging
import zipfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────
BACKUP_DIR       = Path(os.getenv("BACKUP_DIR",            "backups/daily"))
BACKUP_RETENTION = int(os.getenv("BACKUP_RETENTION_DAYS",  "7"))
BACKUP_HOUR      = int(os.getenv("BACKUP_HOUR",            "2"))   # 02:00 local
BASE_DIR         = Path(__file__).parent

_SOURCES = [
    # (path relative to BASE_DIR,   archive entry name)
    ("../backend/database.sqlite",  "database.sqlite"),
    ("config_store.json",           "config_store.json"),
    ("correction_cache.json",       "correction_cache.json"),
    ("profiles/",                   "profiles/"),
]

_LOGS_DIR = BASE_DIR / ".." / "backend" / "logs"


class BackupService:
    """Nightly backup with retention management."""

    def __init__(self, alert_fn: Optional[Callable] = None) -> None:
        self._alert_fn = alert_fn or (lambda sev, msg: None)
        self._running  = False
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # ── Public API ──────────────────────────────────────────────────────────

    def run_now(self) -> Optional[str]:
        """Run a backup immediately. Returns zip path or None on failure."""
        tag      = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = BACKUP_DIR / f"backup_{tag}.zip"
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                self._add_sources(zf)
                self._add_logs(zf)
            size_mb = zip_path.stat().st_size / 1_048_576
            log.info("[Backup] Created %s (%.1f MB)", zip_path.name, size_mb)
            self._alert_fn("info", f"Backup completed: {zip_path.name} ({size_mb:.1f} MB)")
            self._prune_old()
            return str(zip_path)
        except Exception as exc:
            log.error("[Backup] Failed: %s", exc)
            self._alert_fn("warning", f"Backup failed: {exc}")
            zip_path.unlink(missing_ok=True)
            return None

    def list_backups(self) -> list:
        result = []
        for f in sorted(BACKUP_DIR.glob("backup_*.zip"), reverse=True):
            stat = f.stat()
            result.append({
                "name":       f.name,
                "path":       str(f),
                "size_mb":    round(stat.st_size / 1_048_576, 2),
                "created_at": stat.st_mtime,
            })
        return result

    def restore(self, backup_name: str, dest_dir: Optional[Path] = None) -> bool:
        """Extract a backup to dest_dir (default: BASE_DIR/restore/)."""
        zip_path = BACKUP_DIR / backup_name
        if not zip_path.exists():
            log.error("[Backup] %s not found", backup_name)
            return False
        dest = dest_dir or (BASE_DIR / "restore")
        dest.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(dest)
            log.info("[Backup] Restored %s → %s", backup_name, dest)
            return True
        except Exception as exc:
            log.error("[Backup] Restore failed: %s", exc)
            return False

    # ── Internal ─────────────────────────────────────────────────────────────

    def _add_sources(self, zf: zipfile.ZipFile) -> None:
        for rel_path, arc_name in _SOURCES:
            src = (BASE_DIR / rel_path).resolve()
            if not src.exists():
                continue
            if src.is_dir():
                for item in src.rglob("*"):
                    if item.is_file():
                        zf.write(item, arc_name + item.relative_to(src).as_posix())
            else:
                zf.write(src, arc_name)

    def _add_logs(self, zf: zipfile.ZipFile) -> None:
        if not _LOGS_DIR.exists():
            return
        cutoff = datetime.now() - timedelta(days=7)
        for item in _LOGS_DIR.rglob("*"):
            if not item.is_file():
                continue
            if datetime.fromtimestamp(item.stat().st_mtime) < cutoff:
                continue
            arc = "logs/" + item.relative_to(_LOGS_DIR).as_posix()
            try:
                zf.write(item, arc)
            except Exception:
                pass  # file in use — skip

    def _prune_old(self) -> None:
        cutoff  = datetime.now() - timedelta(days=BACKUP_RETENTION)
        removed = 0
        for f in BACKUP_DIR.glob("backup_*.zip"):
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                removed += 1
        if removed:
            log.info("[Backup] Pruned %d old backups (retention=%d days)",
                     removed, BACKUP_RETENTION)

    # ── Scheduler ────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        t = threading.Thread(target=self._scheduler, daemon=True, name="backup-scheduler")
        t.start()
        log.info("[Backup] Scheduler started (daily %02d:00, retention=%d days)",
                 BACKUP_HOUR, BACKUP_RETENTION)

    def _scheduler(self) -> None:
        while self._running:
            now  = datetime.now()
            next_ = now.replace(hour=BACKUP_HOUR, minute=0, second=0, microsecond=0)
            if next_ <= now:
                # Next fire is tomorrow
                next_ = next_.replace(day=now.day + 1) if now.day < 28 else (
                    next_ + timedelta(days=1)
                )
            sleep_sec = (next_ - datetime.now()).total_seconds()
            log.info("[Backup] Next backup in %.0f min", sleep_sec / 60)
            time.sleep(max(sleep_sec, 1))
            self.run_now()
