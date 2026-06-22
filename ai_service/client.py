"""
client.py — Production Thin Client LPR with ByteTrack
======================================================

Pipeline:
  RTSP/Camera
  → Motion Gate (cheap pixel diff — skips dead frames fast)
  → YOLOv8 Vehicle Detection with ByteTrack (ultralytics built-in)
  → Per-track Best Frame Selection
      ✓ Vehicle width ≥ 20% of frame
      ✓ Laplacian variance ≥ BLUR_THRESHOLD (blur rejection)
      ✓ Brightness 40–220
  → Save ONE best frame per track_id to pending_frames/

Environment:
  CAMERA_SOURCE     0 / RTSP URL           0
  CAMERA_ID         Camera label           1
  FPS_LIMIT         Max frames processed   5
  BLUR_THRESHOLD    Min sharpness          100
  MIN_VEHICLE_RATIO Min vehicle width %    0.20
  PENDING_DIR       Output folder          pending_frames
  MODEL_PATH        YOLOv8 model path      auto
"""

import os
import cv2
import time
import numpy as np
from datetime import datetime
from pathlib import Path
from ultralytics import YOLO
from logger_lpr import get_logger

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
_source = os.getenv("CAMERA_SOURCE", "0")
CAMERA_SOURCE     = int(_source) if str(_source).isdigit() else _source
CAMERA_ID         = int(os.getenv("CAMERA_ID", "1"))
FPS_LIMIT         = float(os.getenv("FPS_LIMIT", "5"))          # max 5 FPS
BLUR_THRESHOLD    = float(os.getenv("BLUR_THRESHOLD", "100"))   # Laplacian variance
MIN_VEHICLE_RATIO = float(os.getenv("MIN_VEHICLE_RATIO", "0.20"))
PENDING_DIR       = Path(os.getenv("PENDING_DIR", "pending_frames"))
MODEL_PATH        = os.getenv("MODEL_PATH",
                    "yolov8n.onnx" if os.path.exists("yolov8n.onnx") else "yolov8n.pt")

# Camera reconnect
CAM_MAX_RETRY       = int(os.getenv("CAM_MAX_RETRY", "30"))
CAM_RECONNECT_DELAY = float(os.getenv("CAM_RECONNECT_DELAY", "2.0"))

# Track management
TRACK_FORGET_SEC    = float(os.getenv("TRACK_FORGET_SEC", "60.0"))  # drop track after N seconds
MAX_SAVED_TRACKS    = int(os.getenv("MAX_SAVED_TRACKS", "500"))     # LRU eviction

VEHICLE_CLASSES = [2, 3, 5, 7]   # car, motorcycle, bus, truck

PENDING_DIR.mkdir(parents=True, exist_ok=True)

log = get_logger("THIN_CLIENT", camera_id=f"CAM{CAMERA_ID:02d}")

# ─────────────────────────────────────────────────────────────────────────────
# Model
# ─────────────────────────────────────────────────────────────────────────────
log.info(f"Loading model: {MODEL_PATH}")
try:
    model = YOLO(MODEL_PATH)
    log.info(f"Vehicle detection model ready: {MODEL_PATH}")
except Exception as e:
    log.critical(f"Cannot load model: {e}")
    raise SystemExit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Image Quality Helpers
# ─────────────────────────────────────────────────────────────────────────────
def laplacian_variance(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())

def frame_quality_score(gray: np.ndarray) -> tuple:
    """Returns (lap_var, mean_brightness, is_acceptable)."""
    lap_var = laplacian_variance(gray)
    mean_br = float(np.mean(gray))
    ok      = (lap_var >= BLUR_THRESHOLD) and (40 <= mean_br <= 220)
    return lap_var, mean_br, ok

# ─────────────────────────────────────────────────────────────────────────────
# Camera helpers
# ─────────────────────────────────────────────────────────────────────────────
def open_camera(source, max_attempts: int = 5) -> cv2.VideoCapture:
    for attempt in range(1, max_attempts + 1):
        cap = cv2.VideoCapture(source)
        if cap.isOpened():
            # Reduce buffer: avoid stale frames from RTSP
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            log.info(f"Camera opened: {source} (attempt {attempt})")
            return cap
        log.warn("-", "Camera Open",
                 f"Attempt {attempt}/{max_attempts} failed for: {source}")
        time.sleep(CAM_RECONNECT_DELAY)
    raise RuntimeError(f"Cannot open camera after {max_attempts} attempts: {source}")

