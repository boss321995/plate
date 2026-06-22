/**
 * cleanupJob.ts — Scheduled Image Cleanup (3-day retention)
 *
 * Runs at 02:00 AM every day.
 * Deletes image files whose image_expire_at < NOW()
 * and nullifies image_path in vehicle_logs.
 *
 * Also cleans up stale track vote data older than 24h.
 */

import fs from 'fs';
import path from 'path';
import { pool } from './db';

// ─────────────────────────────────────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────────────────────────────────────
const LOGS_BASE_DIR  = path.join(__dirname, '..', 'logs');
const RETENTION_DAYS = parseInt(process.env.IMAGE_RETENTION_DAYS || '3', 10);
const CLEANUP_HOUR   = parseInt(process.env.CLEANUP_HOUR || '2', 10);  // 2 AM
const DRY_RUN        = process.env.CLEANUP_DRY_RUN === 'true';

let cleanupTimer: NodeJS.Timeout | null = null;

// ─────────────────────────────────────────────────────────────────────────────
// File deletion helper
// ─────────────────────────────────────────────────────────────────────────────
function deleteFile(filePath: string): boolean {
  try {
    if (DRY_RUN) {
      console.log(`[Cleanup][DRY_RUN] Would delete: ${filePath}`);
      return true;
    }
    if (fs.existsSync(filePath)) {
      fs.unlinkSync(filePath);
      return true;
    }
    return false;   // Already gone
  } catch (err: any) {
    console.error(`[Cleanup] Failed to delete ${filePath}: ${err.message}`);
    return false;
  }
}

// Remove empty directories recursively upward
function pruneEmptyDirs(dir: string): void {
  if (!fs.existsSync(dir) || dir === LOGS_BASE_DIR) return;
  try {
    const items = fs.readdirSync(dir);
    if (items.length === 0) {
      if (!DRY_RUN) fs.rmdirSync(dir);
      pruneEmptyDirs(path.dirname(dir));
    }
  } catch (_) { /* ignore */ }
}

// ─────────────────────────────────────────────────────────────────────────────
// Main cleanup job
// ─────────────────────────────────────────────────────────────────────────────
export async function runCleanup(): Promise<void> {
  const jobStart = Date.now();
  console.log(`\n[Cleanup] ▶ Starting cleanup job at ${new Date().toISOString()}`);
  console.log(`[Cleanup]   Retention: ${RETENTION_DAYS} days | DRY_RUN: ${DRY_RUN}`);

  let deletedFiles = 0;
  let deletedRows  = 0;
  let errorCount   = 0;

  try {
    // ── 1. Find expired image records ──────────────────────────────────────
    const now    = new Date().toISOString();
    const [rows] = await pool.query(
      `SELECT id, image_path, plate_number, track_id
       FROM vehicle_logs
       WHERE image_expire_at IS NOT NULL
         AND image_expire_at < ?
         AND image_path IS NOT NULL`,
      [now]
    ) as any[];

    const expiredRows = Array.isArray(rows) ? rows : [];
    console.log(`[Cleanup]   Found ${expiredRows.length} expired image record(s)`);

    const expiredIds: number[] = [];

    for (const row of expiredRows) {
      const { id, image_path, plate_number } = row;

      if (image_path) {
        // image_path stored relative to LOGS_BASE_DIR
        const abs = path.isAbsolute(image_path)
          ? image_path
          : path.join(LOGS_BASE_DIR, image_path);

        const deleted = deleteFile(abs);
        if (deleted) {
          deletedFiles++;
          pruneEmptyDirs(path.dirname(abs));
          console.log(`[Cleanup]   🗑  Deleted: ${abs} (plate: ${plate_number})`);
        }
      }

      expiredIds.push(id);
    }

    // ── 2. Update DB: nullify image_path & clear expire date ───────────────
    if (expiredIds.length > 0 && !DRY_RUN) {
      const placeholders = expiredIds.map(() => '?').join(',');
      await pool.query(
        `UPDATE vehicle_logs
         SET image_path = NULL, image_expire_at = NULL
         WHERE id IN (${placeholders})`,
        expiredIds
      );
      deletedRows = expiredIds.length;
      console.log(`[Cleanup]   ✅ Updated ${deletedRows} DB record(s)`);
    }

    // ── 3. Scan filesystem for orphan files not in DB ──────────────────────
    // (Safety net: files that somehow lost their DB reference)
    const cutoff = new Date(Date.now() - RETENTION_DAYS * 24 * 60 * 60 * 1000);
    let orphans  = 0;

    function scanDir(dir: string): void {
      if (!fs.existsSync(dir)) return;
      const entries = fs.readdirSync(dir, { withFileTypes: true });
      for (const entry of entries) {
        const entryPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          scanDir(entryPath);
          pruneEmptyDirs(entryPath);
        } else if (entry.name.endsWith('.jpg') || entry.name.endsWith('.jpeg')) {
          const stat = fs.statSync(entryPath);
          if (stat.mtime < cutoff) {
            const deleted = deleteFile(entryPath);
            if (deleted) orphans++;
          }
        }
      }
    }

    scanDir(LOGS_BASE_DIR);
    if (orphans > 0) {
      console.log(`[Cleanup]   🧹 Removed ${orphans} orphan file(s) from filesystem`);
    }

  } catch (err: any) {
    errorCount++;
    console.error(`[Cleanup] ✗ Error:`, err.message);
  }

  const ms = Date.now() - jobStart;
  console.log(
    `[Cleanup] ◀ Done in ${ms}ms | ` +
    `files=${deletedFiles} | db_rows=${deletedRows} | errors=${errorCount}\n`
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Scheduler: runs at CLEANUP_HOUR every day
// ─────────────────────────────────────────────────────────────────────────────
function msUntilNextRun(targetHour: number): number {
  const now  = new Date();
  const next = new Date(now);
  next.setHours(targetHour, 0, 0, 0);
  if (next <= now) {
    next.setDate(next.getDate() + 1);
  }
  return next.getTime() - now.getTime();
}

export function startCleanupScheduler(): void {
  const scheduleNext = (): void => {
    const delay = msUntilNextRun(CLEANUP_HOUR);
    const hours = Math.round(delay / 3600000 * 10) / 10;
    console.log(`[Cleanup] ⏰ Next run in ~${hours}h (at ${CLEANUP_HOUR}:00 AM)`);

    cleanupTimer = setTimeout(async () => {
      await runCleanup();
      scheduleNext();   // Schedule next occurrence
    }, delay);
  };

  scheduleNext();
}

export function stopCleanupScheduler(): void {
  if (cleanupTimer) {
    clearTimeout(cleanupTimer);
    cleanupTimer = null;
    console.log('[Cleanup] Scheduler stopped.');
  }
}
