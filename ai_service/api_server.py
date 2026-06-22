"""
api_server.py — Production AI Server for LPR (FastAPI)
=======================================================

Pipeline per uploaded frame:
  1. Receive frame (multipart)
  2. Vehicle Detection (YOLOv8 ONNX)
  3. Per-vehicle:
       a. Plate Detection (plate model or fallback crop)
       b. Blur Rejection  (Laplacian variance < BLUR_THRESHOLD → skip)
       c. Enhancement      (CLAHE → Gamma → Bilateral → Sharpen → AdaptiveThreshold)
       d. Optional SR      (OpenCV DNN ESPCN 2x, OFF by default)
       e. EasyOCR on plate crop ONLY
       f. Per-track_id vote buffer (majority vote from last MAX_VOTE_FRAMES readings)
       g. Composite confidence = OCR×0.5 + plate_detect×0.3 + quality×0.2
       h. Accept only if composite ≥ MIN_CONFIDENCE
  4. Send structured JSON to Backend
  5. Delete temp file immediately after processing
  6. No permanent image storage on AI server

Environment variables:
  API_URL             Backend URL           http://plate-backend:3003
  API_KEY             Shared API key        PLATE-AI-KEY-totacademy-2026
  ENABLE_SR           Super Resolution      false
  SR_MODEL_PATH       ESPCN model file      ESPCN_x2.pb
  BLUR_THRESHOLD      Laplacian variance    100
  MIN_CONFIDENCE      Accept threshold      0.80
  MAX_VOTE_FRAMES     Vote buffer size      5
  GLOBAL_COOLDOWN     Seconds between sends 5
  DUPLICATE_COOLDOWN  Dup suppression secs  60
"""

import os
import cv2
import uuid
import time
import tempfile
import re
import difflib
import json
import base64
import logging
import asyncio

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List, Dict

import numpy as np
import requests
import torch
from torchvision import models, transforms

from fastapi import FastAPI, File, UploadFile, Header, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.gzip import GZipMiddleware
from ultralytics import YOLO
import easyocr

from logger_lpr import get_logger

# ─────────────────────────────────────────────────────────────────────────────
# App Setup
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Plate AI Server", version="2.0.0")
app.add_middleware(GZipMiddleware, minimum_size=1000)

log = get_logger("API_SERVER", camera_id="API")
std_log = logging.getLogger("uvicorn.error")

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
API_URL             = os.getenv("API_URL",  "http://plate-backend:3003")
API_KEY             = os.getenv("API_KEY",  "PLATE-AI-KEY-totacademy-2026")
ENABLE_SR           = os.getenv("ENABLE_SR", "false").lower() == "true"
SR_MODEL_PATH       = os.getenv("SR_MODEL_PATH", "ESPCN_x2.pb")
BLUR_THRESHOLD      = float(os.getenv("BLUR_THRESHOLD", "100"))
MIN_CONFIDENCE      = float(os.getenv("MIN_CONFIDENCE", "0.80"))
MAX_VOTE_FRAMES     = int(os.getenv("MAX_VOTE_FRAMES", "5"))
PLATE_CONF_THRESHOLD    = float(os.getenv("PLATE_CONF_THRESHOLD", "0.40"))
PROVINCE_CONF_THRESHOLD = float(os.getenv("PROVINCE_CONF_THRESHOLD", "0.55"))
OCR_CONF_THRESHOLD      = float(os.getenv("OCR_CONF_THRESHOLD", "0.35"))
GLOBAL_COOLDOWN     = int(os.getenv("GLOBAL_COOLDOWN", "5"))
DUPLICATE_COOLDOWN  = int(os.getenv("DUPLICATE_COOLDOWN", "60"))
DETECT_IMGSZ        = int(os.getenv("DETECT_IMGSZ", "320"))
PLATE_IMGSZ         = int(os.getenv("PLATE_IMGSZ", "160"))

# Temp directory for uploaded frames
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
    "อุทัยธานี","อุบลราชธานี"
]

# ─────────────────────────────────────────────────────────────────────────────
# Model Loading
# ─────────────────────────────────────────────────────────────────────────────
log.info("Loading YOLOv8 Vehicle Model...")
vehicle_model_path = "yolov8n.onnx" if os.path.exists("yolov8n.onnx") else "yolov8n.pt"
try:
    vehicle_model = YOLO(vehicle_model_path)
    log.info(f"Loaded vehicle model: {vehicle_model_path}")
