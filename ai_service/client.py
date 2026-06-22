"""
client.py — Production ANPR Orchestrator v6
============================================

Orchestrates all Phase-4 + Phase-5 + Phase-6/7 modules:

  Phase 4:  adaptive_fps, quality_engine, direction_engine, window_manager,
            track_manager, pipeline_metrics, health_monitor
  Phase 5:  auto_calibration, camera_diagnostics, alert_center, self_healing
  Phase 6:  fleet_manager (via api_server heartbeat)
  Phase 7:  Hikvision dual-stream (sub for detection, main for OCR snapshots)
            camera_config    → reads cameras.json (no hardcoded URLs)
            stream_manager   → DualStreamCapture + watchdog

Dual-Stream Architecture:
  Sub Stream (Channels/102): always open, low-res
    → YOLOv8 + ByteTrack, LiveView, diagnostics
  Main Stream (Channels/101): on-demand only
    → one snapshot when Best Frame Window is full → saved for OCR

Environment variables:
  CAMERA_SOURCE        Fallback if cameras.json missing   0 / RTSP URL
  CAMERA_ID            Camera label integer                1
  HIKVISION_USERNAME   Hikvision admin username            admin
  HIKVISION_PASSWORD   Hikvision admin password
  HIKVISION_IP         Hikvision NVR/DVR IP                192.168.1.50
  HIKVISION_PORT       RTSP port                           554
  PENDING_DIR          Frame output folder                 pending_frames
  MODEL_PATH           YOLOv8 model path                   auto-detect
  WATCHDOG_TIMEOUT     No-frame reconnect (sec)            5.0
  VIRTUAL_LINE_Y       Virtual line position               0.5
  MIN_QUALITY_SCORE    Quality gate (0-100)                75
  TRACK_FORGET_SEC     Stale track timeout                 30.0
  CAM_MAX_RETRY        Max consecutive frame fails         30
  CAM_RECONNECT_DELAY  Seconds between retries             2.0
  HEALTH_PORT          /health endpoint port               8880
  DIAG_INTERVAL        Camera diagnostics check (sec)      10.0
"""

import os
import cv2
import time
import json
import numpy as np
from datetime import datetime
from pathlib import Path

from ultralytics import YOLO
from logger_lpr import get_logger

from adaptive_fps       import AdaptiveFPSEngine
from quality_engine     import compute as compute_quality
from direction_engine   import DirectionEngine
from window_manager     import WindowManager
from track_manager      import TrackManager
from pipeline_metrics   import PipelineMetrics
from health_monitor     import HealthMonitor
from auto_calibration   import AutoCalibration
from camera_diagnostics import CameraDiagnostics
from alert_center       import AlertCenter
from self_healing       import SelfHealing

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
_source             = os.getenv("CAMERA_SOURCE", "0")
CAMERA_SOURCE       = int(_source) if str(_source).isdigit() else _source
CAMERA_ID           = int(os.getenv("CAMERA_ID", "1"))
PENDING_DIR         = Path(os.getenv("PENDING_DIR", "pending_frames"))
MODEL_PATH          = os.getenv("MODEL_PATH",
                      "yolov8n.onnx" if os.path.exists("yolov8n.onnx") else "yolov8n.pt")
WATCHDOG_TIMEOUT    = float(os.getenv("WATCHDOG_TIMEOUT", "5.0"))
VIRTUAL_LINE_Y      = float(os.getenv("VIRTUAL_LINE_Y", "0.5"))
MIN_QUALITY_SCORE   = float(os.getenv("MIN_QUALITY_SCORE", "75"))
TRACK_FORGET_SEC    = float(os.getenv("TRACK_FORGET_SEC", "30.0"))
CAM_MAX_RETRY       = int(os.getenv("CAM_MAX_RETRY", "30"))
CAM_RECONNECT_DELAY = float(os.getenv("CAM_RECONNECT_DELAY", "2.0"))
HEALTH_PORT         = int(os.getenv("HEALTH_PORT", "8880"))
DIAG_INTERVAL       = float(os.getenv("DIAG_INTERVAL", "10.0"))  # camera diagnostics period

VEHICLE_CLASSES = [2, 3, 5, 7]   # car, motorcycle, bus, truck

