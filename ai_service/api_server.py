import os
import cv2
import numpy as np
import requests
import time
import re
import difflib
import json
import logging
from datetime import datetime
from collections import Counter
from fastapi import FastAPI, File, UploadFile, Header, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from ultralytics import YOLO
import easyocr
import torch
from torchvision import models, transforms

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("API")

app = FastAPI(title="Plate AI Server")

# ============================================================
# Config
# ============================================================
API_URL = os.getenv("API_URL", "http://plate-backend:3003") # ยิงตรงเข้า Backend container (ไม่ต้องผ่าน Nginx)
API_KEY = os.getenv("API_KEY", "PLATE-AI-KEY-totacademy-2026") 
PLATE_CONF_THRESHOLD = 0.4
PROVINCE_CONF_THRESHOLD = 0.6
OCR_UPSCALE = 1.5
MULTI_FRAME_VOTES_NEEDED = 2
DEBOUNCE_WINDOW = 8.0
INSTANT_SEND_THRESHOLD = 0.85
GLOBAL_COOLDOWN = 5
DUPLICATE_COOLDOWN = 60

# ============================================================
# Models
# ============================================================
log.info("Loading YOLOv8 Models...")
try:
    # Use ONNX if available for faster CPU inference
    vehicle_model_path = "yolov8n.onnx" if os.path.exists("yolov8n.onnx") else "yolov8n.pt"
    vehicle_model = YOLO(vehicle_model_path)
    log.info(f"Loaded vehicle model: {vehicle_model_path}")
except Exception as e:
    log.critical(f"Cannot load YOLO vehicle model: {e}")

# Check for plate model (ONNX or PT)
PLATE_MODEL_PATH = "plate_detect.onnx" if os.path.exists("plate_detect.onnx") else "plate_detect.pt"
plate_model = None
if os.path.exists(PLATE_MODEL_PATH):
    try:
        plate_model = YOLO(PLATE_MODEL_PATH)
        log.info(f"Loaded plate model: {PLATE_MODEL_PATH}")
    except Exception as e:
        log.warning(f"Found plate model but failed to load: {e}")
else:
    log.info("No plate model found. Using fallback hardcoded crop.")

log.info("Loading EasyOCR...")
ocr = easyocr.Reader(['th', 'en'], gpu=False)

# ============================================================
# Vehicle Fingerprint: ResNet18 Feature Extractor
# ============================================================
log.info("Loading ResNet18 for vehicle fingerprinting...")
try:
    _resnet = models.resnet18(weights='IMAGENET1K_V1')
    _resnet.eval()
    # ตัด classification head ออก → ใช้แค่ feature vector 512 มิติ
    vehicle_feature_extractor = torch.nn.Sequential(*list(_resnet.children())[:-1])
    _fp_preprocess = transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    log.info("ResNet18 loaded successfully (512-dim fingerprint)")
except Exception as e:
    vehicle_feature_extractor = None
    log.warning(f"Could not load ResNet18: {e}. Fingerprinting disabled.")

def get_vehicle_fingerprint(vehicle_crop):
    """แปลงรูปรถเป็น 512-dim feature vector (ลายนิ้วมือ)"""
    if vehicle_feature_extractor is None:
        return None
    try:
        # แปลง BGR (OpenCV) → RGB
        rgb = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2RGB)
        tensor = _fp_preprocess(rgb).unsqueeze(0)
        with torch.no_grad():
            features = vehicle_feature_extractor(tensor)
        return features.squeeze().numpy().tolist()  # → list of 512 floats
    except Exception as e:
        log.debug(f"Fingerprint extraction failed: {e}")
        return None

