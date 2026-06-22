CREATE DATABASE IF NOT EXISTS lpr_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE lpr_db;

-- 1. Registered Vehicles (whitelist / blacklist)
CREATE TABLE IF NOT EXISTS vehicles (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  plate_number  VARCHAR(20) UNIQUE NOT NULL,
  province      VARCHAR(50),
  plate_type    VARCHAR(50),
  vehicle_type  VARCHAR(50),
  is_staff      BOOLEAN NOT NULL DEFAULT FALSE,
  is_internal   BOOLEAN NOT NULL DEFAULT FALSE,
  is_blacklist  BOOLEAN NOT NULL DEFAULT FALSE,
  owner_name    VARCHAR(100),
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Cameras
CREATE TABLE IF NOT EXISTS cameras (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  name        VARCHAR(100) NOT NULL,
  location    VARCHAR(100),
  ip_address  VARCHAR(50),
  stream_url  VARCHAR(255),
  status      VARCHAR(20) DEFAULT 'Online',
  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Detection Logs
CREATE TABLE IF NOT EXISTS vehicle_logs (
  id                   INT AUTO_INCREMENT PRIMARY KEY,
  plate_number         VARCHAR(20) NOT NULL,
  vehicle_id           INT NULL,
  camera_id            INT,
  direction            VARCHAR(20),
  confidence_score     FLOAT DEFAULT 0,
  image_quality_score  FLOAT DEFAULT 0,
  quality_score        FLOAT DEFAULT 0,
  processing_time_ms   INT DEFAULT 0,
  track_id             VARCHAR(50),
  is_fuzzy_match       TINYINT(1) NOT NULL DEFAULT 0,
  original_ocr_text    VARCHAR(50),
  image_path           VARCHAR(255),
  image_expire_at      DATETIME,
  created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Vehicle Visual Fingerprints (anomaly detection)
CREATE TABLE IF NOT EXISTS vehicle_fingerprints (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  vehicle_id    INT NOT NULL,
  fingerprint   LONGTEXT NOT NULL,
  vehicle_color VARCHAR(100),
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Parking Sessions
CREATE TABLE IF NOT EXISTS parking_sessions (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  plate_number VARCHAR(20) NOT NULL,
  vehicle_id   INT NULL,
  camera_in    INT,
  camera_out   INT,
  entry_time   DATETIME,
  exit_time    DATETIME,
  duration_min INT,
  created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. Indexes (performance)
CREATE INDEX IF NOT EXISTS idx_logs_created_at ON vehicle_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_logs_plate      ON vehicle_logs(plate_number);
CREATE INDEX IF NOT EXISTS idx_logs_camera     ON vehicle_logs(camera_id);
CREATE INDEX IF NOT EXISTS idx_logs_expire     ON vehicle_logs(image_expire_at);
CREATE INDEX IF NOT EXISTS idx_fp_vehicle      ON vehicle_fingerprints(vehicle_id);