PENDING_DIR.mkdir(parents=True, exist_ok=True)
log = get_logger("CLIENT", camera_id=f"CAM{CAMERA_ID:02d}")


# ─────────────────────────────────────────────────────────────────────────────
# Model
# ─────────────────────────────────────────────────────────────────────────────
log.info(f"Loading model: {MODEL_PATH}")
try:
    model = YOLO(MODEL_PATH)
    log.info(f"Vehicle detection model ready: {MODEL_PATH}")
except Exception as _e:
    log.critical(f"Cannot load model: {_e}")
    raise SystemExit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Module instances
# ─────────────────────────────────────────────────────────────────────────────
fps_engine    = AdaptiveFPSEngine()
direction_eng = DirectionEngine(line_y_ratio=VIRTUAL_LINE_Y)
window_mgr    = WindowManager()
track_mgr     = TrackManager(forget_sec=TRACK_FORGET_SEC)
pm            = PipelineMetrics()
health        = HealthMonitor(
    camera_ids=[str(CAMERA_ID)],
    port=HEALTH_PORT,
)

# Phase-5 modules
calibrator  = AutoCalibration()     # auto-adjusts quality/blur/fps thresholds
camera_diag = CameraDiagnostics()   # dirty lens, rain, camera shift detection
alerts      = AlertCenter()         # INFO/WARNING/CRITICAL routing
healer      = SelfHealing(
    alert_fn=lambda sev, msg: alerts.emit(sev, "self_healing", msg)
)


# ─────────────────────────────────────────────────────────────────────────────
# Camera helpers
# ─────────────────────────────────────────────────────────────────────────────
def open_camera(source, max_attempts: int = 5) -> cv2.VideoCapture:
    for attempt in range(1, max_attempts + 1):
        cap = cv2.VideoCapture(source)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            log.info(f"Camera opened: {source} (attempt {attempt})")
            health.set_camera_status(str(CAMERA_ID), "ok")
            alerts.info("camera", f"Camera connected: {source}")
            return cap
        log.warn("-", "Camera Open", f"Attempt {attempt}/{max_attempts} failed: {source}")
        health.set_camera_status(str(CAMERA_ID), "reconnecting")
        alerts.warning("camera", f"Camera open failed (attempt {attempt}/{max_attempts}): {source}")
        time.sleep(CAM_RECONNECT_DELAY)
    health.set_camera_status(str(CAMERA_ID), "lost")
    alerts.critical("camera", f"Camera lost after {max_attempts} attempts: {source}")
    raise RuntimeError(f"Cannot open camera after {max_attempts} attempts: {source}")