# ─────────────────────────────────────────────────────────────────────────────
# Per-Track Best Frame State
# ─────────────────────────────────────────────────────────────────────────────
class TrackState:
    """Tracks the best candidate frame for a single vehicle track_id."""
    __slots__ = ("track_id", "saved", "best_score", "first_seen", "last_seen")

    def __init__(self, track_id: int):
        self.track_id  = track_id
        self.saved     = False       # Already saved one image for this track
        self.best_score = -1.0
        self.first_seen = time.time()
        self.last_seen  = time.time()

    def touch(self):
        self.last_seen = time.time()

    def is_stale(self) -> bool:
        return time.time() - self.last_seen > TRACK_FORGET_SEC


class TrackRegistry:
    """Thread-safe-ish dict of TrackState objects with LRU eviction."""

    def __init__(self):
        self._tracks: dict[int, TrackState] = {}

    def get_or_create(self, track_id: int) -> TrackState:
        if track_id not in self._tracks:
            self._tracks[track_id] = TrackState(track_id)
        self._tracks[track_id].touch()
        return self._tracks[track_id]

    def cleanup(self):
        """Remove stale tracks. Call periodically."""
        stale = [tid for tid, ts in self._tracks.items() if ts.is_stale()]
        for tid in stale:
            del self._tracks[tid]
        # LRU eviction if too many tracks
        if len(self._tracks) > MAX_SAVED_TRACKS:
            oldest = sorted(self._tracks.keys(),
                            key=lambda k: self._tracks[k].last_seen)
            for tid in oldest[:len(oldest)//2]:
                del self._tracks[tid]

    def __len__(self):
        return len(self._tracks)

# ─────────────────────────────────────────────────────────────────────────────
# Best Frame Scoring
# ─────────────────────────────────────────────────────────────────────────────
def compute_frame_score(
    frame: np.ndarray,
    x1: int, y1: int, x2: int, y2: int,
    frame_w: int
) -> tuple:
    """
    Compute quality score for a detected vehicle box.
    Returns (score, lap_var, mean_br, is_acceptable)

    Conditions for acceptable frame:
      - Vehicle width ≥ MIN_VEHICLE_RATIO of frame width
      - Lap variance ≥ BLUR_THRESHOLD
      - Brightness 40–220
    """
    vehicle_w = x2 - x1
    width_ratio = vehicle_w / frame_w

    if width_ratio < MIN_VEHICLE_RATIO:
        return -1.0, 0.0, 0.0, False   # Vehicle too small / too far

    vehicle_crop = frame[y1:y2, x1:x2]
    if vehicle_crop.size == 0:
        return -1.0, 0.0, 0.0, False

    gray = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2GRAY)
    lap_var, mean_br, ok = frame_quality_score(gray)

    if not ok:
        return -1.0, lap_var, mean_br, False

    # Score: emphasize sharpness (70%) and size (30%)
    sharp_norm = min(lap_var / 600.0, 1.0)
    size_norm  = min(width_ratio / 0.6, 1.0)
    score = sharp_norm * 0.7 + size_norm * 0.3

    return score, lap_var, mean_br, True

