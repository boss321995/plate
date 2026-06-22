"""
api_server.py — Production AI Server for LPR v4 (FastAPI + PaddleOCR)
=======================================================================

Pipeline per uploaded frame:
  1. Receive frame (multipart) + metadata headers from uploader.py
  2. Vehicle Detection (YOLOv8)
  3. Per-vehicle:
       a. Plate Detection (plate model or fallback crop bottom 30%)
       b. Plate Size Validation  (plate_validator — min 80x25 px)
       c. Reflection Detection   (reflection_detector — rejects ratio > 0.50)
       d. Blur Rejection         (Laplacian variance < BLUR_THRESHOLD → skip)
       e. Enhancement            (CLAHE → Auto-Gamma → Bilateral → Unsharp → Denoise)
       f. Optional SR            (OpenCV DNN ESPCN 2x)
       g. PaddleOCR (PP-OCRv4) on plate crop ONLY
       h. OCR Correction Cache   (correction_cache — auto-learned corrections)
       i. Per-track_id vote buffer (majority vote, MAX_VOTE_FRAMES readings)
       j. Composite confidence = OCR×0.5 + plate_detect×0.3 + quality×0.2
       k. Accept only if composite ≥ MIN_CONFIDENCE
  4. Duplicate Suppression (30s per plate+camera pair)
  5. Send structured JSON to Backend (with direction from client headers)
  6. Delete temp file immediately
  7. No permanent image storage on AI server

New endpoints (Phase 4):
  GET /metrics   — pipeline counters (vehicle_seen → backend_saved)

Environment variables:
  API_URL              Backend URL            http://plate-backend:3003
  API_KEY              Shared API key         PLATE-AI-KEY-totacademy-2026
  ENABLE_SR            Super Resolution       false
  SR_MODEL_PATH        ESPCN model file       ESPCN_x2.pb
  BLUR_THRESHOLD       Laplacian variance     100
  MIN_CONFIDENCE       Accept threshold       0.80
  MAX_VOTE_FRAMES      Vote buffer size       5
  DUPLICATE_COOLDOWN   Dup suppression secs   30
  GLOBAL_COOLDOWN      Seconds between sends  5
"""

import os
import cv2
import uuid
import time
import tempfile
import re
import difflib
import logging

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List, Dict

import numpy as np
import requests
import torch
from torchvision import models, transforms

from fastapi import FastAPI, File, UploadFile, Header, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.gzip import GZipMiddleware
from ultralytics import YOLO

try:
    from paddleocr import PaddleOCR as _PaddleOCR   # type: ignore[import-untyped]
    PaddleOCR = _PaddleOCR
    _PADDLE_AVAILABLE = True
except ImportError:
    PaddleOCR = None          # type: ignore[assignment,misc]
    _PADDLE_AVAILABLE = False
    print(
        "[WARNING] paddleocr not installed — OCR disabled.\n"
        "          Run: pip install paddlepaddle paddleocr"
    )

from logger_lpr import get_logger
import plate_validator
import reflection_detector
from correction_cache   import CorrectionCache
from pipeline_metrics   import PipelineMetrics
from camera_diagnostics import CameraDiagnostics
from ocr_analyzer       import OCRAnalyzer
from alert_center       import AlertCenter
from fleet_manager      import FleetManager
from config_service     import ConfigService
from update_manager     import UpdateManager
from backup_service     import BackupService

# ─────────────────────────────────────────────────────────────────────────────
# App Setup
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Plate AI Server", version="3.0.0")
app.add_middleware(GZipMiddleware, minimum_size=1000)

log     = get_logger("API_SERVER", camera_id="API")
std_log = logging.getLogger("uvicorn.error")

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
API_URL                  = os.getenv("API_URL",  "http://plate-backend:3003")
API_KEY                  = os.getenv("API_KEY",  "PLATE-AI-KEY-totacademy-2026")
ENABLE_SR                = os.getenv("ENABLE_SR", "false").lower() == "true"
SR_MODEL_PATH            = os.getenv("SR_MODEL_PATH", "ESPCN_x2.pb")
BLUR_THRESHOLD           = float(os.getenv("BLUR_THRESHOLD", "100"))
MIN_CONFIDENCE           = float(os.getenv("MIN_CONFIDENCE", "0.80"))
MAX_VOTE_FRAMES          = int(os.getenv("MAX_VOTE_FRAMES", "5"))
PLATE_CONF_THRESHOLD     = float(os.getenv("PLATE_CONF_THRESHOLD", "0.40"))
PROVINCE_CONF_THRESHOLD  = float(os.getenv("PROVINCE_CONF_THRESHOLD", "0.55"))
OCR_CONF_THRESHOLD       = float(os.getenv("OCR_CONF_THRESHOLD", "0.35"))
GLOBAL_COOLDOWN          = int(os.getenv("GLOBAL_COOLDOWN", "5"))
DUPLICATE_COOLDOWN       = int(os.getenv("DUPLICATE_COOLDOWN", "30"))   # Part 9: 30s
DETECT_IMGSZ             = int(os.getenv("DETECT_IMGSZ", "320"))
PLATE_IMGSZ              = int(os.getenv("PLATE_IMGSZ", "160"))