# ─────────────────────────────────────────────────────────────────────────────
# Frame save + sidecar JSON
# ─────────────────────────────────────────────────────────────────────────────
def save_frame(
    frame:       np.ndarray,
    track_id:    int,
    score:       float,
    components:  dict,
    frame_index: int,
    direction:   str,
) -> Path:
    h, w = frame.shape[:2]
    if w > 640:
        scale = 640 / w
        frame = cv2.resize(frame, (640, int(h * scale)))

    ts   = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    stem = f"frame_{ts}_TRK{track_id:03d}_F{frame_index}_CAM{CAMERA_ID}"
    jpg  = PENDING_DIR / f"{stem}.jpg"
    meta = PENDING_DIR / f"{stem}.json"

    cv2.imwrite(str(jpg), frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
    meta.write_text(json.dumps({
        "track_id":   f"TRK_{track_id:03d}",
        "camera_id":  CAMERA_ID,
        "direction":  direction,
        "quality":    score,
        "frame_idx":  frame_index,
        "components": components,
        "timestamp":  datetime.now().isoformat(),
    }, ensure_ascii=False))

    log.event(
        f"TRK_{track_id:03d}", "Frame Saved",
        status="OK", file=jpg.name,
        score=f"{score:.1f}", dir=direction, idx=frame_index,
    )
    return jpg


# ─────────────────────────────────────────────────────────────────────────────
# Flush Best Frame Window → pending_frames/
# ─────────────────────────────────────────────────────────────────────────────
def flush_window(state) -> int:
    """
    Save all candidates from the Best Frame Window to pending_frames/.
    Returns number of frames saved.
    """
    if not state.candidates or state.saved:
        return 0

    ranked = sorted(state.candidates, key=lambda c: c.score, reverse=True)
    trk    = state.track_id

    log.event(
        f"TRK_{trk:03d}", "Best Frame Selected",
        status=f"{len(ranked)} frames",
        best_score=f"{ranked[0].score:.1f}",
        dir=state.direction,
    )
    pm.inc("best_frame_selected")

    for i, candidate in enumerate(ranked):
        save_frame(
            frame=candidate.frame,
            track_id=trk,
            score=candidate.score,
            components=candidate.components,
            frame_index=i + 1,
            direction=state.direction,
        )

    state.candidates.clear()
    state.saved = True
    return len(ranked)


# ─────────────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────────────
def main():
    log.info("=== ANPR Orchestrator v5 — Enterprise Edge Platform ===")
    log.info(f"Camera: {CAMERA_SOURCE}  |  Min quality: {MIN_QUALITY_SCORE}/100 (auto-calibrated)")
    log.info(f"Adaptive FPS: {fps_engine.FPS_IDLE}/{fps_engine.FPS_DETECTED}/{fps_engine.FPS_TRACKING} (idle/vehicle/tracking)")
    log.info(f"RTSP watchdog: {WATCHDOG_TIMEOUT}s  |  Virtual line: {VIRTUAL_LINE_Y:.0%}")
    log.info(f"Output: {PENDING_DIR.resolve()}")

    # Start Phase-5 background services
    calibrator.start()
    healer.start()
    health.start(pipeline_metrics_ref=pm)

    try:
        cap = open_camera(CAMERA_SOURCE)
    except RuntimeError as e:
        log.error("-", "Startup", str(e))
        alerts.critical("startup", str(e))
        return

    cam_fail        = 0
    frame_count     = 0
    last_process    = 0.0
    last_cleanup    = time.time()
    last_frame_time = time.time()
    last_diag       = time.time()   # Camera diagnostics timer

    # FPS measurement
    fps_measure_t   = time.time()
    fps_measure_cnt = 0

    log.info("Camera open — entering main loop...")

    try:
        while True:
            ret, frame = cap.read()

            # ── RTSP Watchdog ──────────────────────────────────────────────────
            if not ret:
                cam_fail += 1
                elapsed   = time.time() - last_frame_time
                log.warn("-", "Frame Read",
                         f"Failed ({cam_fail}), {elapsed:.1f}s since last good frame")
                health.set_camera_status(str(CAMERA_ID), "reconnecting")
                time.sleep(0.3)

                if elapsed >= WATCHDOG_TIMEOUT or cam_fail >= CAM_MAX_RETRY:
                    log.warn("-", "RTSP Watchdog",
                             f"No frame for {elapsed:.1f}s — reconnecting...")
                    cap.release()
                    try:
                        cap             = open_camera(CAMERA_SOURCE)
                        cam_fail        = 0
                        last_frame_time = time.time()
                        log.event("-", "Camera Reconnect", status="OK")
                    except RuntimeError as e:
                        log.error("-", "Camera Reconnect", str(e))
                        time.sleep(10)
                continue

            cam_fail        = 0
            last_frame_time = time.time()
            frame_count    += 1

            # ── Adaptive FPS Cap ───────────────────────────────────────────────
            now      = time.time()
            interval = fps_engine.get_interval()
            if now - last_process < interval:
                continue
            last_process = now

            # Measure actual FPS
            fps_measure_cnt += 1
            if now - fps_measure_t >= 5.0:
                actual_fps = fps_measure_cnt / (now - fps_measure_t)
                health.set_fps(actual_fps)
                fps_measure_cnt = 0
                fps_measure_t   = now

            frame_h, frame_w = frame.shape[:2]

            # ── Camera Diagnostics (every DIAG_INTERVAL seconds) ──────────────
            if now - last_diag >= DIAG_INTERVAL:
                diag = camera_diag.update(frame)
                last_diag = now
                if diag.status == "CRITICAL":
                    alerts.critical("camera_diag", diag.recommendation,
                                    {"camera_id": CAMERA_ID})
                elif diag.status == "WARNING":
                    alerts.warning("camera_diag", diag.recommendation,
                                   {"camera_id": CAMERA_ID})

            # ── YOLOv8 + ByteTrack ────────────────────────────────────────────
            results = model.track(
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                classes=VEHICLE_CLASSES,
                imgsz=640,
                verbose=False,
                conf=0.35,
            )

            active_ids: set[int] = set()

            if results and results[0].boxes is not None:
                boxes  = results[0].boxes
                ids_t  = boxes.id

                if ids_t is not None:
                    ids   = ids_t.int().cpu().tolist()
                    xyxys = boxes.xyxy.cpu().tolist()
                    clss  = boxes.cls.int().cpu().tolist()
                    confs = boxes.conf.cpu().tolist()

                    for track_id, xyxy, cls, det_conf in zip(ids, xyxys, clss, confs):
                        active_ids.add(track_id)
                        x1, y1, x2, y2 = map(int, xyxy)
                        state = track_mgr.get_or_create(track_id)
                        pm.inc("vehicle_seen")

                        if state.saved:
                            continue

                        # ── Direction Detection ───────────────────────────────
                        cx = (x1 + x2) / 2.0
                        cy = (y1 + y2) / 2.0
                        detected_dir = direction_eng.update(track_id, cx, cy, frame_h)
                        if detected_dir:
                            state.direction = detected_dir

                        # ── Speed for dynamic window size ──────────────────────
                        window_mgr.update_centroid(track_id, cx, cy)
                        window_size = window_mgr.get_window_size_for_track(track_id)

                        trk_label = f"TRK_{track_id:03d}"

                        # ── 6-Component Quality Score (calibrated thresholds) ──
                        qr = compute_quality(frame, x1, y1, x2, y2)

                        # Feed metrics to auto-calibration engine
                        calibrator.record_frame(
                            blur=qr.components.get("lap_var", 0.0),
                            brightness=qr.components.get("mean_brightness", 128.0),
                            quality=qr.score,
                            speed=window_mgr.get_speed(track_id),
                        )

                        # Collect rejection reasons for metrics
                        if qr.components.get("reflection_status") == "reject":
                            pm.inc("rejected_reflection")
                        elif qr.components.get("lap_var", 9999) < calibrator.blur_threshold:
                            pm.inc("rejected_blur")

                        # Use calibrated quality threshold (overrides env var)
                        effective_quality_gate = calibrator.quality_threshold
                        if not qr.acceptable or qr.score < effective_quality_gate:
                            log.warn(trk_label, "Quality Gate",
                                     f"Rejected score={qr.score:.1f} "
                                     f"(gate={effective_quality_gate:.0f}) "
                                     f"blur={qr.components.get('lap_var', 0):.0f} "
                                     f"refl={qr.components.get('reflection_status', '?')}")
                            continue

                        log.event(trk_label, "Vehicle Detected",
                                  status="CANDIDATE",
                                  score=f"{qr.score:.1f}",
                                  cls=cls, conf=f"{det_conf:.2f}",
                                  window=window_size,
                                  dir=state.direction)

                        # ── Best Frame Window ─────────────────────────────────
                        state.add_candidate(frame, qr.score, qr.components, window_size)

                        if state.is_window_full(window_size):
                            flush_window(state)

            # ── Update Adaptive FPS engine ─────────────────────────────────────
            fps_engine.update(len(active_ids))
            window_mgr.cleanup_all(active_ids)

            # ── Periodic cleanup — flush stale/lost tracks ─────────────────────
            if now - last_cleanup > 10.0:
                removed = track_mgr.cleanup()
                direction_eng.cleanup_stale()

                for s in removed:
                    if not s.saved and s.candidates:
                        s.direction = direction_eng.infer_direction(s.track_id)
                        flush_window(s)
                    direction_eng.cleanup(s.track_id)
                    window_mgr.cleanup(s.track_id)

                health.set_queue_size(len(list(PENDING_DIR.glob("*.jpg"))))

                if removed:
                    log.event("-", "Registry Cleanup",
                              status="OK",
                              removed=len(removed),
                              active=track_mgr.active_count())
                last_cleanup = now

    except KeyboardInterrupt:
        log.info("Interrupted by user — shutting down.")
    finally:
        cap.release()
        log.info("Camera released. Orchestrator stopped.")
        log.info(f"Final pipeline metrics: {pm.summary()}")


if __name__ == "__main__":
    main()
