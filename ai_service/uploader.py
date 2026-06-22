"""
uploader.py — Background Frame Uploader v3
===========================================

Watches pending_frames/ for JPEG files.
Reads sidecar .json metadata (written by client.py) to include:
  - track_id, camera_id, direction, quality_score, frame_idx
as HTTP headers sent to ai_server.

Deletes JPEG + sidecar JSON immediately after server confirms receipt (HTTP 200).
Implements exponential backoff on network errors.

Environment:
  API_URL          AI Server URL     http://100.127.92.120/api/plate/ai/detect_frame
  API_KEY          Shared key        PLATE-AI-KEY-totacademy-2026
  PENDING_DIR      Watch folder      pending_frames
  CAMERA_ID        Camera label      1
"""

import os
import json
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
CAMERA_ID   = int(os.getenv("CAMERA_ID", "1"))

PENDING_DIR.mkdir(parents=True, exist_ok=True)
log = get_logger("UPLOADER", camera_id=f"CAM{CAMERA_ID:02d}")

# Backoff config
MAX_RETRIES      = 5
BASE_DELAY_SEC   = 1.0
MAX_DELAY_SEC    = 60.0
INTER_FILE_WAIT  = 0.3    # Brief pause between files to avoid flooding

# ─────────────────────────────────────────────────────────────────────────────
# Filename fallback parser (if sidecar JSON is missing)
# ─────────────────────────────────────────────────────────────────────────────
_TRK_RE = re.compile(r"TRK(\d+)", re.IGNORECASE)
_CAM_RE = re.compile(r"CAM(\d+)", re.IGNORECASE)
_FRM_RE = re.compile(r"_F(\d+)_", re.IGNORECASE)

def extract_metadata_from_filename(filename: str) -> dict:
    trk_m = _TRK_RE.search(filename)
    cam_m = _CAM_RE.search(filename)
    frm_m = _FRM_RE.search(filename)
    return {
        "track_id":  f"TRK_{trk_m.group(1)}" if trk_m else "TRK_unknown",
        "camera_id": int(cam_m.group(1)) if cam_m else CAMERA_ID,
        "frame_idx": int(frm_m.group(1)) if frm_m else 1,
        "direction": "IN",
        "quality":   0.0,
    }

def load_metadata(jpg_path: Path) -> dict:
    """Load sidecar JSON written by client.py; fall back to filename parsing."""
    meta_path = jpg_path.with_suffix(".json")
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return extract_metadata_from_filename(jpg_path.name)

# ─────────────────────────────────────────────────────────────────────────────
# Upload one file
# ─────────────────────────────────────────────────────────────────────────────
def upload_file(filepath: Path) -> bool:
    """
    Upload a single JPEG + metadata to the AI server.
    Returns True  → delete the file (success or permanent rejection).
    Returns False → keep the file, retry later (transient server error).
    """
    meta = load_metadata(filepath)
    track_id  = meta.get("track_id", "TRK_unknown")
    camera_id = meta.get("camera_id", CAMERA_ID)
    direction = meta.get("direction", "IN")
    quality   = meta.get("quality",   0.0)
    frame_idx = meta.get("frame_idx", 1)

    with open(filepath, "rb") as f:
        file_data = f.read()

    files   = {"file": (filepath.name, file_data, "image/jpeg")}
    headers = {
        "X-API-Key":       API_KEY,
        "X-Track-Id":      str(track_id),
        "X-Camera-Id":     str(camera_id),
        "X-Direction":     str(direction),
        "X-Quality-Score": f"{quality:.2f}",
        "X-Frame-Index":   str(frame_idx),
    }

    log.event(track_id, "Uploading Frame",
              status="START",
              file=filepath.name,
              dir=direction,
              quality=f"{quality:.1f}",
              size_kb=f"{len(file_data) / 1024:.1f}")

    t0  = time.perf_counter()
    res = requests.post(API_URL, files=files, headers=headers, timeout=30.0)
    ms  = int((time.perf_counter() - t0) * 1000)

    if res.status_code == 200:
        data       = res.json()
        detections = data.get("detections", [])
        for det in detections:
            log.event(track_id, "Server Detection",
                      status=det.get("status", ""),
                      plate=det.get("plate", "—"),
                      conf=f"{det.get('confidence', 0):.2f}")

        log.event(track_id, "Upload Success",
                  status="DELETED",
                  file=filepath.name,
                  detections=len(detections),
                  latency_ms=ms)
        return True

    elif res.status_code in (400, 422):
        log.warn(track_id, "Upload Rejected",
                 f"HTTP {res.status_code} — deleting bad file: {filepath.name}")
        return True   # Delete — server won't accept it on retry

    else:
        log.warn(track_id, "Upload Error",
                 f"HTTP {res.status_code} — will retry: {filepath.name}")
        return False  # Keep for retry


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup sidecar JSON
# ─────────────────────────────────────────────────────────────────────────────
def delete_sidecar(jpg_path: Path):
    meta_path = jpg_path.with_suffix(".json")
    try:
        meta_path.unlink(missing_ok=True)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Main upload loop
# ─────────────────────────────────────────────────────────────────────────────
def upload_loop():
    log.info("=== Uploader v3 starting ===")
    log.info(f"Watch: {PENDING_DIR.resolve()}")
    log.info(f"Target: {API_URL}")

    network_fail_count = 0

    while True:
        try:
            # Process oldest files first (filename has timestamp prefix)
            files = sorted(PENDING_DIR.glob("*.jpg"))

            if not files:
                time.sleep(0.8)
                network_fail_count = 0
                continue

            for filepath in files:
                if not filepath.exists():
                    continue   # Race: already deleted

                delay   = BASE_DELAY_SEC
                success = False

                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        should_delete = upload_file(filepath)
                        if should_delete:
                            try:
                                filepath.unlink()
                                delete_sidecar(filepath)
                            except FileNotFoundError:
                                pass
                            network_fail_count = 0
                            success = True
                            break
                        else:
                            if attempt < MAX_RETRIES:
                                log.warn("—", "Retry",
                                         f"Attempt {attempt}/{MAX_RETRIES} — waiting {delay:.1f}s")
                                time.sleep(delay)
                                delay = min(delay * 2, MAX_DELAY_SEC)

                    except requests.exceptions.RequestException as e:
                        network_fail_count += 1
                        if attempt < MAX_RETRIES:
                            log.warn("—", "Network Error",
                                     f"{e} — attempt {attempt}/{MAX_RETRIES} — waiting {delay:.1f}s")
                            time.sleep(delay)
                            delay = min(delay * 2, MAX_DELAY_SEC)
                        else:
                            log.error("—", "Network Error",
                                      f"Max retries reached: {e}. File kept.")

                if not success:
                    time.sleep(min(network_fail_count * 2, MAX_DELAY_SEC))
                else:
                    time.sleep(INTER_FILE_WAIT)

        except Exception as e:
            log.error("-", "Uploader Loop", str(e))
            time.sleep(5)


if __name__ == "__main__":
    upload_loop()