except Exception as e:
    log.critical(f"Cannot load vehicle model: {e}")
    raise SystemExit(1)

PLATE_MODEL_PATH = "plate_detect.onnx" if os.path.exists("plate_detect.onnx") else "plate_detect.pt"
plate_model = None
if os.path.exists(PLATE_MODEL_PATH):
    try:
        plate_model = YOLO(PLATE_MODEL_PATH)
        log.info(f"Loaded plate model: {PLATE_MODEL_PATH}")
    except Exception as e:
        log.warn("-", "Model Load", f"Plate model load failed: {e}")

log.info("Loading EasyOCR (th, en)...")
ocr_reader = easyocr.Reader(['th', 'en'], gpu=False)
log.info("EasyOCR loaded.")

# ─────────────────────────────────────────────────────────────────────────────
# Super Resolution (Optional)
# ─────────────────────────────────────────────────────────────────────────────
sr_model = None
if ENABLE_SR:
    try:
        import cv2
        sr = cv2.dnn_superres.DnnSuperResImpl_create()
        if os.path.exists(SR_MODEL_PATH):
            sr.readModel(SR_MODEL_PATH)
            sr.setModel("espcn", 2)
            sr_model = sr
            log.info(f"Super Resolution enabled: {SR_MODEL_PATH} (2x)")
        else:
            log.warn("-", "SR Init", f"SR model not found: {SR_MODEL_PATH}. Disabled.")
    except Exception as e:
        log.warn("-", "SR Init", f"SR init failed: {e}. Disabled.")

# ─────────────────────────────────────────────────────────────────────────────
# Vehicle Fingerprint (ResNet18)
# ─────────────────────────────────────────────────────────────────────────────
log.info("Loading ResNet18 fingerprint extractor...")
vehicle_feature_extractor = None
_fp_preprocess = None
try:
    _resnet = models.resnet18(weights='IMAGENET1K_V1')
    _resnet.eval()
    vehicle_feature_extractor = torch.nn.Sequential(*list(_resnet.children())[:-1])
    _fp_preprocess = transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    log.info("ResNet18 fingerprint extractor ready.")
except Exception as e:
    log.warn("-", "Fingerprint Init", f"ResNet18 load failed: {e}. Fingerprinting disabled.")

# ─────────────────────────────────────────────────────────────────────────────
# Per-Track Vote Buffer (stateful within API process)
# ─────────────────────────────────────────────────────────────────────────────
class TrackVoteBuffer:
    """Maintains per-track_id OCR vote history for multi-frame consensus."""

    def __init__(self, max_frames: int = 5, window_sec: float = 30.0):
        self.max_frames = max_frames
        self.window_sec = window_sec
        # track_id -> list of (plate, province, ocr_conf, composite_conf, timestamp)
        self._data: Dict[str, list] = {}
        self._last_clean = time.time()

    def add(self, track_id: str, plate: str, province: str, ocr_conf: float, composite: float):
        now = time.time()
        if track_id not in self._data:
            self._data[track_id] = []
        self._data[track_id].append((plate, province, ocr_conf, composite, now))
        # Keep only last max_frames within window
        self._data[track_id] = [
            r for r in self._data[track_id]
            if now - r[4] < self.window_sec
        ][-self.max_frames:]
        self._cleanup_stale(now)

    def get_consensus(self, track_id: str) -> Optional[Tuple[str, str, float, float]]:
        """Returns (plate, province, avg_ocr_conf, avg_composite) or None."""
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
        stale = [tid for tid, readings in self._data.items()
                 if readings and now - readings[-1][4] > self.window_sec]
        for tid in stale:
            del self._data[tid]
        self._last_clean = now


track_buffer    = TrackVoteBuffer(max_frames=MAX_VOTE_FRAMES)
sent_cache      = {}         # plate_number -> timestamp
global_last_sent = 0.0

# ─────────────────────────────────────────────────────────────────────────────
# Utility: Text Cleaning
# ─────────────────────────────────────────────────────────────────────────────
def clean_plate_text(text: str) -> str:
    return re.sub(r'[^ก-ฮ0-9]', '', text)

def clean_for_province(text: str) -> str:
    return re.sub(r'[^\u0E01-\u0E5B]', '', text)

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
    """Higher = sharper. Blur rejection threshold: BLUR_THRESHOLD."""
    return float(cv2.Laplacian(gray_img, cv2.CV_64F).var())