THAI_PROVINCES = [
    "กรุงเทพมหานคร", "กระบี่", "กาญจนบุรี", "กาฬสินธุ์", "กำแพงเพชร",
    "ขอนแก่น", "จันทบุรี", "ฉะเชิงเทรา", "ชลบุรี", "ชัยนาท",
    "ชัยภูมิ", "ชุมพร", "เชียงราย", "เชียงใหม่", "ตรัง",
    "ตราด", "ตาก", "นครนายก", "นครปฐม", "นครพนม",
    "นครราชสีมา", "นครศรีธรรมราช", "นครสวรรค์", "นนทบุรี", "นราธิวาส",
    "น่าน", "บึงกาฬ", "บุรีรัมย์", "ปทุมธานี", "ประจวบคีรีขันธ์",
    "ปราจีนบุรี", "ปัตตานี", "พระนครศรีอยุธยา", "พะเยา", "พังงา",
    "พัทลุง", "พิจิตร", "พิษณุโลก", "เพชรบุรี", "เพชรบูรณ์",
    "แพร่", "ภูเก็ต", "มหาสารคาม", "มุกดาหาร", "แม่ฮ่องสอน",
    "ยโสธร", "ยะลา", "ร้อยเอ็ด", "ระนอง", "ระยอง",
    "ราชบุรี", "ลพบุรี", "ลำปาง", "ลำพูน", "เลย",
    "ศรีสะเกษ", "สกลนคร", "สงขลา", "สตูล", "สมุทรปราการ",
    "สมุทรสงคราม", "สมุทรสาคร", "สระแก้ว", "สระบุรี", "สิงห์บุรี",
    "สุโขทัย", "สุพรรณบุรี", "สุราษฎร์ธานี", "สุรินทร์", "หนองคาย",
    "หนองบัวลำภู", "อ่างทอง", "อำนาจเจริญ", "อุดรธานี", "อุตรดิตถ์",
    "อุทัยธานี", "อุบลราชธานี"
]

