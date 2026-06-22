/**
 * migrate.ts — Safe Database Migration for LPR v3
 *
 * Run: npx ts-node src/migrate.ts
 *
 * Idempotent: safe to run multiple times on existing databases.
 *
 * Adds to vehicle_logs:
 *   image_expire_at       DATETIME       (3-day retention expiry)
 *   processing_time_ms    INT DEFAULT 0
 *   image_quality_score   FLOAT DEFAULT 0
 *   quality_score         FLOAT DEFAULT 0  (client-side quality from Best Frame Window)
 *   track_id              VARCHAR(50)
 *   is_fuzzy_match        TINYINT DEFAULT 0
 *   original_ocr_text     VARCHAR(50)
 *
 * Adds to vehicles:
 *   is_blacklist          BOOLEAN DEFAULT FALSE
 *
 * Creates tables:
 *   vehicle_fingerprints  (visual fingerprint for anomaly detection)
 *
 * Adds indexes:
 *   idx_logs_created_at, idx_logs_plate, idx_logs_camera, idx_logs_expire
 */

import { pool } from './db';
import dotenv from 'dotenv';
dotenv.config();

const IS_MYSQL = (process.env.DB_CLIENT || 'sqlite') === 'mysql';

interface MigrationStep {
  name: string;
  sql:  string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Column additions (idempotent — errors on duplicate columns are swallowed)
// ─────────────────────────────────────────────────────────────────────────────
const COLUMN_MIGRATIONS: MigrationStep[] = [
  // vehicle_logs
  {
    name: 'vehicle_logs: Add image_expire_at',
    sql:  IS_MYSQL
      ? 'ALTER TABLE vehicle_logs ADD COLUMN image_expire_at DATETIME'
      : 'ALTER TABLE vehicle_logs ADD COLUMN image_expire_at DATETIME',
  },
  {
    name: 'vehicle_logs: Add processing_time_ms',
    sql:  IS_MYSQL
      ? 'ALTER TABLE vehicle_logs ADD COLUMN processing_time_ms INT DEFAULT 0'
      : 'ALTER TABLE vehicle_logs ADD COLUMN processing_time_ms INTEGER DEFAULT 0',
  },
  {
    name: 'vehicle_logs: Add image_quality_score',
    sql:  IS_MYSQL
      ? 'ALTER TABLE vehicle_logs ADD COLUMN image_quality_score FLOAT DEFAULT 0'
      : 'ALTER TABLE vehicle_logs ADD COLUMN image_quality_score REAL DEFAULT 0',
  },
  {
    name: 'vehicle_logs: Add quality_score (client Best Frame Window score)',
    sql:  IS_MYSQL
      ? 'ALTER TABLE vehicle_logs ADD COLUMN quality_score FLOAT DEFAULT 0'
      : 'ALTER TABLE vehicle_logs ADD COLUMN quality_score REAL DEFAULT 0',
  },
  {
    name: 'vehicle_logs: Add track_id',
    sql:  IS_MYSQL
      ? 'ALTER TABLE vehicle_logs ADD COLUMN track_id VARCHAR(50)'
      : 'ALTER TABLE vehicle_logs ADD COLUMN track_id TEXT',
  },
  {
    name: 'vehicle_logs: Add is_fuzzy_match',
    sql:  IS_MYSQL
      ? 'ALTER TABLE vehicle_logs ADD COLUMN is_fuzzy_match TINYINT(1) DEFAULT 0'
      : 'ALTER TABLE vehicle_logs ADD COLUMN is_fuzzy_match INTEGER DEFAULT 0',
  },
  {
    name: 'vehicle_logs: Add original_ocr_text',
    sql:  IS_MYSQL
      ? 'ALTER TABLE vehicle_logs ADD COLUMN original_ocr_text VARCHAR(50)'
      : 'ALTER TABLE vehicle_logs ADD COLUMN original_ocr_text TEXT',
  },
  // vehicles
  {
    name: 'vehicles: Add is_blacklist',
    sql:  IS_MYSQL
      ? 'ALTER TABLE vehicles ADD COLUMN is_blacklist TINYINT(1) NOT NULL DEFAULT 0'
      : 'ALTER TABLE vehicles ADD COLUMN is_blacklist INTEGER NOT NULL DEFAULT 0',
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Table creation (CREATE TABLE IF NOT EXISTS — always safe)
// ─────────────────────────────────────────────────────────────────────────────
const TABLE_MIGRATIONS: MigrationStep[] = [
  {
    name: 'Create camera_health table (30-day retention)',
    sql: IS_MYSQL
      ? `CREATE TABLE IF NOT EXISTS camera_health (
           id               INT AUTO_INCREMENT PRIMARY KEY,
           camera_id        INT NOT NULL,
           focus_score      FLOAT DEFAULT 0,
           brightness_score FLOAT DEFAULT 0,
           rain_detected    TINYINT(1) DEFAULT 0,
           camera_shift     TINYINT(1) DEFAULT 0,
           lens_dirty       TINYINT(1) DEFAULT 0,
           vibration        TINYINT(1) DEFAULT 0,
           blockage         TINYINT(1) DEFAULT 0,
           over_exposure    TINYINT(1) DEFAULT 0,
           under_exposure   TINYINT(1) DEFAULT 0,
           disk_usage       FLOAT DEFAULT 0,
           cpu_usage        FLOAT DEFAULT 0,
           memory_usage     FLOAT DEFAULT 0,
           status           VARCHAR(20) DEFAULT 'OK',
           recommendation   VARCHAR(255),
           created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
         ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`
      : `CREATE TABLE IF NOT EXISTS camera_health (
           id               INTEGER PRIMARY KEY AUTOINCREMENT,
           camera_id        INTEGER NOT NULL,
           focus_score      REAL DEFAULT 0,
           brightness_score REAL DEFAULT 0,
           rain_detected    INTEGER DEFAULT 0,
           camera_shift     INTEGER DEFAULT 0,
           lens_dirty       INTEGER DEFAULT 0,
           vibration        INTEGER DEFAULT 0,
           blockage         INTEGER DEFAULT 0,
           over_exposure    INTEGER DEFAULT 0,
           under_exposure   INTEGER DEFAULT 0,
           disk_usage       REAL DEFAULT 0,
           cpu_usage        REAL DEFAULT 0,
           memory_usage     REAL DEFAULT 0,
           status           TEXT DEFAULT 'OK',
           recommendation   TEXT,
           created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
         )`,
  },
  {
    name: 'Create audit_log table',
    sql: IS_MYSQL
      ? `CREATE TABLE IF NOT EXISTS audit_log (
           id         INT AUTO_INCREMENT PRIMARY KEY,
           camera_id  INT,
           event      VARCHAR(100) NOT NULL,
           severity   VARCHAR(20)  NOT NULL DEFAULT 'INFO',
           source     VARCHAR(100),
           action     VARCHAR(255),
           duration_ms INT,
           details    JSON,
           created_at DATETIME DEFAULT CURRENT_TIMESTAMP
         ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`
      : `CREATE TABLE IF NOT EXISTS audit_log (
           id         INTEGER PRIMARY KEY AUTOINCREMENT,
           camera_id  INTEGER,
           event      TEXT NOT NULL,
           severity   TEXT NOT NULL DEFAULT 'INFO',
           source     TEXT,
           action     TEXT,
           duration_ms INTEGER,
           details    TEXT,
           created_at DATETIME DEFAULT CURRENT_TIMESTAMP
         )`,
  },
  // ── Fleet management tables (v6) ─────────────────────────────────────────
  {
    name: 'Create sites table',
    sql: IS_MYSQL
      ? `CREATE TABLE IF NOT EXISTS sites (
           id         INT AUTO_INCREMENT PRIMARY KEY,
           site_name  VARCHAR(100) NOT NULL,
           address    TEXT,
           timezone   VARCHAR(50)  DEFAULT 'Asia/Bangkok',
           latitude   FLOAT        DEFAULT 0,
           longitude  FLOAT        DEFAULT 0,
           status     VARCHAR(20)  DEFAULT 'active',
           created_at DATETIME     DEFAULT CURRENT_TIMESTAMP
         ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`
      : `CREATE TABLE IF NOT EXISTS sites (
           id         INTEGER PRIMARY KEY AUTOINCREMENT,
           site_name  TEXT NOT NULL,
           address    TEXT,
           timezone   TEXT    DEFAULT 'Asia/Bangkok',
           latitude   REAL    DEFAULT 0,
           longitude  REAL    DEFAULT 0,
           status     TEXT    DEFAULT 'active',
           created_at DATETIME DEFAULT CURRENT_TIMESTAMP
         )`,
  },
  {
    name: 'Create devices table',
    sql: IS_MYSQL
      ? `CREATE TABLE IF NOT EXISTS devices (
           id               INT AUTO_INCREMENT PRIMARY KEY,
           device_id        VARCHAR(100) UNIQUE NOT NULL,
           serial           VARCHAR(100),
           hostname         VARCHAR(100),
           site_id          INT,
           os_info          VARCHAR(100),
           cpu_model        VARCHAR(100),
           ram_gb           FLOAT DEFAULT 0,
           disk_gb          FLOAT DEFAULT 0,
           ip_address       VARCHAR(45),
           mac_address      VARCHAR(20),
           software_version VARCHAR(50),
           camera_count     INT DEFAULT 1,
           status           VARCHAR(20) DEFAULT 'ONLINE',
           last_seen        DATETIME,
           created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
           FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE SET NULL
         ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`
      : `CREATE TABLE IF NOT EXISTS devices (
           id               INTEGER PRIMARY KEY AUTOINCREMENT,
           device_id        TEXT UNIQUE NOT NULL,
           serial           TEXT,
           hostname         TEXT,
           site_id          INTEGER,
           os_info          TEXT,
           cpu_model        TEXT,
           ram_gb           REAL DEFAULT 0,
           disk_gb          REAL DEFAULT 0,
           ip_address       TEXT,
           mac_address      TEXT,
           software_version TEXT,
           camera_count     INTEGER DEFAULT 1,
           status           TEXT DEFAULT 'ONLINE',
           last_seen        DATETIME,
           created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
           FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE SET NULL
         )`,
  },
  {
    name: 'Create model_registry table',
    sql: IS_MYSQL
      ? `CREATE TABLE IF NOT EXISTS model_registry (
           id           INT AUTO_INCREMENT PRIMARY KEY,
           model_name   VARCHAR(100) NOT NULL,
           model_version VARCHAR(50) NOT NULL,
           model_type   VARCHAR(50) DEFAULT 'vehicle',
           accuracy     FLOAT DEFAULT 0,
           file_path    VARCHAR(255),
           checksum     VARCHAR(64),
           is_active    TINYINT(1) DEFAULT 0,
           status       VARCHAR(20) DEFAULT 'staged',
           notes        TEXT,
           deployed_at  DATETIME,
           created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
         ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`
      : `CREATE TABLE IF NOT EXISTS model_registry (
           id            INTEGER PRIMARY KEY AUTOINCREMENT,
           model_name    TEXT NOT NULL,
           model_version TEXT NOT NULL,
           model_type    TEXT DEFAULT 'vehicle',
           accuracy      REAL DEFAULT 0,
           file_path     TEXT,
           checksum      TEXT,
           is_active     INTEGER DEFAULT 0,
           status        TEXT DEFAULT 'staged',
           notes         TEXT,
           deployed_at   DATETIME,
           created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
         )`,
  },
  {
    name: 'Create vehicle_fingerprints table',
    sql: IS_MYSQL
      ? `CREATE TABLE IF NOT EXISTS vehicle_fingerprints (
           id            INT AUTO_INCREMENT PRIMARY KEY,
           vehicle_id    INT NOT NULL,
           fingerprint   LONGTEXT NOT NULL,
           vehicle_color VARCHAR(100),
           created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
           FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
         ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci`
      : `CREATE TABLE IF NOT EXISTS vehicle_fingerprints (
           id            INTEGER PRIMARY KEY AUTOINCREMENT,
           vehicle_id    INTEGER NOT NULL,
           fingerprint   TEXT NOT NULL,
           vehicle_color TEXT,
           created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
           FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
         )`,
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Index creation (CREATE INDEX IF NOT EXISTS — always safe)
// ─────────────────────────────────────────────────────────────────────────────
const INDEX_MIGRATIONS: MigrationStep[] = [
  {
    name: 'Index vehicle_logs.created_at',
    sql:  'CREATE INDEX IF NOT EXISTS idx_logs_created_at ON vehicle_logs(created_at)',
  },
  {
    name: 'Index vehicle_logs.plate_number',
    sql:  'CREATE INDEX IF NOT EXISTS idx_logs_plate ON vehicle_logs(plate_number)',
  },
  {
    name: 'Index vehicle_logs.camera_id',
    sql:  'CREATE INDEX IF NOT EXISTS idx_logs_camera ON vehicle_logs(camera_id)',
  },
  {
    name: 'Index vehicle_logs.image_expire_at (cleanup performance)',
    sql:  'CREATE INDEX IF NOT EXISTS idx_logs_expire ON vehicle_logs(image_expire_at)',
  },
  {
    name: 'Index vehicle_fingerprints.vehicle_id',
    sql:  'CREATE INDEX IF NOT EXISTS idx_fp_vehicle ON vehicle_fingerprints(vehicle_id)',
  },
  {
    name: 'Index camera_health.camera_id + created_at',
    sql:  'CREATE INDEX IF NOT EXISTS idx_cam_health ON camera_health(camera_id, created_at)',
  },
  {
    name: 'Index devices.device_id',
    sql:  'CREATE INDEX IF NOT EXISTS idx_devices_id ON devices(device_id)',
  },
  {
    name: 'Index devices.site_id',
    sql:  'CREATE INDEX IF NOT EXISTS idx_devices_site ON devices(site_id)',
  },
  {
    name: 'Index model_registry.is_active',
    sql:  'CREATE INDEX IF NOT EXISTS idx_models_active ON model_registry(is_active)',
  },
  {
    name: 'Index audit_log.created_at',
    sql:  'CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at)',
  },
  {
    name: 'Index audit_log.severity',
    sql:  'CREATE INDEX IF NOT EXISTS idx_audit_severity ON audit_log(severity)',
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
async function runSafeAlter(step: MigrationStep): Promise<void> {
  try {
    await pool.query(step.sql);
    console.log(`  ✅ ${step.name}`);
  } catch (err: any) {
    const msg = (err?.message || '').toLowerCase();
    if (
      msg.includes('duplicate column') ||
      msg.includes('already exists') ||
      msg.includes('already have a column')
    ) {
      console.log(`  ⏭  ${step.name} (already exists — skipped)`);
    } else {
      console.warn(`  ⚠️  ${step.name} failed: ${err.message}`);
    }
  }
}

async function runAlways(step: MigrationStep): Promise<void> {
  try {
    await pool.query(step.sql);
    console.log(`  ✅ ${step.name}`);
  } catch (err: any) {
    console.warn(`  ⚠️  ${step.name} failed: ${err?.message}`);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Main
// ─────────────────────────────────────────────────────────────────────────────
async function migrate(): Promise<void> {
  console.log(`\n🛠  LPR Database Migration v3`);
  console.log(`   DB: ${IS_MYSQL ? 'MySQL' : 'SQLite'}\n`);

  console.log('📋 Table migrations:');
  for (const step of TABLE_MIGRATIONS) {
    await runAlways(step);
  }

  console.log('\n📋 Column migrations:');
  for (const step of COLUMN_MIGRATIONS) {
    await runSafeAlter(step);
  }

  console.log('\n📑 Index migrations:');
  for (const step of INDEX_MIGRATIONS) {
    await runAlways(step);
  }

  console.log('\n✅ Migration v4 complete.\n');
  process.exit(0);
}

migrate().catch((err) => {
  console.error('Migration failed:', err);
  process.exit(1);
});