TEMP_DIR = Path(tempfile.gettempdir()) / "lpr_frames"
TEMP_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# Province List
# ─────────────────────────────────────────────────────────────────────────────
THAI_PROVINCES = [
    "กรุงเทพมหานคร","กระบี่","กาญจนบุรี","กาฬสินธุ์","กำแพงเพชร",
    "ขอนแก่น","จันทบุรี","ฉะเชิงเทรา","ชลบุรี","ชัยนาท",
    "ชัยภูมิ","ชุมพร","เชียงราย","เชียงใหม่","ตรัง",
    "ตราด","ตาก","นครนายก","นครปฐม","นครพนม",
    "นครราชสีมา","นครศรีธรรมราช","นครสวรรค์","นนทบุรี","นราธิวาส",
    "น่าน","บึงกาฬ","บุรีรัมย์","ปทุมธานี","ประจวบคีรีขันธ์",
    "ปราจีนบุรี","ปัตตานี","พระนครศรีอยุธยา","พะเยา","พังงา",
    "พัทลุง","พิจิตร","พิษณุโลก","เพชรบุรี","เพชรบูรณ์",
    "แพร่","ภูเก็ต","มหาสารคาม","มุกดาหาร","แม่ฮ่องสอน",
    "ยโสธร","ยะลา","ร้อยเอ็ด","ระนอง","ระยอง",
    "ราชบุรี","ลพบุรี","ลำปาง","ลำพูน","เลย",
    "ศรีสะเกษ","สกลนคร","สงขลา","สตูล","สมุทรปราการ",
    "สมุทรสงคราม","สมุทรสาคร","สระแก้ว","สระบุรี","สิงห์บุรี",
    "สุโขทัย","สุพรรณบุรี","สุราษฎร์ธานี","สุรินทร์","หนองคาย",
    "หนองบัวลำภู","อ่างทอง","อำนาจเจริญ","อุดรธานี","อุตรดิตถ์",
    "อุทัยธานี","อุบลราชธานี",
]

# ─────────────────────────────────────────────────────────────────────────────
# Model Loading
# ─────────────────────────────────────────────────────────────────────────────
log.info("Loading YOLOv8 Vehicle Model...")
vehicle_model_path = "yolov8n.onnx" if os.path.exists("yolov8n.onnx") else "yolov8n.pt"
try:
    vehicle_model = YOLO(vehicle_model_path)
    log.info(f"Vehicle model ready: {vehicle_model_path}")
except Exception as e:
    log.critical(f"Cannot load vehicle model: {e}")
    raise SystemExit(1)