# ============================================================
# Low-Light Enhancement
# ============================================================
def is_low_light(frame):
    """ตรวจว่าภาพมืดกว่าปกติ (ค่าเฉลี่ยสว่างน้อยกว่า 70 = กลางคืน/ห้องมืด)"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean_brightness = cv2.mean(gray)[0]
    return mean_brightness < 70, mean_brightness

def enhance_low_light(frame):
    """
    เพิ่มความสว่างภาพกลางคืนแบบ 3 ขั้น:
    1. CLAHE บน L-channel (ทำให้รายละเอียดชัด ไม่ overexpose)
    2. Gamma Correction (ดึงเงาให้สว่างขึ้น)
    3. Denoise (ลด noise ที่มากับกลางคืน)
    """
    # Step 1: CLAHE บน L-channel ของ LAB color space
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l)
    lab_enhanced = cv2.merge([l_enhanced, a, b])
    result = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)
    
    # Step 2: Gamma Correction (gamma < 1 = ดึงเงาให้สว่างขึ้น)
    gamma = 1.8
    inv_gamma = 1.0 / gamma
    table = np.array([(i / 255.0) ** inv_gamma * 255 for i in range(256)]).astype(np.uint8)
    result = cv2.LUT(result, table)
    
    # Step 3: Denoise เบาๆ เพื่อลด Grain ของกล้อง
    result = cv2.fastNlMeansDenoisingColored(result, None, 5, 5, 7, 21)
    
    return result

# ============================================================
# State / Variables
# ============================================================
class PlateVoteBuffer:
    def __init__(self, votes_needed=2, window_sec=8.0):
        self.votes_needed = votes_needed
        self.window_sec = window_sec
        self.buffer = []

    def add_reading(self, plate_text, province, conf):
        now = time.time()
        self.buffer.append((plate_text, province, conf, now))
        self.buffer = [(p, prov, c, t) for p, prov, c, t in self.buffer if now - t < self.window_sec]

    def get_consensus(self):
        if not self.buffer: return None
        groups = {}
        for plate_text, province, conf, t in self.buffer:
            norm = normalize_plate(plate_text)
            if norm not in groups:
                groups[norm] = {"plates": [], "provinces": [], "confs": []}
            groups[norm]["plates"].append(plate_text)
            groups[norm]["provinces"].append(province)
            groups[norm]["confs"].append(conf)

        for norm, data in groups.items():
            if len(data["plates"]) >= self.votes_needed:
                best_plate = Counter(data["plates"]).most_common(1)[0][0]
                provinces = [p for p in data["provinces"] if p]
                best_province = Counter(provinces).most_common(1)[0][0] if provinces else ""
                avg_conf = sum(data["confs"]) / len(data["confs"])
                self.buffer = [(p, prov, c, t) for p, prov, c, t in self.buffer if normalize_plate(p) != norm]
                return (best_plate, best_province, avg_conf)
        return None

vote_buffer = PlateVoteBuffer(votes_needed=MULTI_FRAME_VOTES_NEEDED, window_sec=DEBOUNCE_WINDOW)
sent_plates_cache = {}
global_last_sent_time = 0

# ============================================================
# Utils
# ============================================================
def clean_plate_text(text):
    return re.sub(r'[^ก-ฮ0-9]', '', text)

def clean_for_province(text):
    return re.sub(r'[^\u0E01-\u0E5B]', '', text)

def normalize_plate(plate_text):
    normalized = re.sub(r'[\s\-\._]+', '', plate_text)
    return re.sub(r'[^ก-ฮ0-9]', '', normalized)

def match_province(raw_text):
    cleaned = clean_for_province(raw_text)
    if len(cleaned) < 3 or any(c.isdigit() for c in raw_text): return None
    if cleaned in THAI_PROVINCES: return cleaned
    
    best_match, best_ratio = None, 0
    for province in THAI_PROVINCES:
        ratio = difflib.SequenceMatcher(None, cleaned, province).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = province
            
    for province in THAI_PROVINCES:
        if len(cleaned) >= 3 and cleaned in province:
            if best_ratio < 0.8:
                best_match = province
                best_ratio = 0.85
    if best_ratio >= 0.5: return best_match
    return None

def get_human_like_color_and_type(vehicle_crop, class_id):
    # 1. คิดแบบคน: แยกประเภทรถจากรูปทรง (YOLO Class ID)
    type_map = {
        2: "รถยนต์/เก๋ง (Car)", 
        3: "มอเตอร์ไซค์ (Motorcycle)", 
        5: "รถบัส/รถตู้ (Bus/Van)", 
        7: "รถกระบะ/บรรทุก (Truck)"
    }
    v_type = type_map.get(int(class_id), "รถทั่วไป (Vehicle)")

    # 2. คิดแบบคน: มองหาสีเด่นของรถ โดยตัดส่วนหน้าต่างและยางออกไป (ใช้ครึ่งล่างของรถ)
    h, w = vehicle_crop.shape[:2]
    # คนเรามองสีรถจากตัวถัง ตัดขอบบน (หลังคา/กระจก) และขอบล่างสุด (ยาง/เงา) ทิ้งไป
    body_crop = vehicle_crop[int(h*0.3):int(h*0.8), int(w*0.1):int(w*0.9)]
    if body_crop.size == 0:
        return v_type, "ไม่ระบุ (Unknown)"

    # ย่อภาพเพื่อลด Noise และทำงานเร็วขึ้น (เหมือนคนหรี่ตามองภาพรวม)
    small = cv2.resize(body_crop, (32, 32))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    
    # กำหนดช่วงสี (Hue, Saturation, Value) ตามสายตาคนมอง
    color_ranges = {
        "ขาว (White)":    {"lower": [0, 0, 180],   "upper": [180, 40, 255]},
        "ดำ (Black)":      {"lower": [0, 0, 0],     "upper": [180, 255, 50]},
        "เทา/เงิน (Silver)": {"lower": [0, 0, 50],  "upper": [180, 40, 180]},
        "แดง (Red)":       {"lower": [0, 70, 50],   "upper": [10, 255, 255]},
        "แดง (Red)_2":     {"lower": [170, 70, 50], "upper": [180, 255, 255]},
        "น้ำเงิน (Blue)":  {"lower": [90, 50, 50],  "upper": [130, 255, 255]},
        "เหลือง (Yellow)": {"lower": [15, 50, 50],  "upper": [35, 255, 255]},
        "เขียว (Green)":   {"lower": [35, 50, 50],  "upper": [85, 255, 255]}
    }
    
    color_counts = {}
    for name, bounds in color_ranges.items():
        lower = np.array(bounds["lower"], dtype=np.uint8)
        upper = np.array(bounds["upper"], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
        
        base_name = name.split("_")[0] # รวม แดง และ แดง_2 เข้าด้วยกัน
        color_counts[base_name] = color_counts.get(base_name, 0) + cv2.countNonZero(mask)
        
    dominant_color = max(color_counts, key=color_counts.get)
    # ถ้าทุกสึมีค่าน้อยมาก (ภาพมืดมาก หรือจ้ามาก)
    if color_counts[dominant_color] < 50:
        dominant_color = "ไม่ชัดเจน (Unclear)"
        
    return v_type, dominant_color

def send_to_backend(payload):
    try:
        headers = {"X-API-Key": API_KEY}
        res = requests.post(API_URL, json=payload, headers=headers, timeout=3)
        if res.status_code == 200:
            log.info(f"Successfully sent to backend: {payload}")
        else:
            log.error(f"Backend returned {res.status_code}: {res.text}")
    except Exception as e:
        log.error(f"Failed to send to backend: {e}")

# ============================================================
# API Endpoints
# ============================================================
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "plate-ai-server"}

@app.post("/detect_frame")
async def detect_frame(file: UploadFile = File(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    global global_last_sent_time, sent_plates_cache
    
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if frame is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    # --- Low-Light Mode: ตรวจและปรับแสงก่อนส่ง AI ---
    low_light, brightness = is_low_light(frame)
    if low_light:
        log.debug(f"[LowLight] Brightness={brightness:.1f} < 70 -> Enhancing frame...")
        frame = enhance_low_light(frame)

    results = vehicle_model(frame, classes=[2, 3, 5, 7], imgsz=320, verbose=False)
    detections = []
    
    for r in results:
        for box in r.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            class_id = int(box.cls[0])
            vehicle_crop = frame[y1:y2, x1:x2]
            
            if vehicle_crop.size == 0: continue
            
            # AI ให้เหตุผลเหมือนคน: "เห็นรถประเภทนี้ สีนี้"
            v_type, v_color = get_human_like_color_and_type(vehicle_crop, class_id)
            
            # --- Plate Detection Strategy ---
            plate_crop = None
            if plate_model is not None:
                # 1. ใช้โมเดลหาป้ายโดยเฉพาะ (เร็วและแม่นยำที่สุด)
                p_results = plate_model(vehicle_crop, imgsz=160, verbose=False)
                for pr in p_results:
                    if len(pr.boxes) > 0:
                        # สมมติว่าเอากล่องที่มั่นใจที่สุด
                        best_box = max(pr.boxes, key=lambda b: b.conf[0])
                        px1, py1, px2, py2 = map(int, best_box.xyxy[0])
                        plate_crop = vehicle_crop[py1:py2, px1:px2]
                        break
            
            if plate_crop is None or plate_crop.size == 0:
                # 2. Fallback: ถ้าไม่มีโมเดล หรือโมเดลหาไม่เจอ ให้สุ่มตัดตรงกลางล่างของรถ
                h, w = vehicle_crop.shape[:2]
                plate_crop = vehicle_crop[int(h*0.55):int(h*0.95), int(w*0.2):int(w*0.8)]
            
            if plate_crop.size == 0: continue
            
            # OCR Processing (ตอนนี้จะเร็วขึ้นมากถ้าใช้ plate_detect.onnx ตัดมาให้ก่อน)
            new_w, new_h = int(plate_crop.shape[1] * OCR_UPSCALE), int(plate_crop.shape[0] * OCR_UPSCALE)
            enlarged = cv2.resize(plate_crop, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
            
            gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            enhanced_img = clahe.apply(gray)
            enlarged_bgr = cv2.cvtColor(enhanced_img, cv2.COLOR_GRAY2BGR)
            
            ocr_res = ocr.readtext(enlarged_bgr)
            
            plate_candidate = ""
            province_candidate = ""
            best_conf = 0
            plate_parts = []
            
            if ocr_res:
                for line in ocr_res:
                    raw_text = line[1]
                    ocr_conf = line[2]
                    
                    province = match_province(raw_text)
                    if province and ocr_conf >= PROVINCE_CONF_THRESHOLD:
                        province_candidate = province
                    else:
                        cleaned = clean_plate_text(raw_text)
                        if ocr_conf >= PLATE_CONF_THRESHOLD and 2 <= len(cleaned) <= 20:
                            plate_parts.append({"text": cleaned, "x": line[0][0][0], "conf": ocr_conf})
                
                plate_parts = sorted(plate_parts, key=lambda p: p["x"])
                combined_plate = normalize_plate("".join([p["text"] for p in plate_parts]))
                
                if plate_parts:
                    best_conf = max([p["conf"] for p in plate_parts])
                    
                has_consonant = bool(re.search(r'[ก-ฮ]', combined_plate))
                has_number = bool(re.search(r'[0-9]', combined_plate))
                is_standard = (has_consonant and has_number and len(combined_plate) >= 3)
                is_truck = (combined_plate.isdigit() and len(combined_plate) >= 5)
                
                if is_standard or is_truck:
                    plate_candidate = combined_plate
                    
            if plate_candidate:
                consensus = None
                if best_conf >= INSTANT_SEND_THRESHOLD:
                    consensus = (plate_candidate, province_candidate, best_conf)
                else:
                    vote_buffer.add_reading(plate_candidate, province_candidate, best_conf)
                    consensus = vote_buffer.get_consensus()
                
                if consensus:
                    final_plate, final_province, avg_conf = consensus
                    current_time = time.time()
                    
                    # Cleanup cache
                    sent_plates_cache = {k: v for k, v in sent_plates_cache.items() if (current_time - v) <= DUPLICATE_COOLDOWN}
                    
                    if (current_time - global_last_sent_time) >= GLOBAL_COOLDOWN:
                        is_duplicate = False
                        norm_candidate = normalize_plate(final_plate)
                        for cached_plate, last_time in sent_plates_cache.items():
                            similarity = difflib.SequenceMatcher(None, norm_candidate, normalize_plate(cached_plate)).ratio()
                            if similarity > 0.8:
                                is_duplicate = True
                                sent_plates_cache[cached_plate] = current_time
                                break
                                
                        if not is_duplicate:
                            log.info(f"*** CONFIRMED: {final_plate} | {final_province} | {v_type} | สี: {v_color} ***")
                            
                            # สร้าง fingerprint สำหรับรถคันนี้
                            fingerprint = get_vehicle_fingerprint(vehicle_crop)
                            
                            payload = {
                                "plate_number": final_plate,
                                "province": final_province,
                                "vehicle_type": v_type,
                                "vehicle_color": v_color,
                                "vehicle_fingerprint": fingerprint,
                                "confidence_score": round(avg_conf, 4),
                                "camera_id": 1,
                                "timestamp": datetime.now().isoformat()
                            }
                            background_tasks.add_task(send_to_backend, payload)
                            sent_plates_cache[final_plate] = current_time
                            global_last_sent_time = current_time
                            
                            detections.append({
                                "vehicle_box": [x1, y1, x2, y2],
                                "plate": final_plate,
                                "province": final_province,
                                "vehicle_type": v_type,
                                "vehicle_color": v_color,
                                "confidence": round(avg_conf, 4),
                                "status": "sent"
                            })
                            continue
                            
                detections.append({
                    "vehicle_box": [x1, y1, x2, y2],
                    "plate": plate_candidate,
                    "province": province_candidate,
                    "vehicle_type": v_type,
                    "vehicle_color": v_color,
                    "confidence": round(best_conf, 4),
                    "status": "pending_vote"
                })
            else:
                detections.append({
                    "vehicle_box": [x1, y1, x2, y2],
                    "vehicle_type": v_type,
                    "vehicle_color": v_color,
                    "status": "no_plate_detected"
                })

    return {"detections": detections}
