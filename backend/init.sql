CREATE DATABASE IF NOT EXISTS lpr_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE lpr_db;

-- 1. Table for Whitelist / Registered Vehicles
CREATE TABLE IF NOT EXISTS vehicles (
  id INT AUTO_INCREMENT PRIMARY KEY,
  plate_number VARCHAR(20) UNIQUE NOT NULL,
  province VARCHAR(50),
  plate_type VARCHAR(50),
  vehicle_type VARCHAR(50),
  is_staff BOOLEAN DEFAULT FALSE,
  is_internal BOOLEAN DEFAULT FALSE,
  owner_name VARCHAR(100),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Table for Cameras
CREATE TABLE IF NOT EXISTS cameras (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  location VARCHAR(100),
  ip_address VARCHAR(50),
  stream_url VARCHAR(255),
  status VARCHAR(20) DEFAULT 'Online',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Table for Detection Logs
CREATE TABLE IF NOT EXISTS vehicle_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  plate_number VARCHAR(20) NOT NULL,
  vehicle_id INT NULL,
  camera_id INT,
  direction VARCHAR(20),
  confidence_score FLOAT,
  image_path VARCHAR(255),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
