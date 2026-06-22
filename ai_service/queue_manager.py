"""
queue_manager.py — Edge Priority Queue Manager (Part 3)
========================================================

Provides offline-first detection delivery:
  - SQLite-backed persistence (survives process restarts / power outages)
  - Priority order: BLACKLIST=1 > ANOMALY=2 > STAFF=3 > VISITOR=4
  - Exponential backoff retry (up to MAX_RETRIES attempts)
  - Background sender thread

Usage:
    def my_sender(payload: dict) -> bool:
        # Return True on success, False to retry
        resp = requests.post(url, json=payload, timeout=5)
        return resp.status_code == 200

    qm = QueueManager(send_fn=my_sender)
    qm.start()
    qm.enqueue(payload, priority=Priority.BLACKLIST)
"""

from __future__ import annotations
import os
import json
import time
import sqlite3
import threading
from enum import IntEnum
from pathlib import Path
from typing import Callable, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
QUEUE_DB_PATH  = Path(os.getenv("QUEUE_DB",          "queue.db"))
MAX_RETRIES    = int(os.getenv("QUEUE_MAX_RETRIES",  "10"))
RETRY_BASE_SEC = float(os.getenv("QUEUE_RETRY_BASE", "5.0"))
RETRY_MAX_SEC  = float(os.getenv("QUEUE_RETRY_MAX",  "300.0"))
FLUSH_BATCH    = int(os.getenv("QUEUE_FLUSH_BATCH",  "10"))


class Priority(IntEnum):
    BLACKLIST = 1
    ANOMALY   = 2
    STAFF     = 3
    VISITOR   = 4


# ─────────────────────────────────────────────────────────────────────────────
# QueueManager
# ─────────────────────────────────────────────────────────────────────────────
class QueueManager:
    """
    SQLite-backed priority queue for offline-first detection delivery.

    The background sender thread reads items ordered by (priority ASC, id ASC)
    and calls send_fn(payload). On success, the item is deleted. On failure,
    it is re-queued with exponential backoff. After MAX_RETRIES failures,
    the item is discarded (logged as dead-letter).
    """

    def __init__(self, send_fn: Callable[[dict], bool]):
        self._send_fn = send_fn
        self._conn    = self._init_db()
        self._lock    = threading.Lock()
        self._wake    = threading.Event()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ── Enqueue ───────────────────────────────────────────────────────────────

    def enqueue(
        self,
        payload:  dict,
        priority: Priority = Priority.VISITOR,
    ):
        """Add a payload to the queue. Thread-safe."""
        with self._lock:
            self._conn.execute(
                """INSERT INTO queue (priority, payload, retries, next_attempt, created_at)
                   VALUES (?, ?, 0, ?, ?)""",
                (int(priority), json.dumps(payload, ensure_ascii=False), time.time(), time.time()),
            )
            self._conn.commit()
        self._wake.set()

    # ── Stats ─────────────────────────────────────────────────────────────────

    def qsize(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM queue").fetchone()
            return int(row[0]) if row else 0

    def pending_by_priority(self) -> dict:
        with self._lock:
            rows = self._conn.execute(
                "SELECT priority, COUNT(*) as cnt FROM queue GROUP BY priority"
            ).fetchall()
        pmap = {1: "blacklist", 2: "anomaly", 3: "staff", 4: "visitor"}
        return {pmap.get(r[0], str(r[0])): r[1] for r in rows}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._sender_loop, daemon=True, name="queue-sender"
        )
        self._thread.start()

    def stop(self):
        self._running = False
        self._wake.set()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _sender_loop(self):
        while self._running:
            self._wake.wait(timeout=5.0)
            self._wake.clear()
            try:
                self._flush()
            except Exception as e:
                print(f"[QueueManager] Flush error: {e}")

    def _flush(self):
        now = time.time()
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, priority, payload, retries
                   FROM queue
                   WHERE next_attempt <= ?
                   ORDER BY priority ASC, id ASC
                   LIMIT ?""",
                (now, FLUSH_BATCH),
            ).fetchall()

        for row_id, _prio, payload_str, retries in rows:
            try:
                payload = json.loads(payload_str)
                ok      = self._send_fn(payload)
            except Exception as exc:
                print(f"[QueueManager] send_fn error: {exc}")
                ok = False

            with self._lock:
                if ok:
                    self._conn.execute("DELETE FROM queue WHERE id = ?", (row_id,))
                else:
                    new_retries  = retries + 1
                    backoff      = min(RETRY_BASE_SEC * (2 ** retries), RETRY_MAX_SEC)
                    next_attempt = time.time() + backoff

                    if new_retries >= MAX_RETRIES:
                        # Dead-letter: move to failed_queue, delete from queue
                        try:
                            self._conn.execute(
                                """INSERT INTO failed_queue (priority, payload, retries, created_at)
                                   VALUES (?, ?, ?, ?)""",
                                (_prio, payload_str, new_retries, time.time()),
                            )
                        except Exception:
                            pass
                        self._conn.execute("DELETE FROM queue WHERE id = ?", (row_id,))
                        print(f"[QueueManager] Dead-letter after {new_retries} retries (id={row_id})")
                    else:
                        self._conn.execute(
                            "UPDATE queue SET retries = ?, next_attempt = ? WHERE id = ?",
                            (new_retries, next_attempt, row_id),
                        )
                self._conn.commit()

    def _init_db(self) -> sqlite3.Connection:
        QUEUE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(QUEUE_DB_PATH), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                priority     INTEGER NOT NULL DEFAULT 4,
                payload      TEXT    NOT NULL,
                retries      INTEGER NOT NULL DEFAULT 0,
                next_attempt REAL    NOT NULL,
                created_at   REAL    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS failed_queue (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                priority   INTEGER NOT NULL,
                payload    TEXT    NOT NULL,
                retries    INTEGER NOT NULL,
                created_at REAL    NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_q_prio ON queue(priority ASC, id ASC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_q_next ON queue(next_attempt ASC)"
        )
        conn.commit()
        return conn