def compute_quality_score(img: np.ndarray) -> Tuple[float, float]:
    """
    Returns (quality_score 0–1, laplacian_var).
    Combines sharpness + brightness into a single quality metric.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
    lap_var  = laplacian_variance(gray)
    mean_br  = float(np.mean(gray))

    # Sharpness score: sigmoid-like mapping, saturates at 500
    sharp_score = min(lap_var / 500.0, 1.0)

    # Brightness score: peak at 128, falls off toward 0 or 255
    bright_score = 1.0 - abs(mean_br - 128.0) / 128.0
    bright_score = max(0.0, bright_score)

    quality = sharp_score * 0.7 + bright_score * 0.3
    return round(quality, 4), lap_var

def is_low_light(frame: np.ndarray) -> Tuple[bool, float]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
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
    # Gamma correction γ=1.8
    table = np.array([(i / 255.0) ** (1.0 / 1.8) * 255 for i in range(256)], dtype=np.uint8)
    result = cv2.LUT(result, table)
    result = cv2.fastNlMeansDenoisingColored(result, None, 5, 5, 7, 21)
    return result

# ─────────────────────────────────────────────────────────────────────────────
# Plate Image Enhancement Pipeline
# ─────────────────────────────────────────────────────────────────────────────
def enhance_plate_image(plate_bgr: np.ndarray) -> np.ndarray:
    """
    Full enhancement pipeline for plate crop before OCR:
      1. Resize to OCR-friendly size (height ≥ 64px)
      2. CLAHE on L-channel
      3. Auto-Gamma based on mean brightness
      4. Bilateral Filter (denoise without edge blur)
      5. Unsharp Mask (sharpening)
      6. Adaptive Threshold variant returned alongside BGR
    Returns enhanced BGR image (OCR works better with it than binary threshold).
    """
    h, w = plate_bgr.shape[:2]

    # ── 1. Upscale to at least 64px height ────────────────────────────────
    target_h = max(h, 64)
    scale = target_h / h if h < 64 else 1.0
    if scale > 1.0:
        new_w = int(w * scale)
        plate_bgr = cv2.resize(plate_bgr, (new_w, target_h), interpolation=cv2.INTER_CUBIC)

    # Apply super resolution if enabled (2x)
    if sr_model is not None:
        try:
            plate_bgr = sr_model.upsample(plate_bgr)
        except Exception:
            pass  # SR failed, continue without it

    # ── 2. CLAHE on L-channel ─────────────────────────────────────────────
    lab = cv2.cvtColor(plate_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    l_enh = clahe.apply(l)
    plate_bgr = cv2.cvtColor(cv2.merge([l_enh, a, b]), cv2.COLOR_LAB2BGR)

    # ── 3. Auto-Gamma ─────────────────────────────────────────────────────
    gray_check = cv2.cvtColor(plate_bgr, cv2.COLOR_BGR2GRAY)
    mean_br = float(np.mean(gray_check))
    # Dark image → gamma < 1 (brighten); bright image → gamma > 1 (darken slightly)
    if mean_br < 80:
        gamma = 0.7
    elif mean_br > 180:
        gamma = 1.4
    else:
        gamma = 1.0
    if gamma != 1.0:
        table = np.array([(i / 255.0) ** gamma * 255 for i in range(256)], dtype=np.uint8)
        plate_bgr = cv2.LUT(plate_bgr, table)

    # ── 4. Bilateral Filter ───────────────────────────────────────────────
    plate_bgr = cv2.bilateralFilter(plate_bgr, d=9, sigmaColor=75, sigmaSpace=75)

    # ── 5. Unsharp Mask (sharpening) ──────────────────────────────────────
    blur    = cv2.GaussianBlur(plate_bgr, (0, 0), sigmaX=3)
    plate_bgr = cv2.addWeighted(plate_bgr, 1.5, blur, -0.5, 0)

    return plate_bgr

def deskew_plate(gray: np.ndarray) -> np.ndarray:
    """Correct small rotation angles in plate image."""
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
    7: "รถกระบะ/บรรทุก (Truck)"
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
    h, w = vehicle_crop.shape[:2]
    body = vehicle_crop[int(h*0.3):int(h*0.8), int(w*0.1):int(w*0.9)]
    if body.size == 0:
        return v_type, "ไม่ระบุ (Unknown)"
    small = cv2.resize(body, (32, 32))
    hsv   = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    counts: Dict[str, int] = {}
    for name, bounds in COLOR_RANGES.items():
        lo = np.array(bounds["lower"], dtype=np.uint8)
        hi = np.array(bounds["upper"], dtype=np.uint8)
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
        rgb    = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2RGB)
        tensor = _fp_preprocess(rgb).unsqueeze(0)
        with torch.no_grad():
            features = vehicle_feature_extractor(tensor)
        return features.squeeze().numpy().tolist()
    except Exception:
        return None

# ─────────────────────────────────────────────────────────────────────────────
# OCR — runs ONLY on plate crop
# ─────────────────────────────────────────────────────────────────────────────
def run_ocr_on_plate(
    plate_bgr: np.ndarray,
    plate_detect_conf: float
) -> Optional[Dict]:
    """
    Full OCR pipeline for a single plate crop.
    Returns dict or None if quality/confidence below thresholds.

    Returns:
        {
          plate, province, ocr_conf,
          quality_score, laplacian_var,
          composite_conf
        }
    """
    if plate_bgr is None or plate_bgr.size == 0:
        return None

    # ── Blur Rejection ────────────────────────────────────────────────────
    gray = cv2.cvtColor(plate_bgr, cv2.COLOR_BGR2GRAY)
    lap_var = laplacian_variance(gray)
    if lap_var < BLUR_THRESHOLD:
        return None   # Too blurry — reject

    # ── Brightness Check ──────────────────────────────────────────────────
    mean_br = float(np.mean(gray))
    if mean_br < 30 or mean_br > 240:
        return None   # Extreme exposure

    # ── Enhance ───────────────────────────────────────────────────────────
    enhanced = enhance_plate_image(plate_bgr)

    # Deskew
    gray_enh = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)
    gray_enh = deskew_plate(gray_enh)
    enhanced = cv2.cvtColor(gray_enh, cv2.COLOR_GRAY2BGR)

    # ── OCR ───────────────────────────────────────────────────────────────
    ocr_results = ocr_reader.readtext(enhanced)

    plate_parts = []
    province_candidate = ""
    province_conf      = 0.0

    if ocr_results:
        for item in ocr_results:
            raw_text = item[1]
            conf     = float(item[2])

            province = match_province(raw_text)
            if province and conf >= PROVINCE_CONF_THRESHOLD:
                if conf > province_conf:
                    province_candidate = province
                    province_conf      = conf
            else:
                cleaned = clean_plate_text(raw_text)
                if conf >= OCR_CONF_THRESHOLD and 2 <= len(cleaned) <= 20:
                    x_pos = float(item[0][0][0])
                    plate_parts.append({"text": cleaned, "x": x_pos, "conf": conf})

    if not plate_parts:
        return None

    # Sort left-to-right
    plate_parts.sort(key=lambda p: p["x"])
    combined = normalize_plate("".join(p["text"] for p in plate_parts))

    has_consonant = bool(re.search(r'[ก-ฮ]', combined))
    has_number    = bool(re.search(r'[0-9]', combined))
    is_standard   = has_consonant and has_number and len(combined) >= 3
    is_truck      = combined.isdigit() and len(combined) >= 5

    if not (is_standard or is_truck):
        return None

    ocr_conf     = max(p["conf"] for p in plate_parts)
    quality_score, _ = compute_quality_score(plate_bgr)

    # ── Composite Confidence ──────────────────────────────────────────────
    composite = (
        ocr_conf          * 0.50 +
        plate_detect_conf * 0.30 +
        quality_score     * 0.20
    )

    return {
        "plate":           combined,
        "province":        province_candidate,
        "ocr_conf":        round(ocr_conf,  4),
        "quality_score":   round(quality_score, 4),
        "laplacian_var":   round(lap_var, 2),
        "composite_conf":  round(composite, 4),
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

def send_live_frame(frame_b64: str, camera_id: int = 1):
    try:
        headers = {"X-API-Key": API_KEY}
        requests.post(
            BACKEND_LIVE_FRAME_URL,
            json={"camera_id": camera_id, "frame": frame_b64},
            headers=headers, timeout=1
        )
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# Live snapshot store (latest processed frame, for /snapshot endpoint)
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
        "version": "2.0.0",
        "sr":      ENABLE_SR,
        "models":  {
            "vehicle":  vehicle_model_path,
            "plate":    PLATE_MODEL_PATH if plate_model else "fallback crop",
        }
    }


@app.get("/snapshot")
def get_snapshot():
    """Return latest processed frame as JPEG (for dashboard polling, 2s interval)."""
    global _latest_snapshot
    if _latest_snapshot is None:
        raise HTTPException(status_code=404, detail="No frame yet")
    return StreamingResponse(
        iter([_latest_snapshot]),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"}
    )


@app.post("/detect_frame")
async def detect_frame(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    x_track_id: Optional[str] = Header(None),  # track_id from thin client
    x_camera_id: Optional[str] = Header(None),
):
    """
    Main detection endpoint.
    Receives a JPEG frame, runs AI pipeline, returns detections.
    Temp file deleted immediately after processing.
    """
    global global_last_sent, _latest_snapshot, sent_cache

    t_start = time.perf_counter()
    track_id  = x_track_id  or f"TRK_{uuid.uuid4().hex[:8]}"
    camera_id = int(x_camera_id) if x_camera_id and x_camera_id.isdigit() else 1

    # ── Write to temp file ────────────────────────────────────────────────
    temp_path = TEMP_DIR / f"{uuid.uuid4().hex}.jpg"
    try:
        contents = await file.read()
        temp_path.write_bytes(contents)

        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            raise HTTPException(status_code=400, detail="Invalid image")

        log.event(track_id, "Frame Received", status="OK",
                  camera=camera_id, size=f"{frame.shape[1]}x{frame.shape[0]}")

        # ── Low-Light Enhancement ─────────────────────────────────────────
        low_light, brightness = is_low_light(frame)
        if low_light:
            frame = enhance_low_light(frame)
            log.event(track_id, "Low-Light Enhancement",
                      status="Applied", brightness=f"{brightness:.1f}")

        # ── Vehicle Detection ─────────────────────────────────────────────
        yolo_results = vehicle_model(frame, classes=[2, 3, 5, 7],
                                      imgsz=DETECT_IMGSZ, verbose=False)
        detections: List[dict] = []
        display_frame = frame.copy()

        for r in yolo_results:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                class_id = int(box.cls[0])
                vehicle_crop = frame[y1:y2, x1:x2]
                if vehicle_crop.size == 0:
                    continue

                log.event(track_id, "Vehicle Detected", status="OK",
                           cls=class_id, box=f"[{x1},{y1},{x2},{y2}]")

                # ── Plate Detection ───────────────────────────────────────
                plate_crop      = None
                plate_det_conf  = 0.5    # Default for fallback crop

                if plate_model is not None:
                    p_results = plate_model(vehicle_crop, imgsz=PLATE_IMGSZ, verbose=False)
                    for pr in p_results:
                        if len(pr.boxes) > 0:
                            best = max(pr.boxes, key=lambda b: float(b.conf[0]))
                            plate_det_conf = float(best.conf[0])
                            px1, py1, px2, py2 = map(int, best.xyxy[0])
                            # 10% padding
                            ph, pw = vehicle_crop.shape[:2]
                            pad_x = int((px2 - px1) * 0.10)
                            pad_y = int((py2 - py1) * 0.10)
                            px1 = max(0, px1 - pad_x)
                            py1 = max(0, py1 - pad_y)
                            px2 = min(pw, px2 + pad_x)
                            py2 = min(ph, py2 + pad_y)
                            plate_crop = vehicle_crop[py1:py2, px1:px2]
                            log.event(track_id, "Plate Detected",
                                       status="MODEL", conf=f"{plate_det_conf:.2f}")
                            break

                # Fallback crop (bottom 55–95%, center 20–80%)
                if plate_crop is None or plate_crop.size == 0:
                    vh, vw = vehicle_crop.shape[:2]
                    plate_crop = vehicle_crop[
                        int(vh * 0.55):int(vh * 0.95),
                        int(vw * 0.20):int(vw * 0.80)
                    ]
                    plate_det_conf = 0.5
                    log.event(track_id, "Plate Detected", status="FALLBACK_CROP")

                if plate_crop is None or plate_crop.size == 0:
                    detections.append({
                        "vehicle_box": [x1, y1, x2, y2],
                        "status": "no_plate_region"
                    })
                    continue

                # ── OCR Pipeline ──────────────────────────────────────────
                ocr_result = run_ocr_on_plate(plate_crop, plate_det_conf)

                if ocr_result is None:
                    log.warn(track_id, "OCR", "Rejected (blur/quality/no text)")
                    detections.append({
                        "vehicle_box": [x1, y1, x2, y2],
                        "status": "ocr_rejected"
                    })
                    continue

                plate    = ocr_result["plate"]
                province = ocr_result["province"]
                comp     = ocr_result["composite_conf"]
                qs       = ocr_result["quality_score"]

                log.event(track_id, "OCR Success", status="OK",
                           plate=plate, province=province,
                           conf=f"{comp:.2f}", quality=f"{qs:.2f}")

                # ── Vote Buffer ───────────────────────────────────────────
                track_buffer.add(
                    track_id, plate, province,
                    ocr_result["ocr_conf"], comp
                )
                consensus = track_buffer.get_consensus(track_id)

                if consensus is None:
                    detections.append({
                        "vehicle_box": [x1, y1, x2, y2],
                        "plate":       plate,
                        "province":    province,
                        "confidence":  round(comp, 4),
                        "quality":     round(qs, 4),
                        "status":      "pending_vote"
                    })
                    continue

                final_plate, final_province, avg_ocr, avg_comp = consensus

                if avg_comp < MIN_CONFIDENCE:
                    log.warn(track_id, "Confidence Check",
                             f"Below threshold ({avg_comp:.2f} < {MIN_CONFIDENCE})")
                    detections.append({
                        "vehicle_box": [x1, y1, x2, y2],
                        "plate":       final_plate,
                        "province":    final_province,
                        "confidence":  round(avg_comp, 4),
                        "status":      "low_confidence"
                    })
                    continue

                # ── Cooldown + Duplicate Check ────────────────────────────
                now = time.time()
                sent_cache = {
                    k: v for k, v in sent_cache.items()
                    if now - v < DUPLICATE_COOLDOWN
                }
                if now - global_last_sent < GLOBAL_COOLDOWN:
                    detections.append({
                        "vehicle_box": [x1, y1, x2, y2],
                        "plate":       final_plate,
                        "province":    final_province,
                        "status":      "cooldown"
                    })
                    continue

                norm_new = normalize_plate(final_plate)
                is_dup   = any(
                    difflib.SequenceMatcher(None, norm_new, normalize_plate(k)).ratio() > 0.8
                    for k in sent_cache
                )
                if is_dup:
                    detections.append({
                        "vehicle_box": [x1, y1, x2, y2],
                        "plate":       final_plate,
                        "status":      "duplicate"
                    })
                    continue

                # ── Build Payload & Send ──────────────────────────────────
                proc_ms     = int((time.perf_counter() - t_start) * 1000)
                v_type, v_color = get_vehicle_attributes(vehicle_crop, class_id)
                fingerprint     = get_vehicle_fingerprint(vehicle_crop)

                payload = {
                    "plate_number":       final_plate,
                    "province":           final_province,
                    "vehicle_type":       v_type,
                    "vehicle_color":      v_color,
                    "vehicle_fingerprint": fingerprint,
                    "confidence_score":   round(avg_comp, 4),
                    "image_quality_score": round(avg_ocr, 4),
                    "processing_time_ms": proc_ms,
                    "track_id":           track_id,
                    "camera_id":          camera_id,
                    "timestamp":          datetime.now().isoformat(),
                }

                background_tasks.add_task(send_to_backend, payload)
                sent_cache[final_plate] = now
                global_last_sent        = now
                track_buffer.clear_track(track_id)

                log.event(track_id, "Data Sent", status="QUEUED",
                           plate=final_plate, conf=f"{avg_comp:.2f}",
                           proc_ms=proc_ms)

                # Draw on display frame
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(display_frame, final_plate, (x1, max(0, y1 - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                detections.append({
                    "vehicle_box":  [x1, y1, x2, y2],
                    "plate":        final_plate,
                    "province":     final_province,
                    "vehicle_type": v_type,
                    "vehicle_color": v_color,
                    "confidence":   round(avg_comp, 4),
                    "quality":      round(qs, 4),
                    "track_id":     track_id,
                    "status":       "sent"
                })

        # ── Update live snapshot ──────────────────────────────────────────
        try:
            snap = cv2.resize(display_frame, (640,
                int(640 * display_frame.shape[0] / display_frame.shape[1])))
            _, buf = cv2.imencode('.jpg', snap, [cv2.IMWRITE_JPEG_QUALITY, 60])
            _latest_snapshot = buf.tobytes()
        except Exception:
            pass

        proc_total = int((time.perf_counter() - t_start) * 1000)
        log.event(track_id, "Frame Complete",
                  status=f"{len(detections)} detections", proc_ms=proc_total)

        return JSONResponse({"detections": detections, "processing_time_ms": proc_total})

    finally:
        # ── ALWAYS delete temp file ───────────────────────────────────────
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
