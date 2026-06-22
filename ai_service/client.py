import cv2
import requests
import time
import os
import threading
import queue
import numpy as np

API_URL = os.getenv("API_URL", "http://100.127.92.120/api/plate/ai/detect_frame")
API_KEY = os.getenv("API_KEY", "PLATE-AI-KEY-totacademy-2026")
CAMERA_SOURCE = 0
FPS_LIMIT = 5  # ส่งภาพสูงสุด 5 ภาพต่อวินาที
MOTION_THRESHOLD = 3000  # จำนวนพิกเซลที่เปลี่ยนไป (ยิ่งน้อยยิ่งไวต่อการเคลื่อนไหว)

print(f"🚀 Starting Thin Client LPR (Async + Motion Detection)...")
print(f"📡 Sending to: {API_URL}")

# ============================================================
# Background API Worker (Thread)
# ============================================================
frame_queue = queue.Queue(maxsize=1)  # เก็บเฟรมล่าสุดที่จะส่ง (ขนาด 1 เพื่อลดอาการค้าง)
result_dict = {"boxes": []}  # เก็บกล่องข้อความจาก Server เพื่อนำมาวาด

def api_worker():
    """ส่งภาพไปที่ Server แบบเบื้องหลัง เพื่อให้วิดีโอทำงานลื่นไหล 30 FPS ตลอดเวลา"""
    while True:
        try:
            # ดึงภาพจากคิว (ถ้าไม่มีมันจะรอตรงนี้)
            frame_to_send = frame_queue.get()
            
            # บีบอัดเป็น JPEG เพื่อส่งเข้าเน็ต
            _, img_encoded = cv2.imencode('.jpg', frame_to_send, [cv2.IMWRITE_JPEG_QUALITY, 85])
            
            files = {"file": ("frame.jpg", img_encoded.tobytes(), "image/jpeg")}
            headers = {"X-API-Key": API_KEY}
            
            # ยิงขึ้น Server
            res = requests.post(API_URL, files=files, headers=headers, timeout=1.5)
            
            if res.status_code == 200:
                data = res.json()
                result_dict["boxes"] = data.get("detections", [])
            
            frame_queue.task_done()
        except requests.exceptions.RequestException:
            # เน็ตหลุดชั่วคราว ให้ข้ามไป ไม่ให้โปรแกรมแครช
            pass

# เริ่ม Thread ทันที
threading.Thread(target=api_worker, daemon=True).start()

# ============================================================
# Main Camera Loop (Motion Detection)
# ============================================================
cap = cv2.VideoCapture(CAMERA_SOURCE)
if not cap.isOpened():
    print("❌ Error: Cannot open camera.")
    exit(1)

# เตรียม Background (สำหรับจับความเคลื่อนไหว)
ret, first_frame = cap.read()
if ret:
    gray = cv2.cvtColor(first_frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)
    avg_bg = np.float32(gray)
else:
    avg_bg = None

last_send_time = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break

    now = time.time()
    motion_detected = False

    # 1. Motion Detection (ตรวจสอบความเคลื่อนไหว)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)

    if avg_bg is not None:
        # อัปเดตพื้นหลังอย่างช้าๆ ให้เข้ากับสภาพแสงที่เปลี่ยนไป
        cv2.accumulateWeighted(gray, avg_bg, 0.05)
        bg_uint8 = cv2.convertScaleAbs(avg_bg)

        # หาความแตกต่าง
        frame_diff = cv2.absdiff(bg_uint8, gray)
        thresh = cv2.threshold(frame_diff, 25, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)

        # นับพิกเซลความแตกต่าง
        motion_pixels = cv2.countNonZero(thresh)
        if motion_pixels > MOTION_THRESHOLD:
            motion_detected = True
    else:
        avg_bg = np.float32(gray)

    # 2. ถ้ารถขยับ & ถึงรอบส่งภาพ ก็สั่งส่งภาพ
    if motion_detected and (now - last_send_time) >= (1.0 / FPS_LIMIT):
        # ย่อขนาดเพื่อให้ส่งเน็ตได้ลื่นปรี๊ด
        h, w = frame.shape[:2]
        new_w = 640
        new_h = int((new_w / w) * h)
        small_frame = cv2.resize(frame, (new_w, new_h))
        
        # ยัดภาพใส่ Queue ไปให้ Background Thread จัดการ (ถ้าคิวไม่เต็ม)
        if not frame_queue.full():
            frame_queue.put(small_frame)
            last_send_time = now

    # 3. วาดผลลัพธ์ (สเกลพิกัดกลับเป็นขนาดเต็มจอ)
    h, w = frame.shape[:2]
    new_w = 640
    new_h = int((new_w / w) * h)
    scale_x = w / new_w
    scale_y = h / new_h
    
    # วาดกรอบรถ/ป้าย ที่ได้จาก Server
    for det in result_dict["boxes"]:
        if "vehicle_box" in det:
            bx1, by1, bx2, by2 = det["vehicle_box"]
            x1, y1 = int(bx1 * scale_x), int(by1 * scale_y)
            x2, y2 = int(bx2 * scale_x), int(by2 * scale_y)
            
            status = det.get("status", "")
            # สีเขียว = ตรวจจับอยู่ / สีแดง = ส่งเข้า Database ไปแล้ว
            color = (0, 0, 255) if status == "sent" else (0, 255, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            if "plate" in det and det["plate"]:
                cv2.putText(frame, f"{det['plate']}", (x1, max(0, y1 - 10)), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

    # วาดแจ้งเตือนว่ามีการเคลื่อนไหว
    if motion_detected:
        cv2.putText(frame, "MOTION DETECTED", (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

    # แสดงผลวิดีโอ (ลื่นไหลไม่มีกระตุก)
    cv2.imshow("Thin Client LPR (Async + Motion)", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
