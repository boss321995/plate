"""
uploader.py — Background Frame Uploader
=========================================

Watches pending_frames/ and uploads JPEG files to AI Server.
Deletes each file IMMEDIATELY after server confirms receipt (HTTP 200).
Implements exponential backoff on network errors.

Environment:
  API_URL     AI Server URL    http://100.127.92.120/api/plate/ai/detect_frame
  API_KEY     Shared key       PLATE-AI-KEY-totacademy-2026
  PENDING_DIR Watch folder     pending_frames
  CAMERA_ID   Camera label     1
  UPLOAD_THREADS  Parallelism  1 (keep 1 for in-order processing)
"""

import os
import glob
import time
import re
import requests
from pathlib import Path
from logger_lpr import get_logger

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
API_URL     = os.getenv("API_URL",  "http://100.127.92.120/api/plate/ai/detect_frame")
API_KEY     = os.getenv("API_KEY",  "PLATE-AI-KEY-totacademy-2026")
PENDING_DIR = Path(os.getenv("PENDING_DIR", "pending_frames"))
CAMERA_ID   = int(os.getenv("CAMERA_ID",  "1"))

PENDING_DIR.mkdir(parents=True, exist_ok=True)

log = get_logger("UPLOADER", camera_id=f"CAM{CAMERA_ID:02d}")

# Backoff config
MAX_RETRIES    = 5
BASE_DELAY_SEC = 1.0      # Initial retry wait
MAX_DELAY_SEC  = 60.0     # Cap backoff at 60s
INTER_FILE_WAIT = 0.3     # Short pause between files to avoid flooding server

# ─────────────────────────────────────────────────────────────────────────────
# Extract track_id from filename (if embedded by client.py)
# Filename pattern: frame_YYYYMMDD_HHMMSS_ffffff_TRKxxx_CAMx.jpg
# ─────────────────────────────────────────────────────────────────────────────
_TRK_RE = re.compile(r"TRK(\d+)", re.IGNORECASE)
_CAM_RE = re.compile(r"CAM(\d+)", re.IGNORECASE)

def extract_metadata(filename: str) -> tuple:
    trk_m = _TRK_RE.search(filename)
    cam_m = _CAM_RE.search(filename)
    track_id  = f"TRK_{trk_m.group(1)}" if trk_m else "TRK_unknown"
    camera_id = int(cam_m.group(1)) if cam_m else CAMERA_ID
    return track_id, camera_id

# ─────────────────────────────────────────────────────────────────────────────
# Upload one file
# ─────────────────────────────────────────────────────────────────────────────
def upload_file(filepath: Path) -> bool:
    """
    Upload a single JPEG to the AI server.
    Returns True if server responded 200 (delete file).
    Returns False on non-retryable errors (server rejection).
    Raises requests.exceptions.RequestException on network errors (caller retries).
    """
    track_id, camera_id = extract_metadata(filepath.name)

    with open(filepath, "rb") as f:
        file_data = f.read()

    files   = {"file": (filepath.name, file_data, "image/jpeg")}
    headers = {
        "X-API-Key":    API_KEY,
        "X-Track-Id":   track_id,
        "X-Camera-Id":  str(camera_id),
    }

    log.event(track_id, "Uploading Frame", status="START",
               file=filepath.name, size_kb=f"{len(file_data)/1024:.1f}")

    t0  = time.perf_counter()
    res = requests.post(API_URL, files=files, headers=headers, timeout=30.0)
    ms  = int((time.perf_counter() - t0) * 1000)

    if res.status_code == 200:
        data       = res.json()
        detections = data.get("detections", [])

        for det in detections:
            plate  = det.get("plate", "—")
            status = det.get("status", "")
            conf   = det.get("confidence", 0.0)
            log.event(track_id, "Server Detection",
                       status=status, plate=plate, conf=f"{conf:.2f}")

        log.event(track_id, "Upload Success",
                   status="DELETED", file=filepath.name,
                   detections=len(detections), latency_ms=ms)
        return True

    elif res.status_code in (400, 422):
        # Bad image / server rejected — don't retry, delete anyway
        log.warn(track_id, "Upload Rejected",
                  f"HTTP {res.status_code} — deleting bad file", file=filepath.name)
        return True   # Signal: delete this file

    else:
        log.warn(track_id, "Upload Error",
                  f"HTTP {res.status_code}", file=filepath.name)
        return False   # Signal: keep file, retry later


# ─────────────────────────────────────────────────────────────────────────────
# Main upload loop
# ─────────────────────────────────────────────────────────────────────────────
def upload_loop():
    log.info("=== Uploader v2 starting ===")
    log.info(f"Watch: {PENDING_DIR.resolve()}")
    log.info(f"Target: {API_URL}")

    network_fail_count = 0

    while True:
        try:
            # Sorted by name = sorted by timestamp (filename has ts prefix)
            files = sorted(PENDING_DIR.glob("*.jpg"))

            if not files:
                time.sleep(0.8)
                network_fail_count = 0   # Reset backoff when idle
                continue

            for filepath in files:
                if not filepath.exists():
                    continue   # Race condition: already deleted

                delay = BASE_DELAY_SEC
                success = False

                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        should_delete = upload_file(filepath)
                        if should_delete:
                            # ── IMMEDIATE DELETE on success or rejection ──
                            try:
                                filepath.unlink()
                            except FileNotFoundError:
                                pass
                            network_fail_count = 0
                            success = True
                            break
                        else:
                            # Server error (5xx) — retry with backoff
                            if attempt < MAX_RETRIES:
                                log.warn("—", "Retry",
                                          f"Attempt {attempt}/{MAX_RETRIES} "
                                          f"— waiting {delay:.1f}s")
                                time.sleep(delay)
                                delay = min(delay * 2, MAX_DELAY_SEC)

                    except requests.exceptions.RequestException as e:
                        network_fail_count += 1
                        if attempt < MAX_RETRIES:
                            log.warn("—", "Network Error",
                                      f"{e} — attempt {attempt}/{MAX_RETRIES} "
                                      f"— waiting {delay:.1f}s")
                            time.sleep(delay)
                            delay = min(delay * 2, MAX_DELAY_SEC)
                        else:
                            log.error("—", "Network Error",
                                       f"Max retries reached: {e}. File kept.")

                if not success:
                    # Pause before trying the next file to avoid flooding
                    time.sleep(min(network_fail_count * 2, MAX_DELAY_SEC))
                else:
                    time.sleep(INTER_FILE_WAIT)

        except Exception as e:
            log.error("-", "Uploader Loop", str(e))
            time.sleep(5)


if __name__ == "__main__":
    upload_loop()