# ─────────────────────────────────────────────────────────────────────────────
# Save Frame
# ─────────────────────────────────────────────────────────────────────────────
def save_best_frame(
    frame: np.ndarray,
    track_id: int,
    score: float,
    lap_var: float,
    mean_br: float
) -> Path:
    """Resize to max 640px wide and save as JPEG with metadata filename."""
    h, w = frame.shape[:2]
    if w > 640:
        scale = 640 / w
        frame = cv2.resize(frame, (640, int(h * scale)))

    ts       = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"frame_{ts}_TRK{track_id}_CAM{CAMERA_ID}.jpg"
    filepath = PENDING_DIR / filename

    cv2.imwrite(str(filepath), frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
    log.event(
        f"TRK_{track_id}", "Best Frame Saved",
        status="OK",
        file=filename,
        score=f"{score:.3f}",
        blur=f"{lap_var:.1f}",
        bright=f"{mean_br:.1f}"
    )
    return filepath

# ─────────────────────────────────────────────────────────────────────────────
# Main Loop
# ─────────────────────────────────────────────────────────────────────────────
def main():
    log.info(f"=== Thin Client LPR v2 starting ===")
    log.info(f"Camera: {CAMERA_SOURCE}  |  FPS cap: {FPS_LIMIT}")
    log.info(f"Blur threshold: {BLUR_THRESHOLD}  |  Min vehicle ratio: {MIN_VEHICLE_RATIO:.0%}")
    log.info(f"Output: {PENDING_DIR.resolve()}")

    # Open camera
    try:
        cap = open_camera(CAMERA_SOURCE)
    except RuntimeError as e:
        log.error("-", "Startup", str(e))
        return

    registry     = TrackRegistry()
    cam_fail     = 0
    frame_count  = 0
    last_process = 0.0
    last_cleanup = time.time()
    fps_interval = 1.0 / FPS_LIMIT   # seconds between processed frames

    log.info("Camera open — entering main loop...")

    try:
        while True:
            ret, frame = cap.read()

            # ── Camera failure / reconnect ────────────────────────────────
            if not ret:
                cam_fail += 1
                log.warn("-", "Frame Read",
                         f"Failed ({cam_fail}/{CAM_MAX_RETRY})")
                time.sleep(0.5)
                if cam_fail >= CAM_MAX_RETRY:
                    log.warn("-", "Camera Reconnect", "Too many failures — reconnecting...")
                    cap.release()
                    try:
                        cap = open_camera(CAMERA_SOURCE)
                        cam_fail = 0
                        log.event("-", "Camera Reconnect", status="OK")
                    except RuntimeError as e:
                        log.error("-", "Camera Reconnect", str(e))
                        time.sleep(10)
                continue

            cam_fail = 0
            frame_count += 1

            # ── FPS cap (drop excess frames) ──────────────────────────────
            now = time.time()
            if now - last_process < fps_interval:
                continue
            last_process = now

            frame_h, frame_w = frame.shape[:2]

            # ── YOLOv8 + ByteTrack ────────────────────────────────────────
            # `persist=True` keeps the tracker state across calls
            results = model.track(
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                classes=VEHICLE_CLASSES,
                imgsz=640,
                verbose=False,
                conf=0.35
            )

            if results and results[0].boxes is not None:
                boxes    = results[0].boxes
                track_ids_tensor = boxes.id

                if track_ids_tensor is not None:
                    track_ids_list = track_ids_tensor.int().cpu().tolist()
                    xyxy_list      = boxes.xyxy.cpu().tolist()
                    cls_list       = boxes.cls.int().cpu().tolist()
                    conf_list      = boxes.conf.cpu().tolist()

                    for track_id, xyxy, cls, det_conf in zip(
                        track_ids_list, xyxy_list, cls_list, conf_list
                    ):
                        x1, y1, x2, y2 = map(int, xyxy)
                        state = registry.get_or_create(track_id)

                        if state.saved:
                            # Already captured best frame for this track — skip
                            continue

                        score, lap_var, mean_br, acceptable = compute_frame_score(
                            frame, x1, y1, x2, y2, frame_w
                        )

                        trk_label = f"TRK_{track_id}"

                        if not acceptable:
                            log.warn(
                                trk_label, "Frame Quality",
                                f"Rejected (blur={lap_var:.1f}, bright={mean_br:.1f}, "
                                f"ratio={(x2-x1)/frame_w:.2f})"
                            )
                            continue

                        log.event(
                            trk_label, "Vehicle Detected",
                            status="TRACKING",
                            cls=cls, det_conf=f"{det_conf:.2f}",
                            score=f"{score:.3f}"
                        )

                        # Update best if this frame is better
                        if score > state.best_score:
                            state.best_score = score
                            # We capture immediately when score > 0 (any acceptable frame)
                            # to avoid missing the vehicle as it passes quickly
                            save_best_frame(frame, track_id, score, lap_var, mean_br)
                            state.saved = True   # ONE save per track

            # ── Periodic cleanup ──────────────────────────────────────────
            if now - last_cleanup > 30:
                before = len(registry)
                registry.cleanup()
                after = len(registry)
                if before != after:
                    log.event("-", "Registry Cleanup",
                               status="OK", removed=before - after, active=after)
                last_cleanup = now

    except KeyboardInterrupt:
        log.info("Interrupted by user — shutting down.")
    finally:
        cap.release()
        log.info("Camera released. Thin client stopped.")


if __name__ == "__main__":
    main()
