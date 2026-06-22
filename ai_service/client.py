import cv2
import requests
import time
import os

API_URL = os.getenv("API_URL", "http://100.127.92.120/api/plate/ai/detect_frame")
API_KEY = os.getenv("API_KEY", "PLATE-AI-KEY-totacademy-2026")
CAMERA_SOURCE = 0
FPS_LIMIT = 5  # ส่งภาพสูงสุด 5 ภาพต่อวินาที (ประหยัดเน็ต)

print(f"🚀 Starting Thin Client LPR...")
print(f"📡 Sending to: {API_URL}")
print(f"📸 FPS Limit: {FPS_LIMIT}")

cap = cv2.VideoCapture(CAMERA_SOURCE)

if not cap.isOpened():
    print("❌ Error: Cannot open camera.")
    exit(1)

last_send_time = 0
boxes_to_draw = []

while True:
    ret, frame = cap.read()
    if not ret:
        break

    now = time.time()
    
    # ส่งภาพเมื่อถึงเวลา (FPS Limiter)
    if (now - last_send_time) >= (1.0 / FPS_LIMIT):
        # 1. ย่อขนาดภาพเป็น 640px ช่วยให้ส่งผ่านเน็ตเร็วขึ้นมากๆ
        h, w = frame.shape[:2]
        new_w = 640
        new_h = int((new_w / w) * h)
        small_frame = cv2.resize(frame, (new_w, new_h))
        
        # 2. บีบอัดเป็น JPEG (Quality 85%)
        _, img_encoded = cv2.imencode('.jpg', small_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        
        # 3. ส่งเข้า Server (ไม่ต้องเซฟลงดิสก์)
        try:
            files = {"file": ("frame.jpg", img_encoded.tobytes(), "image/jpeg")}
            headers = {"X-API-Key": API_KEY}
            
            # ใช้ Timeout ต่ำๆ เพื่อไม่ให้วิดีโอค้างถ้ารอเน็ตนาน
            res = requests.post(API_URL, files=files, headers=headers, timeout=0.8)
            
            if res.status_code == 200:
                data = res.json()
                boxes_to_draw = data.get("detections", [])
        except requests.exceptions.RequestException as e:
            pass # ถ้าเน็ตหลุด/ช้า ก็ปล่อยผ่านไป เพื่อให้วิดีโอยังเล่นต่อได้ลื่นๆ
            
        last_send_time = now

    # วาดกรอบที่ได้รับตอบกลับมาจาก Server (ต้องขยายพิกัดกลับ เพราะตอนส่งเราส่งแบบย่อ)
    h, w = frame.shape[:2]
    new_w = 640
    new_h = int((new_w / w) * h)
    scale_x = w / new_w
    scale_y = h / new_h
    
    for det in boxes_to_draw:
        if "vehicle_box" in det:
            bx1, by1, bx2, by2 = det["vehicle_box"]
            x1, y1 = int(bx1 * scale_x), int(by1 * scale_y)
            x2, y2 = int(bx2 * scale_x), int(by2 * scale_y)
            
            status = det.get("status", "")
            
            # สีเขียว = เจอรถกำลังสแกน / สีแดง = สแกนเจอป้ายแล้ว
            color = (0, 0, 255) if status == "sent" else (0, 255, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            if "plate" in det and det["plate"]:
                text = f"{det['plate']}"
                # วาดข้อความอังกฤษง่ายๆ บนจอ (ถ้าอยากได้ไทยต้องใช้ PIL แต่เปลือง CPU บน Client)
                cv2.putText(frame, text, (x1, max(0, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

    cv2.imshow("Thin Client LPR (Cloud AI)", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
