"""
self_healing.py — System Self-Healing (Part 4)
===============================================

Monitors system health every HEAL_INTERVAL seconds and takes
corrective action automatically:

    Camera offline       → restart camera capture process
    AI worker crashed    → restart AI subprocess
    Uploader failed      → restart uploader subprocess
    Memory > 85%         → run gc.collect()
    Disk > 85%           → stop saving debug/quality images
    Disk > 95%           → emergency cleanup (delete oldest pending frames)

Usage:
    healer = SelfHealing(alert_fn=alert_center.warning)
    healer.register_process("uploader", ["python", "uploader.py"])
    healer.start()
"""

from __future__ import annotations
import os
import gc
import time
import threading
import subprocess
from pathlib import Path
from typing import Optional, Callable

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
HEAL_INTERVAL    = float(os.getenv("HEAL_INTERVAL",  "30.0"))
MEM_GC_PCT       = float(os.getenv("MEM_GC_PCT",     "85.0"))
MEM_WARN_PCT     = float(os.getenv("MEM_WARN_PCT",   "75.0"))
DISK_PAUSE_PCT   = float(os.getenv("DISK_PAUSE_PCT", "85.0"))
DISK_CLEAN_PCT   = float(os.getenv("DISK_CLEAN_PCT", "95.0"))
PENDING_DIR      = Path(os.getenv("PENDING_DIR",     "pending_frames"))

# Module-level flag read by client.py / api_server to gate debug frame saves
debug_images_enabled: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# ProcessWatcher — manages a single subprocess
# ─────────────────────────────────────────────────────────────────────────────
class ProcessWatcher:
    """Starts and monitors a subprocess; restarts it if it exits."""

    def __init__(self, name: str, cmd: list[str], cwd: Optional[str] = None):
        self.name  = name
        self.cmd   = cmd
        self.cwd   = cwd
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self.restart_count = 0

    def ensure_running(self) -> bool:
        """Return True if process is healthy; False if it was restarted."""
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._do_restart()
                return False
        return True

    def _do_restart(self):
        try:
            if self._proc:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
            self._proc = subprocess.Popen(
                self.cmd,
                cwd=self.cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.restart_count += 1
            print(
                f"[SelfHealing] Restarted '{self.name}' "
                f"(pid={self._proc.pid}, count={self.restart_count})"
            )
        except Exception as e:
            print(f"[SelfHealing] Failed to restart '{self.name}': {e}")

    def stop(self):
        with self._lock:
            if self._proc:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
                self._proc = None


# ─────────────────────────────────────────────────────────────────────────────
# SelfHealing
# ─────────────────────────────────────────────────────────────────────────────
class SelfHealing:
    """
    Background health monitor that takes corrective action automatically.

    register_process() before calling start() to enable subprocess watching.
    alert_fn receives (severity: str, message: str) on each corrective action.
    """

    def __init__(self, alert_fn: Optional[Callable[[str, str], None]] = None):
        self._alert = alert_fn or (lambda sev, msg: print(f"[SelfHealing:{sev}] {msg}"))
        self._watchers: dict[str, ProcessWatcher] = {}
        self._running  = False
        self._thread: Optional[threading.Thread] = None
        self._last_gc  = 0.0
        self._last_clean = 0.0

    # ── Registration ──────────────────────────────────────────────────────────

    def register_process(
        self,
        name: str,
        cmd:  list[str],
        cwd:  Optional[str] = None,
    ):
        self._watchers[name] = ProcessWatcher(name, cmd, cwd)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop, daemon=True, name="self-healing"
        )
        self._thread.start()

    def stop(self):
        self._running = False
        for w in self._watchers.values():
            w.stop()

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            try:
                self._check_memory()
                self._check_disk()
                self._check_processes()
            except Exception as e:
                print(f"[SelfHealing] Check error: {e}")
            time.sleep(HEAL_INTERVAL)

    # ── Memory ────────────────────────────────────────────────────────────────

    def _check_memory(self):
        if not _PSUTIL:
            return
        pct = psutil.virtual_memory().percent
        if pct > MEM_GC_PCT:
            now = time.time()
            if now - self._last_gc > 60:   # GC at most once per minute
                self._alert("WARNING", f"Memory {pct:.0f}% — running gc.collect()")
                gc.collect()
                self._last_gc = now
        elif pct > MEM_WARN_PCT:
            self._alert("INFO", f"Memory at {pct:.0f}%")

    # ── Disk ──────────────────────────────────────────────────────────────────

    def _check_disk(self):
        if not _PSUTIL:
            return
        global debug_images_enabled

        try:
            usage = psutil.disk_usage(str(PENDING_DIR) if PENDING_DIR.exists() else "/")
            pct   = usage.percent
        except Exception:
            return

        if pct > DISK_CLEAN_PCT:
            self._alert("CRITICAL", f"Disk {pct:.0f}% — emergency cleanup")
            self._emergency_cleanup()
        elif pct > DISK_PAUSE_PCT:
            if debug_images_enabled:
                self._alert("WARNING", f"Disk {pct:.0f}% — pausing debug image saves")
                debug_images_enabled = False
        else:
            if not debug_images_enabled:
                debug_images_enabled = True   # Re-enable when disk recovers

    # ── Processes ─────────────────────────────────────────────────────────────

    def _check_processes(self):
        for name, watcher in self._watchers.items():
            if not watcher.ensure_running():
                self._alert(
                    "WARNING",
                    f"Process '{name}' was dead — restarted "
                    f"(total restarts: {watcher.restart_count})",
                )

    # ── Emergency cleanup ─────────────────────────────────────────────────────

    def _emergency_cleanup(self):
        now = time.time()
        if now - self._last_clean < 120:   # At most once per 2 minutes
            return
        self._last_clean = now
        try:
            jpg_files = sorted(
                PENDING_DIR.glob("*.jpg"),
                key=lambda f: f.stat().st_mtime,
            )
            # Delete oldest 50% of pending frames
            cut = len(jpg_files) // 2
            removed = 0
            for f in jpg_files[:cut]:
                try:
                    f.unlink(missing_ok=True)
                    f.with_suffix(".json").unlink(missing_ok=True)
                    removed += 1
                except Exception:
                    pass
            self._alert("WARNING", f"Emergency cleanup removed {removed} frames")
        except Exception as e:
            print(f"[SelfHealing] Emergency cleanup error: {e}")

    # ── Stats ─────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        mem_pct  = psutil.virtual_memory().percent if _PSUTIL else -1
        disk_pct = psutil.disk_usage("/").percent   if _PSUTIL else -1
        procs    = {
            name: ("running" if w._proc and w._proc.poll() is None else "stopped")
            for name, w in self._watchers.items()
        }
        return {
            "memory_percent":       mem_pct,
            "disk_percent":         disk_pct,
            "debug_images_enabled": debug_images_enabled,
            "processes":            procs,
        }
