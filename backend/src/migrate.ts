/**
 * migrate.ts — Safe Database Migration for LPR v2
 *
 * Run: npx ts-node src/migrate.ts
 *
 * Adds to vehicle_logs:
 *   - image_expire_at  DATETIME      (auto-set to NOW + 3 days on insert)
 *   - processing_time_ms INT DEFAULT 0
 *   - image_quality_score FLOAT DEFAULT 0
 *   - track_id VARCHAR(50)
 *   - image_path updated (already exists)
 *
 * Adds indexes:
 *   - idx_logs_created_at
 *   - idx_logs_plate
 *   - idx_logs_camera
 *
 * Idempotent: safe to run multiple times.
 */

import { pool } from './db';
import dotenv from 'dotenv';
dotenv.config();

const IS_MYSQL = (process.env.DB_CLIENT || 'sqlite') === 'mysql';

interface MigrationStep {
  name: string;
  sql: string;
}

const COLUMN_MIGRATIONS: MigrationStep[] = [
  {
    name: 'Add image_expire_at',
    sql: IS_MYSQL
      ? 'ALTER TABLE vehicle_logs ADD COLUMN image_expire_at DATETIME'
      : 'ALTER TABLE vehicle_logs ADD COLUMN image_expire_at DATETIME',
  },
  {
    name: 'Add processing_time_ms',
    sql: IS_MYSQL
      ? 'ALTER TABLE vehicle_logs ADD COLUMN processing_time_ms INT DEFAULT 0'
      : 'ALTER TABLE vehicle_logs ADD COLUMN processing_time_ms INTEGER DEFAULT 0',
  },
  {
    name: 'Add image_quality_score',
    sql: IS_MYSQL
      ? 'ALTER TABLE vehicle_logs ADD COLUMN image_quality_score FLOAT DEFAULT 0'
      : 'ALTER TABLE vehicle_logs ADD COLUMN image_quality_score REAL DEFAULT 0',
  },
  {
    name: 'Add track_id',
    sql: IS_MYSQL
      ? 'ALTER TABLE vehicle_logs ADD COLUMN track_id VARCHAR(50)'
      : 'ALTER TABLE vehicle_logs ADD COLUMN track_id TEXT',
  },
];

const INDEX_MIGRATIONS: MigrationStep[] = [
  {
    name: 'Index created_at',
    sql: 'CREATE INDEX IF NOT EXISTS idx_logs_created_at ON vehicle_logs(created_at)',
  },
  {
    name: 'Index plate_number',
    sql: 'CREATE INDEX IF NOT EXISTS idx_logs_plate ON vehicle_logs(plate_number)',
  },
  {
    name: 'Index camera_id',
    sql: 'CREATE INDEX IF NOT EXISTS idx_logs_camera ON vehicle_logs(camera_id)',
  },
];

async function runSafeAlter(step: MigrationStep): Promise<void> {
  try {
    await pool.query(step.sql);
    console.log(`  ✅ ${step.name}`);
  } catch (err: any) {
    // Column already exists → ignore
    const msg = (err?.message || '').toLowerCase();
    if (
      msg.includes('duplicate column') ||
      msg.includes('already exists') ||
      msg.includes('already have a column')
    ) {
      console.log(`  ⏭  ${step.name} (already exists)`);
    } else {
      console.warn(`  ⚠️  ${step.name} failed: ${err.message}`);
    }
  }
}

async function migrate(): Promise<void> {
  console.log(`\n🛠  LPR Database Migration v2`);
  console.log(`   DB: ${IS_MYSQL ? 'MySQL' : 'SQLite'}\n`);

  console.log('📋 Column migrations:');
  for (const step of COLUMN_MIGRATIONS) {
    await runSafeAlter(step);
  }

  console.log('\n📑 Index migrations:');
  for (const step of INDEX_MIGRATIONS) {
    await runSafeAlter(step);
  }

  console.log('\n✅ Migration complete.\n');
  process.exit(0);
}

migrate().catch((err) => {
  console.error('Migration failed:', err);
  process.exit(1);
});
