import cv2
import requests
import time
import os
import numpy as np
from dotenv import load_dotenv
from ultralytics import YOLO
import easyocr
import re
import difflib
import json
from datetime import datetime
from PIL import ImageFont, ImageDraw, Image
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import queue
import logging
import platform
import threading

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("lpr.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("LPR")

send_queue = queue.Queue()

def process_offline_queue():
    while True:
        try:
            payload = send_queue.get()
            success = False
            for attempt in range(3):
                try:
                    res = requests.post(API_URL, json=payload, timeout=3)
                    if res.status_code == 200:
                        success = True
                        log.info(f"-> Sent offline payload successfully: {payload.get('plate_number')}")
                        break
                except Exception:
                    time.sleep(2)
            if not success:
                log.warning(f"-> Still cannot reach backend, re-queueing: {payload.get('plate_number')}")
                time.sleep(5)
                send_queue.put(payload)
            send_queue.task_done()
        except Exception as e:
            log.error(f"Error in offline queue processing: {e}", exc_info=True)
            time.sleep(5)

threading.Thread(target=process_offline_queue, daemon=True).start()

def send_with_retry(payload, retries=3):
    for attempt in range(retries):
        try:
            res = requests.post(API_URL, json=payload, timeout=3)
            if res.status_code == 200:
                return True
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    
    log.warning(f"Backend unreachable, queued: {payload}")
    send_queue.put(payload)
    return False


def preprocess_plate(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    # Deskew: แก้ป้ายเอียง
    coords = np.column_stack(np.where(gray < 200))
    if len(coords) > 10:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45: angle += 90
        if abs(angle) > 0.5:
            M = cv2.getRotationMatrix2D(
                (gray.shape[1]//2, gray.shape[0]//2), angle, 1.0)
            gray = cv2.warpAffine(gray, M, gray.shape[1::-1])
    
    # Sharpen
    kernel = np.array([[0,-1,0],[-1,5,-1],[0,-1,0]])
    return cv2.filter2D(gray, -1, kernel)

def get_thai_font(size):
    system = platform.system()
    paths = {
        "Windows": ["C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/leelawad.ttf"],
        "Linux":   ["/usr/share/fonts/truetype/thai/Garuda.ttf",
                    "/usr/share/fonts/truetype/tlwg/Garuda.ttf"],
        "Darwin":  ["/Library/Fonts/Thonburi.ttf"]
    }
    for path in paths.get(system, []):
        try:
            return ImageFont.truetype(path, size)
        except IOError:
            continue
    return ImageFont.load_default()

API_URL = os.getenv("API_URL", "http://localhost:3001/api/detect")
CAMERA_ID = int(os.getenv("CAMERA_ID", 1))

_source = os.getenv("CAMERA_SOURCE", "0")
CAMERA_SOURCE = int(_source) if str(_source).isdigit() else _source

# ============================================================
# CONFIG: Tunable thresholds
# ============================================================
TEST_MODE = False                 # True = skip YOLO, scan center of frame (for paper plate testing)
                                  # False = normal mode (detect vehicles first, then read plate)
PLATE_CONF_THRESHOLD = 0.4       # Min conf for plate (Lowered for outdoor demo lighting)
PROVINCE_CONF_THRESHOLD = 0.6    # Min conf for province (Lowered for outdoor demo)
PROCESS_EVERY_N_FRAMES = 3       # Run YOLO every 3 frames (was 5) -> faster green box
YOLO_IMG_SIZE = 320               # Shrink YOLO input (640->320) -> 4x faster inference
OCR_UPSCALE = 1.5                 # OCR upscale factor (was 2.0) -> faster OCR
INSTANT_SEND_THRESHOLD = 0.85    # If conf >= this, skip multi-frame wait and send now
DISPLAY_DURATION = 3.0            # Seconds to keep red box on screen
GLOBAL_COOLDOWN = 5               # Seconds between API sends
DUPLICATE_COOLDOWN = 60           # Seconds to treat similar plates as duplicate
MULTI_FRAME_VOTES_NEEDED = 2     # How many frames must agree before we send
DEBOUNCE_WINDOW = 8.0            # Seconds window for multi-frame voting
PLATE_MODEL_PATH = os.getenv("PLATE_MODEL_PATH", "plate_detect.pt")  # 2nd-stage YOLO for plate region

# ============================================================
# DEBUG: Directory to save cropped plate images
# ============================================================
DEBUG_DIR = os.path.join(os.path.dirname(__file__), "debug_plates")
os.makedirs(DEBUG_DIR, exist_ok=True)

# ============================================================
# Initialize Models
# ============================================================
log.info("Loading YOLOv8 Models...")
try:
    vehicle_model = YOLO("yolov8n.pt")
except Exception as e:
    log.error(f"Error loading YOLO vehicle model: {e}", exc_info=True)

# 2nd-stage: Plate detection model (optional but recommended)
plate_model = None
if os.path.exists(PLATE_MODEL_PATH):
    try:
        plate_model = YOLO(PLATE_MODEL_PATH)
        log.info(f"Plate detection model loaded: {PLATE_MODEL_PATH}")
    except Exception as e:
        log.warning(f"Could not load plate model '{PLATE_MODEL_PATH}': {e}")
else:
    log.info(f"No plate model at '{PLATE_MODEL_PATH}' -> using hardcoded crop fallback.")
    log.info(f"TIP: Place a trained plate YOLO model as '{PLATE_MODEL_PATH}' for better accuracy.")

log.info("Loading EasyOCR...")
ocr = easyocr.Reader(['th', 'en'], gpu=False)

# ============================================================
# Province list (all 77 provinces)
# ============================================================
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
# Utility Functions
# ============================================================

def clean_plate_text(text):
    """Remove everything except Thai consonants and digits (for plate numbers)."""
    cleaned = re.sub(r'[^ก-ฮ0-9]', '', text)
    return cleaned

def clean_for_province(text):
    """Clean text for province matching: keep ALL Thai characters (consonants + vowels + tone marks), remove digits and punctuation."""
    # Keep Thai range U+0E01 to U+0E5B (covers consonants, vowels, tone marks)
    cleaned = re.sub(r'[^\u0E01-\u0E5B]', '', text)
    return cleaned

def normalize_plate(plate_text):
    """
    Normalize plate text:
    - Remove spaces, dashes, dots
    - Remove non Thai-consonant / non-digit chars
    """
    normalized = re.sub(r'[\s\-\._]+', '', plate_text)
    normalized = re.sub(r'[^ก-ฮ0-9]', '', normalized)
    return normalized

def match_province(raw_text):
    """
    Smart province matching from raw OCR text.
    Works on text WITH vowels/tone marks intact.
    
    Examples:
      'สขลา'           -> 'สงขลา'       (missing ง)
      'กรุงเทพมหานค'    -> 'กรุงเทพมหานคร' (missing ร)
      'ชลบุร'           -> 'ชลบุรี'       (missing ี)
      'นนทบร'           -> 'นนทบุรี'      (missing vowel)
    """
    cleaned = clean_for_province(raw_text)
    
    # Must be at least 3 Thai characters and no digits in original
    if len(cleaned) < 3 or any(c.isdigit() for c in raw_text):
        return None
    
    # 1. Exact match
    if cleaned in THAI_PROVINCES:
        return cleaned
    
    # 2. Fuzzy match using SequenceMatcher (better than get_close_matches for missing chars)
    best_match = None
    best_ratio = 0
    
    for province in THAI_PROVINCES:
        ratio = difflib.SequenceMatcher(None, cleaned, province).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = province
    
    # 3. Also check if the cleaned text is a substring of a province (handles truncation)
    for province in THAI_PROVINCES:
        if len(cleaned) >= 3 and cleaned in province:
            # Strong substring match
            if best_ratio < 0.8:  # Only override if fuzzy wasn't already great
                best_match = province
                best_ratio = 0.85
    
    # Accept if similarity >= 50% (generous for OCR typos)
    if best_ratio >= 0.5:
        return best_match
    
    return None

def put_thai_text(img, text, position, font_size=32, color=(0, 0, 255)):
    """Draw Thai text on OpenCV image using PIL."""
    font = get_thai_font(font_size)

    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    rgb_color = (color[2], color[1], color[0])
    draw.text(position, text, font=font, fill=rgb_color)
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

def save_debug_images(original_frame, cropped_plate, plate_text, province_text, confidence):
    """
    Save debug images for later analysis:
    - original_frame.jpg
    - cropped_plate.jpg
    - result.json (OCR text + confidence)
    """
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        folder = os.path.join(DEBUG_DIR, f"{ts}_{plate_text}")
        os.makedirs(folder, exist_ok=True)

        # Save original frame
        cv2.imwrite(os.path.join(folder, "frame.jpg"), original_frame)

        # Save cropped plate
        if cropped_plate is not None and cropped_plate.size > 0:
            cv2.imwrite(os.path.join(folder, "plate_crop.jpg"), cropped_plate)

        # Save OCR result as JSON
        result = {
            "plate": plate_text,
            "province": province_text,
            "confidence": round(confidence, 4),
            "camera_id": CAMERA_ID,
            "timestamp": datetime.now().isoformat()
        }
        with open(os.path.join(folder, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        log.debug(f"Saved debug images to {folder}")
    except Exception as e:
        log.error(f"Error saving debug images: {e}", exc_info=True)


# ============================================================
# OCR Worker (runs in background thread)
# ============================================================

def run_ocr_task(image_crop):
    """Run EasyOCR on a cropped image. Returns list of detected text items."""
    h, w = image_crop.shape[:2]
    if h == 0 or w == 0:
        return []

    # Upscale for better small-text detection (1.5x = sweet spot for speed vs accuracy)
    new_w, new_h = int(w * OCR_UPSCALE), int(h * OCR_UPSCALE)
    enlarged = cv2.resize(image_crop, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    # --- Preprocessing & Enhancement ---
    gray = preprocess_plate(enlarged)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced_img = clahe.apply(gray)
    # Convert back to BGR just in case
    enlarged_bgr = cv2.cvtColor(enhanced_img, cv2.COLOR_GRAY2BGR)

    results = ocr.readtext(enlarged_bgr)
    valid_results = []
    if results:
        for line in results:
            raw_text = line[1]
            ocr_conf = line[2]
            bx1, by1 = map(lambda x: int(x/OCR_UPSCALE), line[0][0])
            bx2, by2 = map(lambda x: int(x/OCR_UPSCALE), line[0][2])
            
            # Try province match FIRST on raw text (with vowels intact!)
            province = match_province(raw_text)
            if province:
                valid_results.append({
                    "text": province,
                    "conf": ocr_conf,
                    "bbox": (bx1, by1, bx2, by2),
                    "is_province": True
                })
            else:
                # Not a province -> treat as plate number part
                cleaned = clean_plate_text(raw_text)
                if ocr_conf > 0.2 and 2 <= len(cleaned) <= 20:
                    valid_results.append({
                        "text": cleaned,
                        "conf": ocr_conf,
                        "bbox": (bx1, by1, bx2, by2),
                        "is_province": False
                    })
    return valid_results


# ============================================================
# Multi-Frame Vote Buffer
# ============================================================

class PlateVoteBuffer:
    """
    Collects plate readings across multiple frames.
    Only sends to backend when the same plate is seen >= VOTES_NEEDED times
    within a DEBOUNCE_WINDOW. This dramatically reduces false positives.
    """
    def __init__(self, votes_needed=2, window_sec=8.0):
        self.votes_needed = votes_needed
        self.window_sec = window_sec
        self.buffer = []  # list of (plate_text, province, conf, timestamp)

    def add_reading(self, plate_text, province, conf):
        now = time.time()
        self.buffer.append((plate_text, province, conf, now))
        # Purge expired readings
        self.buffer = [(p, prov, c, t) for p, prov, c, t in self.buffer if now - t < self.window_sec]

    def get_consensus(self):
        """
        Check if any normalized plate has enough votes.
        Returns (plate_text, province, avg_confidence) or None.
        """
        if not self.buffer:
            return None

        # Group by normalized plate
        groups = {}
        for plate_text, province, conf, t in self.buffer:
            norm = normalize_plate(plate_text)
            if norm not in groups:
                groups[norm] = {"plates": [], "provinces": [], "confs": []}
            groups[norm]["plates"].append(plate_text)
            groups[norm]["provinces"].append(province)
            groups[norm]["confs"].append(conf)

        # Find the group with most votes
        for norm, data in groups.items():
            if len(data["plates"]) >= self.votes_needed:
                # Pick the most common raw plate text (majority vote)
                best_plate = Counter(data["plates"]).most_common(1)[0][0]
                # Pick the most common province (if any)
                provinces = [p for p in data["provinces"] if p]
                best_province = Counter(provinces).most_common(1)[0][0] if provinces else ""
                avg_conf = sum(data["confs"]) / len(data["confs"])

                # Clear this group from buffer after consensus
                self.buffer = [(p, prov, c, t) for p, prov, c, t in self.buffer
                               if normalize_plate(p) != norm]
                return (best_plate, best_province, avg_conf)

        return None


# ============================================================
# Main Loop
# ============================================================

def main():
    log.info(f"Starting AI Service for Camera {CAMERA_ID}...")
    cap = cv2.VideoCapture(CAMERA_SOURCE)

    if not cap.isOpened():
        log.error(f"Could not open video source {CAMERA_SOURCE}")
        return

    # Anti-spam cache
    sent_plates_cache = {}
    global_last_sent_time = 0

    # Display state
    last_ocr_display = []
    last_ocr_timestamp = 0

    # OCR executor
    executor = ThreadPoolExecutor(max_workers=1)
    ocr_future = None
    ocr_x_offset = 0
    ocr_y_offset = 0

    # Frame skip state
    frame_count = 0
    last_vehicle_boxes = []
    last_best_crop = None
    last_crop_offset_x = 0
    last_crop_offset_y = 0
    last_vehicle_detected = False

    # Multi-frame vote buffer
    vote_buffer = PlateVoteBuffer(
        votes_needed=MULTI_FRAME_VOTES_NEEDED,
        window_sec=DEBOUNCE_WINDOW
    )

    # Keep a reference to the original frame for debug saving
    last_original_frame = None

    log.info(f"Mode: {'TEST (paper plate)' if TEST_MODE else 'PRODUCTION (real vehicles)'}")
    log.info(f"Plate threshold: {PLATE_CONF_THRESHOLD}, Province threshold: {PROVINCE_CONF_THRESHOLD}")
    log.info(f"Multi-frame votes needed: {MULTI_FRAME_VOTES_NEEDED}, Window: {DEBOUNCE_WINDOW}s")
    log.info(f"Debug images saved to: {DEBUG_DIR}")

    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(1)
            continue

        frame_count += 1
        last_original_frame = frame.copy()

        # ==============================================
        # 1. Vehicle Detection / Test Mode
        # ==============================================
        if TEST_MODE:
            # TEST MODE: Skip YOLO entirely, scan center 60% of frame
            fh, fw = frame.shape[:2]
            margin_x, margin_y = int(fw * 0.2), int(fh * 0.2)
            cx1, cy1 = margin_x, margin_y
            cx2, cy2 = fw - margin_x, fh - margin_y

            last_vehicle_detected = True
            last_vehicle_boxes = [(cx1, cy1, cx2, cy2)]
            last_best_crop = frame[cy1:cy2, cx1:cx2]
            last_crop_offset_x = cx1
            last_crop_offset_y = cy1
        elif frame_count % PROCESS_EVERY_N_FRAMES == 0:
            # PRODUCTION MODE: Use YOLO to find vehicles first
            results = vehicle_model(frame, classes=[2, 3, 5, 7], imgsz=YOLO_IMG_SIZE, verbose=False)
            last_vehicle_boxes = []
            last_vehicle_detected = False
            last_best_crop = None
            last_crop_offset_x = 0
            last_crop_offset_y = 0

            for r in results:
                boxes = r.boxes
                for box in boxes:
                    last_vehicle_detected = True
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    last_vehicle_boxes.append((x1, y1, x2, y2))

                    vehicle_crop = frame[y1:y2, x1:x2]
                    if vehicle_crop.size > 0:
                        h, w = vehicle_crop.shape[:2]

                        # --- 2-Stage: Try plate detection model first ---
                        plate_found_by_model = False
                        if plate_model is not None:
                            plate_results = plate_model(vehicle_crop, imgsz=320, verbose=False)
                            best_plate_conf = 0
                            for pr in plate_results:
                                for pbox in pr.boxes:
                                    pconf = float(pbox.conf[0])
                                    if pconf > best_plate_conf:
                                        best_plate_conf = pconf
                                        px1, py1, px2, py2 = map(int, pbox.xyxy[0])
                                        # Add padding around detected plate (10%)
                                        pad_x = int((px2 - px1) * 0.1)
                                        pad_y = int((py2 - py1) * 0.1)
                                        px1 = max(0, px1 - pad_x)
                                        py1 = max(0, py1 - pad_y)
                                        px2 = min(w, px2 + pad_x)
                                        py2 = min(h, py2 + pad_y)
                                        last_best_crop = vehicle_crop[py1:py2, px1:px2]
                                        last_crop_offset_x = x1 + px1
                                        last_crop_offset_y = y1 + py1
                                        plate_found_by_model = True

                            if plate_found_by_model:
                                log.debug(f"Detected plate region by model (conf: {best_plate_conf:.2f})")

                        # --- Fallback: hardcoded crop if no plate model or no detection ---
                        if not plate_found_by_model:
                            last_best_crop = vehicle_crop[int(h*0.55):int(h*0.95), int(w*0.2):int(w*0.8)]
                            last_crop_offset_x = x1 + int(w*0.2)
                            last_crop_offset_y = y1 + int(h*0.55)

        # Draw cached vehicle/scan boxes
        box_color = (0, 255, 255) if TEST_MODE else (0, 255, 0)  # Yellow in test, Green in prod
        for (x1, y1, x2, y2) in last_vehicle_boxes:
            cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
        
        # Show mode label on screen
        if TEST_MODE:
            cv2.putText(frame, 'TEST MODE', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        # ==============================================
        # 2. Process completed OCR results
        # ==============================================
        if ocr_future is not None and ocr_future.done():
            try:
                found_texts = ocr_future.result()
                if found_texts:
                    plate_candidate = ""
                    province_candidate = ""
                    best_conf = 0
                    consensus = None

                    min_x, min_y = 99999, 99999
                    max_x, max_y = 0, 0

                    plate_parts = []

                    for item in found_texts:
                        text = item["text"]
                        conf = item["conf"]
                        bx1, by1, bx2, by2 = item["bbox"]
                        abs_x1 = bx1 + ocr_x_offset
                        abs_y1 = by1 + ocr_y_offset
                        abs_x2 = bx2 + ocr_x_offset
                        abs_y2 = by2 + ocr_y_offset

                        min_x = min(min_x, abs_x1)
                        min_y = min(min_y, abs_y1)
                        max_x = max(max_x, abs_x2)
                        max_y = max(max_y, abs_y2)

                        log.debug(f"OCR saw: '{text}' (Conf: {conf:.2f}){' [PROVINCE]' if item.get('is_province') else ''}")

                        if item.get("is_province"):
                            # Province already matched by NLP in run_ocr_task
                            if conf >= PROVINCE_CONF_THRESHOLD:
                                province_candidate = text
                                log.debug(f"Province accepted: '{text}' (conf {conf:.2f})")
                            else:
                                log.debug(f"Province '{text}' rejected (conf {conf:.2f} < {PROVINCE_CONF_THRESHOLD})")
                        else:
                            # Plate part: apply plate confidence threshold
                            if conf >= PLATE_CONF_THRESHOLD:
                                plate_parts.append({"text": text, "x": bx1, "conf": conf})
                            else:
                                log.debug(f"Plate part '{text}' rejected (conf {conf:.2f} < {PLATE_CONF_THRESHOLD})")

                    # Sort plate parts left-to-right and join
                    plate_parts = sorted(plate_parts, key=lambda p: p["x"])
                    combined_plate = "".join([p["text"] for p in plate_parts])

                    # Normalize the plate
                    combined_plate = normalize_plate(combined_plate)

                    if plate_parts:
                        best_conf = max([p["conf"] for p in plate_parts])

                    has_consonant = bool(re.search(r'[ก-ฮ]', combined_plate))
                    has_number = bool(re.search(r'[0-9]', combined_plate))

                    is_standard_plate = (has_consonant and has_number and len(combined_plate) >= 3)
                    is_truck_plate = (combined_plate.isdigit() and len(combined_plate) >= 5)

                    if is_standard_plate or is_truck_plate:
                        plate_candidate = combined_plate

                    # ==============================================
                    # 3. Multi-Frame Voting (Debounce) or Instant Send
                    # ==============================================
                    if plate_candidate:
                        # Update display immediately (red box appears fast!)
                        combined_display = plate_candidate
                        if province_candidate:
                            combined_display += f" {province_candidate}"

                        pad_x, pad_y = 15, 10
                        final_box = (
                            max(0, min_x - pad_x),
                            max(0, min_y - pad_y),
                            max_x + pad_x,
                            max_y + pad_y
                        )
                        last_ocr_display = [{"text": combined_display, "bbox": final_box}]
                        last_ocr_timestamp = time.time()

                        # HIGH CONFIDENCE? -> Send immediately, no waiting!
                        if best_conf >= INSTANT_SEND_THRESHOLD:
                            log.info(f"[FAST] High confidence ({best_conf:.2f}) -> instant send!")
                            consensus = (plate_candidate, province_candidate, best_conf)
                        else:
                            # Normal path: add to vote buffer and wait for agreement
                            vote_buffer.add_reading(plate_candidate, province_candidate, best_conf)
                            consensus = vote_buffer.get_consensus()

                    # Process consensus (from either instant or multi-frame)
                    if plate_candidate and consensus:
                        final_plate, final_province, avg_conf = consensus
                        combined_text = final_plate
                        if final_province:
                            combined_text += f" {final_province}"

                        current_time = time.time()

                        # Global cooldown
                        if (current_time - global_last_sent_time) >= GLOBAL_COOLDOWN:
                            # Duplicate check
                            is_duplicate = False
                            for cached_plate, last_time in sent_plates_cache.items():
                                if (current_time - last_time) <= DUPLICATE_COOLDOWN:
                                    similarity = difflib.SequenceMatcher(
                                        None, normalize_plate(combined_text), normalize_plate(cached_plate)
                                    ).ratio()
                                    if similarity > 0.8:
                                        is_duplicate = True
                                        sent_plates_cache[cached_plate] = current_time
                                        break

                            if not is_duplicate:
                                log.info(f"*** CONFIRMED PLATE (multi-frame): {combined_text} (avg conf: {avg_conf:.2f}) ***")

                                # Save debug images
                                save_debug_images(
                                    last_original_frame,
                                    last_best_crop,
                                    final_plate,
                                    final_province,
                                    avg_conf
                                )

                                # Send to backend
                                payload = {
                                    "plate_number": combined_text,
                                    "confidence_score": avg_conf,
                                    "camera_id": CAMERA_ID
                                }
                                send_with_retry(payload)

                                sent_plates_cache[combined_text] = current_time
                                global_last_sent_time = current_time

            except Exception as e:
                log.error(f"OCR Error: {e}", exc_info=True)
            ocr_future = None

        # ==============================================
        # 4. Dispatch new OCR task (if idle)
        # ==============================================
        if ocr_future is None:
            if last_vehicle_detected and last_best_crop is not None:
                ocr_x_offset = last_crop_offset_x
                ocr_y_offset = last_crop_offset_y
                ocr_future = executor.submit(run_ocr_task, last_best_crop)
            # else: Don't scan empty frames -> save CPU for when a car actually appears

        # ==============================================
        # 5. Draw persistent red text
        # ==============================================
        if time.time() - last_ocr_timestamp < DISPLAY_DURATION:
            for item in last_ocr_display:
                bx1, by1, bx2, by2 = item["bbox"]
                text = item["text"]
                cv2.rectangle(frame, (bx1, by1), (bx2, by2), (0, 0, 255), 2)
                frame = put_thai_text(frame, text, (bx1, max(0, by1 - 30)), font_size=24, color=(0, 0, 255))

        # ==============================================
        # 6. Display frame
        # ==============================================
        cv2.imshow(f"LPR Camera {CAMERA_ID}", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