PLATE_MODEL_PATH = "plate_detect.onnx" if os.path.exists("plate_detect.onnx") else "plate_detect.pt"
plate_model = None
if os.path.exists(PLATE_MODEL_PATH):
    try:
        plate_model = YOLO(PLATE_MODEL_PATH)
        log.info(f"Plate model ready: {PLATE_MODEL_PATH}")
    except Exception as e:
        log.warn("-", "Model Load", f"Plate model failed: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Part 6: PaddleOCR (PP-OCRv4, replaces EasyOCR)
# ─────────────────────────────────────────────────────────────────────────────
ocr_reader = None
if _PADDLE_AVAILABLE:
    log.info("Loading PaddleOCR (thai + en)...")
    try:
        ocr_reader = PaddleOCR(
            use_angle_cls=True,
            lang="thai",          # Thai language model (covers Thai + digits)
            use_gpu=False,
            show_log=False,
            enable_mkldnn=False,  # Disable MKL-DNN for compatibility
        )
        log.info("PaddleOCR ready.")
    except Exception as e:
        log.critical(f"Cannot load PaddleOCR: {e}")
        ocr_reader = None
else:
    log.warn("-", "PaddleOCR", "Not installed — OCR endpoint will return empty results")

# ─────────────────────────────────────────────────────────────────────────────
# Super Resolution (Optional)
# ─────────────────────────────────────────────────────────────────────────────
sr_model = None
if ENABLE_SR:
    try:
        sr = cv2.dnn_superres.DnnSuperResImpl_create()
        if os.path.exists(SR_MODEL_PATH):
            sr.readModel(SR_MODEL_PATH)
            sr.setModel("espcn", 2)
            sr_model = sr
            log.info(f"Super Resolution enabled: {SR_MODEL_PATH} (2x)")
        else:
            log.warn("-", "SR Init", f"SR model not found: {SR_MODEL_PATH}")
    except Exception as e:
        log.warn("-", "SR Init", f"SR init failed: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Vehicle Fingerprint (ResNet18)
# ─────────────────────────────────────────────────────────────────────────────
log.info("Loading ResNet18 fingerprint extractor...")
vehicle_feature_extractor = None
_fp_preprocess = None
try:
    _resnet = models.resnet18(weights="IMAGENET1K_V1")
    _resnet.eval()
    vehicle_feature_extractor = torch.nn.Sequential(*list(_resnet.children())[:-1])
    _fp_preprocess = transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    log.info("ResNet18 fingerprint extractor ready.")
except Exception as e:
    log.warn("-", "Fingerprint Init", f"ResNet18 load failed: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Part 7: Per-Track Vote Buffer (Multi Frame OCR Voting)
# ─────────────────────────────────────────────────────────────────────────────
class TrackVoteBuffer:
    """Accumulates OCR results per track_id; returns majority-vote consensus."""

    def __init__(self, max_frames: int = 5, window_sec: float = 30.0):
        self.max_frames = max_frames
        self.window_sec = window_sec
        self._data: Dict[str, list] = {}
        self._last_clean = time.time()

    def add(self, track_id: str, plate: str, province: str,
            ocr_conf: float, composite: float):
        now = time.time()
        if track_id not in self._data:
            self._data[track_id] = []
        self._data[track_id].append((plate, province, ocr_conf, composite, now))
        self._data[track_id] = [
            r for r in self._data[track_id]
            if now - r[4] < self.window_sec
        ][-self.max_frames:]
        self._cleanup_stale(now)

    def get_consensus(self, track_id: str) -> Optional[Tuple[str, str, float, float]]:
        readings = self._data.get(track_id, [])
        if not readings:
            return None
        plates    = [r[0] for r in readings]
        provinces = [r[1] for r in readings if r[1]]
        avg_ocr   = sum(r[2] for r in readings) / len(readings)
        avg_comp  = sum(r[3] for r in readings) / len(readings)
        best_plate    = Counter(plates).most_common(1)[0][0]
        best_province = Counter(provinces).most_common(1)[0][0] if provinces else ""
        return best_plate, best_province, avg_ocr, avg_comp

    def clear_track(self, track_id: str):
        self._data.pop(track_id, None)

    def _cleanup_stale(self, now: float):
        if now - self._last_clean < 60:
            return
        stale = [tid for tid, r in self._data.items()
                 if r and now - r[-1][4] > self.window_sec]
        for tid in stale:
            del self._data[tid]
        self._last_clean = now


track_buffer       = TrackVoteBuffer(max_frames=MAX_VOTE_FRAMES)
sent_cache: Dict[str, float] = {}   # "plate:camera_id" → timestamp
global_last_sent   = 0.0
correction_cache   = CorrectionCache()
api_pm             = PipelineMetrics()   # Server-side pipeline counters

# Phase-5 singletons
camera_diag_store  = CameraDiagnostics()   # most-recent diagnostics (shared across requests)
ocr_analyzer       = OCRAnalyzer()          # OCR performance tracker
api_alerts         = AlertCenter()          # server-side alert routing

# Phase-6 (Fleet / OTA / Config / Backup)
DEVICE_ID   = os.getenv("DEVICE_ID",   "edge-01")
SITE_ID     = os.getenv("SITE_ID",     "default")

fleet_mgr   = FleetManager()
config_svc  = ConfigService()
upd_mgr     = UpdateManager(
    alert_fn=lambda sev, msg: api_alerts.emit(sev, "ota", msg))
backup_svc  = BackupService(
    alert_fn=lambda sev, msg: api_alerts.emit(sev, "backup", msg))


@app.on_event("startup")
async def _startup_fleet() -> None:
    fleet_mgr.start()
    upd_mgr.start()
    backup_svc.start()
    # Self-register this edge device
    import socket
    fleet_mgr.register(DEVICE_ID, {
        "hostname":         socket.gethostname(),
        "site_id":          SITE_ID,
        "camera_count":     1,
        "software_version": "v6.0.0",
    })
    log.info("[Fleet] Self-registered as %s on site %s", DEVICE_ID, SITE_ID)

# ─────────────────────────────────────────────────────────────────────────────
# Utility: Text Cleaning
# ─────────────────────────────────────────────────────────────────────────────
def clean_plate_text(text: str) -> str:
    return re.sub(r'[^ก-ฮ0-9]', '', text)

def clean_for_province(text: str) -> str:
    return re.sub(r'[^ก-๛]', '', text)

def normalize_plate(plate_text: str) -> str:
    normalized = re.sub(r'[\s\-\._]+', '', plate_text)
    return re.sub(r'[^ก-ฮ0-9]', '', normalized)

def match_province(raw_text: str) -> Optional[str]:
    cleaned = clean_for_province(raw_text)
    if len(cleaned) < 3 or any(c.isdigit() for c in raw_text):
        return None
    if cleaned in THAI_PROVINCES:
        return cleaned
    best_match, best_ratio = None, 0.0
    for province in THAI_PROVINCES:
        ratio = difflib.SequenceMatcher(None, cleaned, province).ratio()
        if ratio > best_ratio:
            best_ratio, best_match = ratio, province
    for province in THAI_PROVINCES:
        if len(cleaned) >= 3 and cleaned in province and best_ratio < 0.8:
            best_match, best_ratio = province, 0.85
    return best_match if best_ratio >= 0.5 else None

# ─────────────────────────────────────────────────────────────────────────────
# Image Quality Assessment
# ─────────────────────────────────────────────────────────────────────────────
def laplacian_variance(gray_img: np.ndarray) -> float:
    return float(cv2.Laplacian(gray_img, cv2.CV_64F).var())

def compute_quality_score(img: np.ndarray) -> Tuple[float, float]:
    gray       = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
    lap_var    = laplacian_variance(gray)
    mean_br    = float(np.mean(gray))
    sharp      = min(lap_var / 500.0, 1.0)
    bright     = max(0.0, 1.0 - abs(mean_br - 128.0) / 128.0)
    quality    = sharp * 0.7 + bright * 0.3
    return round(quality, 4), lap_var

def is_low_light(frame: np.ndarray) -> Tuple[bool, float]:
    gray    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean_br = float(cv2.mean(gray)[0])
    return mean_br < 70, mean_br

# ─────────────────────────────────────────────────────────────────────────────
# Low-Light Enhancement
# ─────────────────────────────────────────────────────────────────────────────
def enhance_low_light(frame: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l_enh = clahe.apply(l)
    result = cv2.cvtColor(cv2.merge([l_enh, a, b]), cv2.COLOR_LAB2BGR)
    table  = np.array([(i / 255.0) ** (1.0 / 1.8) * 255 for i in range(256)], dtype=np.uint8)
    result = cv2.LUT(result, table)
    return cv2.fastNlMeansDenoisingColored(result, None, 5, 5, 7, 21)

# ─────────────────────────────────────────────────────────────────────────────
# Part 6: Plate Enhancement Pipeline
# ─────────────────────────────────────────────────────────────────────────────
def enhance_plate_image(plate_bgr: np.ndarray) -> np.ndarray:
    """
    Enhancement steps:
      1. Upscale to min 64px height
      2. Optional Super Resolution (2x)
      3. CLAHE on L-channel
      4. Auto-Gamma Correction
      5. Bilateral Filter
      6. Unsharp Mask
      7. Denoise (fastNlMeansDenoising)
    """
    h, w = plate_bgr.shape[:2]

    # ── 1. Upscale ───────────────────────────────────────────────────────────
    if h < 64:
        scale = 64 / h
        plate_bgr = cv2.resize(plate_bgr, (int(w * scale), 64), interpolation=cv2.INTER_CUBIC)

    # ── 2. Optional Super Resolution ─────────────────────────────────────────
    if sr_model is not None:
        try:
            plate_bgr = sr_model.upsample(plate_bgr)
        except Exception:
            pass

    # ── 3. CLAHE on L-channel ────────────────────────────────────────────────
    lab = cv2.cvtColor(plate_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    plate_bgr = cv2.cvtColor(cv2.merge([clahe.apply(l), a, b]), cv2.COLOR_LAB2BGR)

    # ── 4. Auto-Gamma Correction ─────────────────────────────────────────────
    gray_check = cv2.cvtColor(plate_bgr, cv2.COLOR_BGR2GRAY)
    mean_br    = float(np.mean(gray_check))
    gamma = 0.7 if mean_br < 80 else (1.4 if mean_br > 180 else 1.0)
    if gamma != 1.0:
        table     = np.array([(i / 255.0) ** gamma * 255 for i in range(256)], dtype=np.uint8)
        plate_bgr = cv2.LUT(plate_bgr, table)

    # ── 5. Bilateral Filter ──────────────────────────────────────────────────
    plate_bgr = cv2.bilateralFilter(plate_bgr, d=9, sigmaColor=75, sigmaSpace=75)

    # ── 6. Unsharp Mask ──────────────────────────────────────────────────────
    blur      = cv2.GaussianBlur(plate_bgr, (0, 0), sigmaX=3)
    plate_bgr = cv2.addWeighted(plate_bgr, 1.5, blur, -0.5, 0)

    # ── 7. Denoise ───────────────────────────────────────────────────────────
    plate_gray = cv2.cvtColor(plate_bgr, cv2.COLOR_BGR2GRAY)
    plate_gray = cv2.fastNlMeansDenoising(plate_gray, h=10)
    plate_bgr  = cv2.cvtColor(plate_gray, cv2.COLOR_GRAY2BGR)

    return plate_bgr

def deskew_plate(gray: np.ndarray) -> np.ndarray:
    coords = np.column_stack(np.where(gray < 200))
    if len(coords) < 10:
        return gray
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle += 90
    if abs(angle) > 0.5:
        M = cv2.getRotationMatrix2D(
            (gray.shape[1] // 2, gray.shape[0] // 2), angle, 1.0
        )
        gray = cv2.warpAffine(gray, M, gray.shape[1::-1])
    return gray

# ─────────────────────────────────────────────────────────────────────────────
# Vehicle Attributes
# ─────────────────────────────────────────────────────────────────────────────
VEHICLE_TYPE_MAP = {
    2: "รถยนต์/เก๋ง (Car)",
    3: "มอเตอร์ไซค์ (Motorcycle)",
    5: "รถบัส/รถตู้ (Bus/Van)",
    7: "รถกระบะ/บรรทุก (Truck)",
}

COLOR_RANGES = {
    "ขาว (White)":       {"lower": [0,   0,   180], "upper": [180, 40,  255]},
    "ดำ (Black)":        {"lower": [0,   0,   0],   "upper": [180, 255, 50]},
    "เทา/เงิน (Silver)": {"lower": [0,   0,   50],  "upper": [180, 40,  180]},
    "แดง (Red)":         {"lower": [0,   70,  50],  "upper": [10,  255, 255]},
    "แดง (Red)_2":       {"lower": [170, 70,  50],  "upper": [180, 255, 255]},
    "น้ำเงิน (Blue)":   {"lower": [90,  50,  50],  "upper": [130, 255, 255]},
    "เหลือง (Yellow)":   {"lower": [15,  50,  50],  "upper": [35,  255, 255]},
    "เขียว (Green)":     {"lower": [35,  50,  50],  "upper": [85,  255, 255]},
}

def get_vehicle_attributes(vehicle_crop: np.ndarray, class_id: int) -> Tuple[str, str]:
    v_type = VEHICLE_TYPE_MAP.get(int(class_id), "รถทั่วไป (Vehicle)")
    h, w   = vehicle_crop.shape[:2]
    body   = vehicle_crop[int(h * 0.3):int(h * 0.8), int(w * 0.1):int(w * 0.9)]
    if body.size == 0:
        return v_type, "ไม่ระบุ (Unknown)"
    small  = cv2.resize(body, (32, 32))
    hsv    = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    counts: Dict[str, int] = {}
    for name, bounds in COLOR_RANGES.items():
        lo   = np.array(bounds["lower"], dtype=np.uint8)
        hi   = np.array(bounds["upper"], dtype=np.uint8)
        base = name.split("_")[0]
        counts[base] = counts.get(base, 0) + int(cv2.countNonZero(cv2.inRange(hsv, lo, hi)))
    dominant = max(counts, key=counts.get)
    if counts[dominant] < 50:
        dominant = "ไม่ชัดเจน (Unclear)"
    return v_type, dominant

def get_vehicle_fingerprint(vehicle_crop: np.ndarray) -> Optional[List[float]]:
    if vehicle_feature_extractor is None or _fp_preprocess is None:
        return None
    try:
        rgb     = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2RGB)
        tensor  = _fp_preprocess(rgb).unsqueeze(0)
        with torch.no_grad():
            features = vehicle_feature_extractor(tensor)
        return features.squeeze().numpy().tolist()
    except Exception:
        return None

# ─────────────────────────────────────────────────────────────────────────────
# Part 6: PaddleOCR on plate crop
# ─────────────────────────────────────────────────────────────────────────────
def parse_paddle_results(result) -> list:
    """
    Parse PaddleOCR output into a flat list of (text, conf, x_pos) tuples.
    PaddleOCR format: result[0] = [[[x1,y1],[x2,y1],[x2,y2],[x1,y2]], [text, conf]]
    """
    items = []
    if not result or not result[0]:
        return items
    for line in result[0]:
        if not line or len(line) < 2:
            continue
        bbox  = line[0]    # list of 4 corner points
        text  = line[1][0] if line[1] else ""
        conf  = float(line[1][1]) if line[1] else 0.0
        if not text or conf <= 0:
            continue
        x_pos = float(min(p[0] for p in bbox))
        items.append((text, conf, x_pos))
    return items

def run_ocr_on_plate(
    plate_bgr: np.ndarray,
    plate_detect_conf: float,
) -> Optional[Dict]:
    """
    Full OCR pipeline for a single plate crop using PaddleOCR.
    Returns result dict or None if quality/confidence below thresholds.
    """
    if plate_bgr is None or plate_bgr.size == 0:
        return None

    # ── Part 3: Plate Size Validation ────────────────────────────────────────
    pv = plate_validator.validate(plate_bgr)
    if not pv.valid:
        api_pm.inc("rejected_plate_size")
        return None

    # ── Part 4: Reflection Detection ─────────────────────────────────────────
    ref = reflection_detector.detect(plate_bgr)
    if ref.status == "reject":
        api_pm.inc("rejected_reflection")
        return None

    gray    = cv2.cvtColor(plate_bgr, cv2.COLOR_BGR2GRAY)
    lap_var = laplacian_variance(gray)
    if lap_var < BLUR_THRESHOLD:
        api_pm.inc("rejected_blur")
        return None

    mean_br = float(np.mean(gray))
    if mean_br < 30 or mean_br > 240:
        return None

    # ── Enhancement ──────────────────────────────────────────────────────────
    enhanced   = enhance_plate_image(plate_bgr)
    gray_enh   = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)
    gray_enh   = deskew_plate(gray_enh)
    enhanced   = cv2.cvtColor(gray_enh, cv2.COLOR_GRAY2BGR)

    # ── PaddleOCR ────────────────────────────────────────────────────────────
    if ocr_reader is None:
        return None   # PaddleOCR not installed
    paddle_result = ocr_reader.ocr(enhanced, cls=True)
    ocr_items     = parse_paddle_results(paddle_result)

    plate_parts: list  = []
    province_candidate = ""
    province_conf      = 0.0

    for text, conf, x_pos in ocr_items:
        province = match_province(text)
        if province and conf >= PROVINCE_CONF_THRESHOLD:
            if conf > province_conf:
                province_candidate = province
                province_conf      = conf
        else:
            cleaned = clean_plate_text(text)
            if conf >= OCR_CONF_THRESHOLD and 2 <= len(cleaned) <= 20:
                plate_parts.append({"text": cleaned, "x": x_pos, "conf": conf})

    if not plate_parts:
        return None

    plate_parts.sort(key=lambda p: p["x"])
    raw_combined = normalize_plate("".join(p["text"] for p in plate_parts))
    combined, _corrected = correction_cache.apply(raw_combined)

    has_consonant = bool(re.search(r'[ก-ฮ]', combined))
    has_number    = bool(re.search(r'[0-9]', combined))
    is_standard   = has_consonant and has_number and len(combined) >= 3
    is_truck      = combined.isdigit() and len(combined) >= 5

    if not (is_standard or is_truck):
        return None

    ocr_conf      = max(p["conf"] for p in plate_parts)
    quality_score, _ = compute_quality_score(plate_bgr)

    # ── Part 8: Composite Confidence ──────────────────────────────────────────
    composite = (
        ocr_conf          * 0.50 +
        plate_detect_conf * 0.30 +
        quality_score     * 0.20
    )

    return {
        "plate":          combined,
        "province":       province_candidate,
        "ocr_conf":       round(ocr_conf, 4),
        "quality_score":  round(quality_score, 4),
        "laplacian_var":  round(lap_var, 2),
        "composite_conf": round(composite, 4),
    }

# ─────────────────────────────────────────────────────────────────────────────
# Backend Communication
# ─────────────────────────────────────────────────────────────────────────────
BACKEND_DETECT_URL     = f"{API_URL}/api/plate/detect"
BACKEND_LIVE_FRAME_URL = f"{API_URL}/api/cameras/live_frame"

def send_to_backend(payload: dict):
    try:
        headers = {"X-API-Key": API_KEY}
        res = requests.post(BACKEND_DETECT_URL, json=payload, headers=headers, timeout=5)
        if res.status_code == 200:
            log.event(payload.get("track_id", "-"), "Data Sent",
                      status="OK", plate=payload.get("plate_number"))
        else:
            log.warn(payload.get("track_id", "-"), "Data Sent",
                     f"Backend {res.status_code}")
    except Exception as e:
        log.error(payload.get("track_id", "-"), "Data Sent", str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Live snapshot store
# ─────────────────────────────────────────────────────────────────────────────
_latest_snapshot: Optional[bytes] = None

# ─────────────────────────────────────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    return {
        "status":  "ok",
        "service": "plate-ai-server",
        "version": "3.0.0",
        "ocr":     "PaddleOCR",
        "sr":      ENABLE_SR,
        "models": {
            "vehicle": vehicle_model_path,
            "plate":   PLATE_MODEL_PATH if plate_model else "fallback crop",
        },
    }


@app.get("/metrics")
def get_metrics():
    """Pipeline stage counters + OCR correction cache + OCR analyzer stats."""
    return JSONResponse({
        "pipeline":          api_pm.summary(),
        "correction_cache":  correction_cache.as_dict(),
        "ocr_performance":   ocr_analyzer.as_dict(),
        "ocr_available":     _PADDLE_AVAILABLE,
    })


@app.get("/diagnostics")
def get_diagnostics(camera_id: Optional[int] = None):
    """
    Part 5: Camera self-diagnostics.

    Returns the most recent diagnostic result for the camera.
    To refresh diagnostics, POST a frame to /detect_frame — the result
    is computed on every received frame automatically.
    """
    diag = camera_diag_store.as_dict()
    diag["camera_id"]    = camera_id or 1
    diag["alerts_recent"] = api_alerts.recent(n=10)
    return JSONResponse(diag)


@app.get("/alerts")
def get_alerts(level: Optional[str] = None, n: int = 50):
    """Return recent enterprise alerts (optionally filtered by level)."""
    return JSONResponse({
        "counts": api_alerts.counts(),
        "alerts": api_alerts.recent(n=n, level=level or None),
    })


@app.get("/snapshot")
def get_snapshot():
    """Return latest processed frame as JPEG (polled every 2s by dashboard)."""
    global _latest_snapshot
    if _latest_snapshot is None:
        raise HTTPException(status_code=404, detail="No frame yet")
    return StreamingResponse(
        iter([_latest_snapshot]),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/detect_frame")
async def detect_frame(
    file:             UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    x_track_id:       Optional[str] = Header(None),
    x_camera_id:      Optional[str] = Header(None),
    x_direction:      Optional[str] = Header(None),    # from client.py sidecar
    x_quality_score:  Optional[str] = Header(None),    # from client.py sidecar
    x_frame_index:    Optional[str] = Header(None),    # which frame in window (1-5)
):
    """
    Main detection endpoint.
    Receives JPEG + metadata headers, runs full AI pipeline, returns detections.
    Temp file is deleted immediately after processing.
    """
    global global_last_sent, _latest_snapshot, sent_cache

    t_start   = time.perf_counter()
    track_id       = x_track_id  or f"TRK_{uuid.uuid4().hex[:8]}"
    camera_id      = int(x_camera_id) if x_camera_id and x_camera_id.isdigit() else 1
    direction      = x_direction or "IN"           # Direction from client.py virtual line
    client_quality = float(x_quality_score or 0.0)
    frame_idx      = int(x_frame_index or 1)

    temp_path = TEMP_DIR / f"{uuid.uuid4().hex}.jpg"
    try:
        contents = await file.read()
        temp_path.write_bytes(contents)

        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            raise HTTPException(status_code=400, detail="Invalid image")

        log.event(track_id, "Frame Received",
                  status="OK", camera=camera_id,
                  size=f"{frame.shape[1]}x{frame.shape[0]}",
                  dir=direction, q=f"{client_quality:.1f}",
                  frame_idx=frame_idx)

        # ── Camera Diagnostics (update on every frame received) ──────────────
        diag = camera_diag_store.update(frame)
        if diag.status == "CRITICAL":
            api_alerts.critical("camera", diag.recommendation,
                                {"camera_id": camera_id})
        elif diag.status == "WARNING":
            api_alerts.warning("camera", diag.recommendation,
                               {"camera_id": camera_id})

        # ── Low-Light Enhancement ─────────────────────────────────────────────
        low_light, brightness = is_low_light(frame)
        if low_light:
            frame = enhance_low_light(frame)
            log.event(track_id, "Low-Light Enhancement",
                      status="Applied", brightness=f"{brightness:.1f}")

        # ── Vehicle Detection ─────────────────────────────────────────────────
        yolo_results = vehicle_model(frame, classes=[2, 3, 5, 7],
                                     imgsz=DETECT_IMGSZ, verbose=False)
        detections: List[dict] = []
        display_frame = frame.copy()

        for r in yolo_results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                class_id        = int(box.cls[0])
                vehicle_crop    = frame[y1:y2, x1:x2]
                if vehicle_crop.size == 0:
                    continue

                api_pm.inc("vehicle_seen")
                log.event(track_id, "Vehicle Detected",
                          status="OK", cls=class_id,
                          box=f"[{x1},{y1},{x2},{y2}]")

                # ── Plate Detection ───────────────────────────────────────────
                plate_crop     = None
                plate_det_conf = 0.5

                if plate_model is not None:
                    p_results = plate_model(vehicle_crop, imgsz=PLATE_IMGSZ, verbose=False)
                    for pr in p_results:
                        if len(pr.boxes) > 0:
                            best = max(pr.boxes, key=lambda b: float(b.conf[0]))
                            plate_det_conf = float(best.conf[0])
                            px1, py1, px2, py2 = map(int, best.xyxy[0])
                            ph, pw = vehicle_crop.shape[:2]
                            pad_x  = int((px2 - px1) * 0.10)
                            pad_y  = int((py2 - py1) * 0.10)
                            px1 = max(0, px1 - pad_x)
                            py1 = max(0, py1 - pad_y)
                            px2 = min(pw, px2 + pad_x)
                            py2 = min(ph, py2 + pad_y)
                            plate_crop = vehicle_crop[py1:py2, px1:px2]
                            log.event(track_id, "Plate Detected",
                                      status="MODEL", conf=f"{plate_det_conf:.2f}")
                            break

                # Part 5 fallback: bottom center 30%
                if plate_crop is None or plate_crop.size == 0:
                    vh, vw = vehicle_crop.shape[:2]
                    plate_crop = vehicle_crop[
                        int(vh * 0.70):int(vh * 0.97),
                        int(vw * 0.15):int(vw * 0.85),
                    ]
                    plate_det_conf = 0.5
                    log.event(track_id, "Plate Detected", status="FALLBACK_CROP")

                if plate_crop is None or plate_crop.size == 0:
                    detections.append({
                        "vehicle_box": [x1, y1, x2, y2],
                        "status":      "no_plate_region",
                    })
                    continue

                api_pm.inc("plate_detected")

                # ── Part 6: PaddleOCR Pipeline ───────────────────────────────
                ocr_result = run_ocr_on_plate(plate_crop, plate_det_conf)

                if ocr_result is None:
                    log.warn(track_id, "OCR", "Rejected (blur/quality/no text)")
                    detections.append({
                        "vehicle_box": [x1, y1, x2, y2],
                        "status":      "ocr_rejected",
                    })
                    continue

                api_pm.inc("ocr_success")
                plate    = ocr_result["plate"]
                province = ocr_result["province"]
                comp     = ocr_result["composite_conf"]
                qs       = ocr_result["quality_score"]

                # Record to OCR analyzer (sliding-window performance tracking)
                ocr_analyzer.record(
                    ocr_text=plate,
                    confidence=ocr_result["ocr_conf"],
                    success=True,
                )

                log.event(track_id, "OCR Success",
                          status="OK", plate=plate, province=province,
                          conf=f"{comp:.2f}", quality=f"{qs:.2f}")

                # ── Part 7: Multi-Frame Vote Buffer ──────────────────────────
                track_buffer.add(track_id, plate, province, ocr_result["ocr_conf"], comp)
                consensus = track_buffer.get_consensus(track_id)

                if consensus is None:
                    detections.append({
                        "vehicle_box": [x1, y1, x2, y2],
                        "plate":       plate,
                        "province":    province,
                        "confidence":  round(comp, 4),
                        "quality":     round(qs, 4),
                        "status":      "pending_vote",
                    })
                    continue

                final_plate, final_province, avg_ocr, avg_comp = consensus

                # ── Part 8: Composite Confidence Check ───────────────────────
                if avg_comp < MIN_CONFIDENCE:
                    log.warn(track_id, "Confidence Check",
                             f"Below threshold ({avg_comp:.2f} < {MIN_CONFIDENCE})")
                    detections.append({
                        "vehicle_box": [x1, y1, x2, y2],
                        "plate":       final_plate,
                        "province":    final_province,
                        "confidence":  round(avg_comp, 4),
                        "status":      "low_confidence",
                    })
                    continue

                # ── Part 9: Duplicate Suppression (30s per plate+camera) ──────
                now      = time.time()
                dup_key  = f"{normalize_plate(final_plate)}:{camera_id}"
                sent_cache = {
                    k: v for k, v in sent_cache.items()
                    if now - v < DUPLICATE_COOLDOWN
                }

                if now - global_last_sent < GLOBAL_COOLDOWN:
                    detections.append({
                        "vehicle_box": [x1, y1, x2, y2],
                        "plate":       final_plate,
                        "status":      "cooldown",
                    })
                    continue

                norm_new = normalize_plate(final_plate)
                is_dup   = any(
                    difflib.SequenceMatcher(None, norm_new, k.split(":")[0]).ratio() > 0.8
                    and k.endswith(f":{camera_id}")
                    for k in sent_cache
                )
                if is_dup:
                    api_pm.inc("duplicate_suppressed")
                    log.event(track_id, "Duplicate Suppressed",
                              status="IGNORED", plate=final_plate,
                              cooldown=f"{DUPLICATE_COOLDOWN}s")
                    detections.append({
                        "vehicle_box": [x1, y1, x2, y2],
                        "plate":       final_plate,
                        "status":      "duplicate",
                    })
                    continue

                # ── Build & Send Payload ──────────────────────────────────────
                proc_ms             = int((time.perf_counter() - t_start) * 1000)
                v_type, v_color     = get_vehicle_attributes(vehicle_crop, class_id)
                fingerprint         = get_vehicle_fingerprint(vehicle_crop)

                payload = {
                    "plate_number":        final_plate,
                    "province":            final_province,
                    "vehicle_type":        v_type,
                    "vehicle_color":       v_color,
                    "vehicle_fingerprint": fingerprint,
                    "confidence_score":    round(avg_comp, 4),
                    "image_quality_score": round(avg_ocr, 4),
                    "quality_score":       round(client_quality, 1),  # from thin client
                    "processing_time_ms":  proc_ms,
                    "track_id":            track_id,
                    "camera_id":           camera_id,
                    "direction":           direction,                  # from virtual line
                    "timestamp":           datetime.now().isoformat(),
                }

                background_tasks.add_task(send_to_backend, payload)
                api_pm.inc("backend_saved")
                api_pm.inc("dashboard_sent")
                sent_cache[dup_key]  = now
                global_last_sent     = now
                track_buffer.clear_track(track_id)

                log.event(track_id, "Data Sent",
                          status="QUEUED",
                          plate=final_plate,
                          conf=f"{avg_comp:.2f}",
                          dir=direction,
                          proc_ms=proc_ms)

                cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(display_frame, final_plate, (x1, max(0, y1 - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                detections.append({
                    "vehicle_box":   [x1, y1, x2, y2],
                    "plate":         final_plate,
                    "province":      final_province,
                    "vehicle_type":  v_type,
                    "vehicle_color": v_color,
                    "confidence":    round(avg_comp, 4),
                    "quality":       round(qs, 4),
                    "direction":     direction,
                    "track_id":      track_id,
                    "status":        "sent",
                })

        # ── Update live snapshot ──────────────────────────────────────────────
        try:
            snap = cv2.resize(display_frame, (
                640, int(640 * display_frame.shape[0] / display_frame.shape[1])
            ))
            _, buf           = cv2.imencode(".jpg", snap, [cv2.IMWRITE_JPEG_QUALITY, 60])
            _latest_snapshot = buf.tobytes()
        except Exception:
            pass

        proc_total = int((time.perf_counter() - t_start) * 1000)
        log.event(track_id, "Frame Complete",
                  status=f"{len(detections)} detections",
                  proc_ms=proc_total)

        return JSONResponse({
            "detections":        detections,
            "processing_time_ms": proc_total,
        })

    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# PART 6 — Fleet Management Endpoints
# ─────────────────────────────────────────────────────────────────────────────

from pydantic import BaseModel
from typing import Any


class RegisterPayload(BaseModel):
    device_id:        str
    hostname:         str = ""
    site_id:          str = "default"
    camera_count:     int = 1
    software_version: str = "unknown"


class HeartbeatPayload(BaseModel):
    device_id:     str
    site_id:       str  = "default"
    uptime:        float = 0.0
    cpu:           float = 0.0
    memory:        float = 0.0
    disk:          float = 0.0
    camera_status: dict  = {}
    fps:           float = 0.0
    latency:       float = 0.0


@app.post("/fleet/register")
def fleet_register(payload: RegisterPayload):
    record = fleet_mgr.register(payload.device_id, payload.dict())
    return JSONResponse({"success": True, "device": record})


@app.post("/fleet/heartbeat")
def fleet_heartbeat(payload: HeartbeatPayload):
    fleet_mgr.heartbeat(payload.device_id, payload.dict())
    return JSONResponse({"success": True})


@app.get("/fleet")
def fleet_list(site_id: Optional[str] = None):
    return JSONResponse({
        "devices": fleet_mgr.get_fleet(site_id=site_id),
        "stats":   fleet_mgr.get_stats(),
    })


@app.get("/fleet/{device_id}")
def fleet_device(device_id: str):
    dev = fleet_mgr.get_device(device_id)
    if dev is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return JSONResponse(dev)


# ─────────────────────────────────────────────────────────────────────────────
# PART 6 — Remote Config Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/fleet/config/{device_id}")
def get_device_config(device_id: str):
    return JSONResponse(config_svc.get_config(device_id))


@app.put("/fleet/config/{device_id}")
async def update_device_config(device_id: str, request):
    body: dict = await request.json()
    cfg = config_svc.update_config(device_id, body)
    return JSONResponse({"success": True, "config": cfg})


@app.delete("/fleet/config/{device_id}")
def reset_device_config(device_id: str):
    cfg = config_svc.reset_config(device_id)
    return JSONResponse({"success": True, "config": cfg})


# ─────────────────────────────────────────────────────────────────────────────
# PART 6 — OTA Update Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/updates/version")
def get_version():
    return JSONResponse(upd_mgr.current_version())


@app.post("/updates/check")
def check_update():
    info = upd_mgr.check_now()
    return JSONResponse({"update_found": info is not None, "info": info})


@app.post("/updates/rollback")
def do_rollback():
    ok = upd_mgr.rollback()
    return JSONResponse({"success": ok})


# ─────────────────────────────────────────────────────────────────────────────
# PART 6 — Backup Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/backup/now")
def backup_now():
    path = backup_svc.run_now()
    return JSONResponse({"success": path is not None, "path": path})


@app.get("/backup/list")
def backup_list():
    return JSONResponse({"backups": backup_svc.list_backups()})
