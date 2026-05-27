# Plate - License Plate Recognition System

ระบบตรวจจับป้ายทะเบียนรถยนต์สำหรับงานเข้า-ออกพื้นที่ ประกอบด้วยหน้า Dashboard, Backend API และ AI service สำหรับอ่านป้ายทะเบียนจากกล้องหรือวิดีโอ

## ภาพรวม

โปรเจกต์นี้แบ่งออกเป็น 3 ส่วนหลัก:

- `frontend/` - Nuxt 4 + Vue dashboard สำหรับดูสถิติ, รายการรถ, กล้อง, parking และ logs
- `backend/` - Express + TypeScript API สำหรับจัดการข้อมูล, auth, logs, vehicle registry และ Socket.IO realtime event
- `ai_service/` - Python service ใช้ YOLOv8 + EasyOCR อ่านป้ายทะเบียนและส่งผลไปยัง Backend

## ฟีเจอร์หลัก

- Dashboard แสดงจำนวนรถเข้า-ออกและสถิติรายวัน
- จัดการทะเบียนรถ, ประเภทรถ, staff/internal/visitor
- จัดการกล้องและสถานะกล้อง
- บันทึก log การตรวจจับทะเบียน
- Export log เป็น Excel
- Realtime update ผ่าน Socket.IO
- รองรับ SQLite สำหรับ dev และ MySQL สำหรับ production
- AI service รองรับ webcam, video source หรือ RTSP stream

## โครงสร้างโปรเจกต์

```text
plate/
├── ai_service/      # Python LPR/OCR service
├── backend/         # Express + TypeScript API
├── frontend/        # Nuxt dashboard
├── .gitignore
└── README.md
```

## สิ่งที่ต้องมี

- Node.js 20+ แนะนำสำหรับ frontend/backend
- npm
- Python 3.10+ แนะนำสำหรับ AI service
- กล้อง webcam, video file หรือ RTSP stream ถ้าจะรันตรวจจับจริง
- MySQL เฉพาะกรณีต้องการใช้ฐานข้อมูล production

## Environment Variables

ไฟล์ `.env` ถูก ignore ไว้แล้ว ไม่ควร commit ขึ้น GitHub

### Backend

สร้างไฟล์ `backend/.env`

```env
PORT=3001
JWT_SECRET=change-this-secret

# sqlite หรือ mysql
DB_CLIENT=sqlite
SQLITE_FILENAME=./database.sqlite

# ใช้เมื่อ DB_CLIENT=mysql
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=
DB_NAME=lpr_db
```

### AI Service

สร้างไฟล์ `ai_service/.env`

```env
API_URL=http://localhost:3001/api/detect
CAMERA_ID=1
CAMERA_SOURCE=0
PLATE_MODEL_PATH=plate_detect.pt
```

หมายเหตุ:

- `CAMERA_SOURCE=0` คือ webcam ตัวแรก
- ใส่เป็น RTSP URL หรือ path video file ได้ เช่น `rtsp://...` หรือ `sample.mp4`
- `plate_detect.pt` เป็นโมเดลตรวจป้ายทะเบียนเสริม ถ้าไม่มี service จะใช้ fallback crop

## วิธีติดตั้งและรัน

### 1. Backend

```bash
cd backend
npm install
npm run dev
```

Backend จะรันที่:

```text
http://localhost:3001
```

ทดสอบ health check:

```text
http://localhost:3001/api/health
```

### 2. Frontend

เปิด terminal อีกหน้าหนึ่ง:

```bash
cd frontend
npm install
npm run dev
```

Frontend จะรันที่:

```text
http://localhost:3000
```

บัญชี demo:

```text
username: admin
password: admin
```

### 3. AI Service

เปิด terminal อีกหน้าหนึ่ง:

```bash
cd ai_service
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

บน macOS/Linux ใช้:

```bash
source venv/bin/activate
```

## การใช้ MySQL

ถ้าต้องการใช้ MySQL:

1. สร้าง database/table จากไฟล์ `backend/init.sql`
2. ตั้งค่า `backend/.env`

```env
DB_CLIENT=mysql
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your-password
DB_NAME=lpr_db
```

จากนั้นรัน backend ใหม่

## API หลัก

Backend มี endpoint หลักดังนี้:

- `GET /api/health`
- `/api/auth`
- `/api/vehicles`
- `/api/cameras`
- `/api/parking`
- `/api/logs`
- `/api/detect`

AI service จะส่งผลตรวจจับไปที่:

```text
POST /api/detect
```

payload ตัวอย่าง:

```json
{
  "plate_number": "กก1234",
  "confidence_score": 0.92,
  "camera_id": 1,
  "image_path": "optional/path.jpg"
}
```

## Build สำหรับ Production

### Frontend

```bash
cd frontend
npm run build
npm run preview
```

หรือ generate static:

```bash
npm run generate
```

### Backend

ตอนนี้ backend มี script หลักเป็น dev mode:

```bash
cd backend
npm run dev
```

ถ้าจะ deploy production แนะนำเพิ่ม build/start scripts สำหรับ TypeScript compilation ก่อนใช้งานจริง

## ไฟล์ที่ไม่ควร commit

โปรเจกต์นี้ตั้ง `.gitignore` กันไฟล์เหล่านี้ไว้แล้ว:

- `.env`, `.env.*`
- `node_modules/`
- `venv/`, `.venv/`
- `backend/database.sqlite`
- `ai_service/debug_plates/`
- `__pycache__/`
- log และ cache files

ถ้าต้องแชร์ค่าตัวอย่าง ให้สร้างไฟล์ `.env.example` แทน `.env`

## หมายเหตุด้านความปลอดภัย

- เปลี่ยน `JWT_SECRET` ก่อน deploy จริง
- เปลี่ยนบัญชี demo `admin/admin` ก่อนใช้งานจริง
- อย่า commit `.env`, database จริง, รูปทะเบียนจริง หรือข้อมูลส่วนบุคคลขึ้น GitHub
- ถ้าใช้กล้องจริงหรือ RTSP stream ควรเก็บ URL/credential ไว้ใน `.env`

## License

ยังไม่ได้ระบุ license
