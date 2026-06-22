import { Request, Response } from 'express';
import { pool } from '../db';
import { getIo } from '../socket';
import path from 'path';
import fs from 'fs';

// ─────────────────────────────────────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────────────────────────────────────
// Part 9: duplicate suppression window — 30 seconds per plate+camera pair
const COOLDOWN_TIME_MS     = parseInt(process.env.DUPLICATE_COOLDOWN_MS || '30000', 10);
const IMAGE_RETENTION_DAYS = parseInt(process.env.IMAGE_RETENTION_DAYS  || '3',     10);
const LOGS_BASE_DIR        = path.join(__dirname, '..', '..', 'logs');

// In-memory cooldown: "plate:camera_id" → last-seen timestamp
const cooldownCache = new Map<string, number>();

// Plate fuzzy cache (refreshed every 60s)
let plateCache: {
  id:           number;
  plate_number: string;
  is_staff:     boolean;
  is_internal:  boolean;
  is_blacklist: boolean;
}[] = [];
let plateCacheTime = 0;
const PLATE_CACHE_TTL = 60_000;

fs.mkdirSync(LOGS_BASE_DIR, { recursive: true });

// ─────────────────────────────────────────────────────────────────────────────
// Levenshtein distance (fuzzy plate matching)
// ─────────────────────────────────────────────────────────────────────────────
function levenshteinDistance(a: string, b: string): number {
  const m = a.length, n = b.length;
  const dp: number[][] = [];
  for (let i = 0; i <= m; i++) dp.push(new Array(n + 1).fill(0));
  for (let i = 0; i <= m; i++) dp[i]![0] = i;
  for (let j = 0; j <= n; j++) dp[0]![j] = j;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i]![j] = a[i - 1] === b[j - 1]
        ? dp[i - 1]![j - 1]!
        : 1 + Math.min(dp[i - 1]![j]!, dp[i]![j - 1]!, dp[i - 1]![j - 1]!);
    }
  }
  return dp[m]![n]!;
}

async function refreshPlateCache() {
  const now = Date.now();
  if (now - plateCacheTime < PLATE_CACHE_TTL && plateCache.length > 0) return;
  try {
    const [rows]: any = await pool.query(
      'SELECT id, plate_number, is_staff, is_internal, is_blacklist FROM vehicles'
    );
    plateCache     = rows;
    plateCacheTime = now;
  } catch (e) {
    console.error('[FuzzyCache] Failed:', e);
  }
}

function fuzzyMatchPlate(ocrPlate: string) {
  if (!plateCache.length) return null;
  let bestMatch: any = null, bestDist = Infinity, bestPlate = '';
  for (const v of plateCache) {
    const dist = levenshteinDistance(ocrPlate, v.plate_number);
    if (dist < bestDist) {
      bestDist = dist; bestMatch = v; bestPlate = v.plate_number;
    }
  }
  if (bestDist > 0 && bestDist <= 2 && ocrPlate.length >= 3) {
    return { vehicle: bestMatch, matched_plate: bestPlate, distance: bestDist };
  }
  return null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Anomaly Detection (Cosine Similarity on vehicle fingerprint)
// ─────────────────────────────────────────────────────────────────────────────
function cosineSimilarity(a: number[], b: number[]): number {
  if (!a || !b || a.length !== b.length || a.length === 0) return 0;
  let dot = 0, magA = 0, magB = 0;
  for (let i = 0; i < a.length; i++) {
    dot  += a[i]! * b[i]!;
    magA += a[i]! * a[i]!;
    magB += b[i]! * b[i]!;
  }
  const denom = Math.sqrt(magA) * Math.sqrt(magB);
  return denom === 0 ? 0 : dot / denom;
}

// ─────────────────────────────────────────────────────────────────────────────
// Part 11 (backend): Evidence image storage → logs/YYYY/MM/DD/
// ─────────────────────────────────────────────────────────────────────────────
async function saveEvidenceImage(
  imageBase64: string | undefined,
  plateNumber: string,
): Promise<string | null> {
  if (!imageBase64) return null;
  try {
    const now      = new Date();
    const yyyy     = now.getFullYear().toString();
    const mm       = (now.getMonth() + 1).toString().padStart(2, '0');
    const dd       = now.getDate().toString().padStart(2, '0');
    const dir      = path.join(LOGS_BASE_DIR, yyyy, mm, dd);
    fs.mkdirSync(dir, { recursive: true });

    const ts        = now.toISOString().replace(/[:.]/g, '').slice(0, 15);
    const safePlate = plateNumber.replace(/[^a-zA-Z0-9ก-ฮ]/g, '_');
    const filename  = `${ts}_${safePlate}.jpg`;
    const filepath  = path.join(dir, filename);

    const base64Data = imageBase64.replace(/^data:image\/\w+;base64,/, '');
    fs.writeFileSync(filepath, Buffer.from(base64Data, 'base64'));

    return path.join(yyyy, mm, dd, filename);
  } catch (err: any) {
    console.error('[Detection] Evidence image save failed:', err.message);
    return null;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Detection Handler
// ─────────────────────────────────────────────────────────────────────────────
export const handleDetection = async (req: Request, res: Response) => {
  try {
    const {
      plate_number,
      province,
      confidence_score,
      camera_id,
      image_path,
      image_base64,
      vehicle_color,
      vehicle_fingerprint,
      processing_time_ms,
      image_quality_score,
      quality_score,          // client-side Best Frame Window score
      track_id,
      direction: payloadDir,  // direction from AI virtual line detection
    } = req.body;

    if (!plate_number) {
      res.status(400).json({ success: false, message: 'plate_number is required' });
      return;
    }

    // ── Part 9: Duplicate Suppression (30s per plate+camera pair) ─────────────
    const now       = Date.now();
    const cacheKey  = `${plate_number}:${camera_id || 1}`;
    const lastSeen  = cooldownCache.get(cacheKey);

    if (lastSeen && (now - lastSeen) < COOLDOWN_TIME_MS) {
      const elapsed = Math.round((now - lastSeen) / 1000);
      console.log(`[Duplicate] Ignored ${plate_number} (${elapsed}s ago, cooldown ${COOLDOWN_TIME_MS / 1000}s)`);
      res.status(200).json({ success: true, message: 'Ignored: duplicate within cooldown' });
      return;
    }
    cooldownCache.set(cacheKey, now);

    // Prune expired cooldown entries to prevent memory leak
    if (cooldownCache.size > 1000) {
      for (const [k, t] of cooldownCache.entries()) {
        if (now - t > COOLDOWN_TIME_MS) cooldownCache.delete(k);
      }
    }

    // ── Part 10: Direction — prefer payload from virtual line, fallback camera heuristic
    const direction = payloadDir || ((camera_id === 2 || camera_id === '2') ? 'OUT' : 'IN');

    // ── Fuzzy plate lookup ────────────────────────────────────────────────────
    let vehicleId    = null;
    let isStaff      = false;
    let isInternal   = false;
    let isBlacklist  = false;
    let isFuzzyMatch = false;
    let originalOcr  = plate_number;
    let resolvedPlate = plate_number;

    await refreshPlateCache();

    const [vehicleRows]: any = await pool.query(
      'SELECT id, is_staff, is_internal, is_blacklist FROM vehicles WHERE plate_number = ? LIMIT 1',
      [plate_number]
    );

    if (vehicleRows.length > 0) {
      vehicleId   = vehicleRows[0].id;
      isStaff     = !!vehicleRows[0].is_staff;
      isInternal  = !!vehicleRows[0].is_internal;
      isBlacklist = !!vehicleRows[0].is_blacklist;
    } else {
      const fuzzy = fuzzyMatchPlate(plate_number);
      if (fuzzy) {
        vehicleId     = fuzzy.vehicle.id;
        isStaff       = !!fuzzy.vehicle.is_staff;
        isInternal    = !!fuzzy.vehicle.is_internal;
        isBlacklist   = !!fuzzy.vehicle.is_blacklist;
        isFuzzyMatch  = true;
        originalOcr   = plate_number;
        resolvedPlate = fuzzy.matched_plate;
        console.log(`[Fuzzy] "${plate_number}" → "${resolvedPlate}" (d=${fuzzy.distance})`);
      }
    }

    const vehicleTypeLabel = isBlacklist ? 'BLACKLIST'
      : (isStaff ? 'STAFF' : (isInternal ? 'INTERNAL' : 'VISITOR'));

    console.log(
      `[Detection] ${resolvedPlate} | ${vehicleTypeLabel} | ${direction}` +
      (isFuzzyMatch ? ' [FUZZY]' : '') +
      (track_id     ? ` | ${track_id}` : '')
    );

    // ── Evidence image storage ────────────────────────────────────────────────
    let storedImagePath: string | null = image_path || null;
    if (image_base64 && !storedImagePath) {
      storedImagePath = await saveEvidenceImage(image_base64, resolvedPlate);
    }

    // ── image_expire_at = NOW + IMAGE_RETENTION_DAYS ─────────────────────────
    const expireAt = storedImagePath
      ? new Date(Date.now() + IMAGE_RETENTION_DAYS * 24 * 60 * 60 * 1000).toISOString()
      : null;

    // ── Insert log ────────────────────────────────────────────────────────────
    const [insertResult]: any = await pool.query(
      `INSERT INTO vehicle_logs
         (plate_number, vehicle_id, camera_id, direction,
          confidence_score, image_quality_score, quality_score,
          processing_time_ms, track_id,
          is_fuzzy_match, original_ocr_text,
          image_path, image_expire_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        resolvedPlate,
        vehicleId,
        camera_id || 1,
        direction,
        confidence_score      || 0,
        image_quality_score   || 0,
        quality_score         || 0,
        processing_time_ms    || 0,
        track_id              || null,
        isFuzzyMatch ? 1 : 0,
        isFuzzyMatch ? originalOcr : null,
        storedImagePath,
        expireAt,
      ]
    );

    // ── Fingerprint anomaly detection ─────────────────────────────────────────
    let isAnomaly      = false;
    let anomalyMessage = '';

    if (vehicleId && vehicle_fingerprint &&
        Array.isArray(vehicle_fingerprint) && vehicle_fingerprint.length > 0) {
      try {
        const [prevRows]: any = await pool.query(
          'SELECT fingerprint, vehicle_color FROM vehicle_fingerprints WHERE vehicle_id = ? ORDER BY id DESC LIMIT 5',
          [vehicleId]
        );
        if (prevRows.length > 0) {
          const prevFps: number[][] = prevRows
            .map((r: any) => { try { return JSON.parse(r.fingerprint); } catch { return null; } })
            .filter(Boolean);

          if (prevFps.length > 0) {
            const avgFp = prevFps[0]!.map((_: number, i: number) =>
              prevFps.reduce((s, fp) => s + fp[i]!, 0) / prevFps.length
            );
            const similarity = cosineSimilarity(avgFp, vehicle_fingerprint);
            const prevColor  = prevRows[0].vehicle_color;
            const colorMatch = !prevColor || !vehicle_color || prevColor === vehicle_color;

            if (similarity < 0.65 && !colorMatch) {
              isAnomaly = true;
              anomalyMessage =
                `รถป้าย ${resolvedPlate} หน้าตาไม่เหมือนเดิม! ` +
                `(สีเดิม: ${prevColor}, สีใหม่: ${vehicle_color}, ` +
                `ความคล้าย: ${(similarity * 100).toFixed(0)}%)`;
              console.warn(`[ANOMALY] ${anomalyMessage}`);
            }
          }
        }
        await pool.query(
          'INSERT INTO vehicle_fingerprints (vehicle_id, fingerprint, vehicle_color) VALUES (?, ?, ?)',
          [vehicleId, JSON.stringify(vehicle_fingerprint), vehicle_color || '']
        );
        // Keep only last 5 fingerprints per vehicle
        await pool.query(
          `DELETE FROM vehicle_fingerprints WHERE vehicle_id = ? AND id NOT IN (
             SELECT id FROM vehicle_fingerprints WHERE vehicle_id = ? ORDER BY id DESC LIMIT 5
           )`,
          [vehicleId, vehicleId]
        );
      } catch (fpErr) {
        console.warn('[Fingerprint]', fpErr);
      }
    }

    // ── Part 14: Structured Socket.IO events ──────────────────────────────────
    const io = getIo();
    if (io) {
      const socketPayload = {
        id:           insertResult.insertId,
        plate:        resolvedPlate,
        province:     province     || '',
        type:         vehicleTypeLabel,
        dir:          direction,
        time:         new Date().toLocaleTimeString('th-TH', {
                        hour: '2-digit', minute: '2-digit', second: '2-digit',
                      }),
        confidence:   confidence_score,
        quality:      image_quality_score,
        track_id:     track_id,
        isBlacklist:  isBlacklist,
        isFuzzyMatch: isFuzzyMatch,
        originalOcr:  isFuzzyMatch ? originalOcr : undefined,
        hasImage:     !!storedImagePath,
      };
      io.emit('new_detection', socketPayload);

      if (isAnomaly) {
        io.emit('anomaly_alert', {
          plate:         resolvedPlate,
          message:       anomalyMessage,
          vehicle_color: vehicle_color,
        });
      }

      // Stats update — computed after every detection
      try {
        const today = new Date().toISOString().split('T')[0] + '%';
        const [[totalRow], [inRow], [outRow]]: any[] = await Promise.all([
          pool.query('SELECT COUNT(*) as cnt FROM vehicle_logs WHERE created_at LIKE ?', [today]),
          pool.query("SELECT COUNT(*) as cnt FROM vehicle_logs WHERE direction='IN'  AND created_at LIKE ?", [today]),
          pool.query("SELECT COUNT(*) as cnt FROM vehicle_logs WHERE direction='OUT' AND created_at LIKE ?", [today]),
        ]);
        const [typeRows]: any = await pool.query(`
          SELECT v.is_staff, v.is_internal, COUNT(*) as cnt
          FROM vehicle_logs vl
          LEFT JOIN vehicles v ON vl.vehicle_id = v.id
          WHERE vl.created_at LIKE ?
          GROUP BY v.is_staff, v.is_internal
        `, [today]);

        let staffCnt = 0, visitorCnt = 0;
        for (const r of typeRows) {
          if (r.is_staff || r.is_internal) staffCnt   += r.cnt;
          else                              visitorCnt += r.cnt;
        }
        io.emit('stats_update', {
          total:   (totalRow as any)[0].cnt.toLocaleString(),
          staff:   staffCnt.toLocaleString(),
          visitor: visitorCnt.toLocaleString(),
          active:  Math.max(0, (inRow as any)[0].cnt - (outRow as any)[0].cnt).toLocaleString(),
        });
      } catch (statsErr) {
        console.warn('[Socket] stats_update error:', statsErr);
      }
    }

    res.status(200).json({
      success: true,
      message: 'Detection logged',
      data: {
        plate_number:     resolvedPlate,
        vehicleTypeLabel,
        direction,
        isFuzzyMatch,
        isAnomaly,
        has_image:        !!storedImagePath,
        expire_at:        expireAt,
      },
    });

  } catch (error) {
    console.error('[Detection] Error:', error);
    res.status(500).json({ success: false, message: 'Server Error' });
  }
};

// ─────────────────────────────────────────────────────────────────────────────
// Stats
// ─────────────────────────────────────────────────────────────────────────────
export const getStats = async (_req: Request, res: Response) => {
  try {
    const today = new Date().toISOString().split('T')[0] + '%';
    const [[totalRow], [inRow], [outRow]]: any[] = await Promise.all([
      pool.query('SELECT COUNT(*) as count FROM vehicle_logs WHERE created_at LIKE ?', [today]),
      pool.query("SELECT COUNT(*) as count FROM vehicle_logs WHERE direction='IN'  AND created_at LIKE ?", [today]),
      pool.query("SELECT COUNT(*) as count FROM vehicle_logs WHERE direction='OUT' AND created_at LIKE ?", [today]),
    ]);
    const [typeRows]: any = await pool.query(`
      SELECT v.is_staff, v.is_internal, COUNT(*) as count
      FROM vehicle_logs vl
      LEFT JOIN vehicles v ON vl.vehicle_id = v.id
      WHERE vl.created_at LIKE ?
      GROUP BY v.is_staff, v.is_internal
    `, [today]);

    let staffCount = 0, visitorCount = 0;
    for (const r of typeRows) {
      if (r.is_staff || r.is_internal) staffCount   += r.count;
      else                              visitorCount += r.count;
    }
    const total  = (totalRow as any)[0].count;
    const inCnt  = (inRow   as any)[0].count;
    const outCnt = (outRow  as any)[0].count;

    res.json({
      success: true,
      data: {
        total:   total.toLocaleString(),
        staff:   staffCount.toLocaleString(),
        visitor: visitorCount.toLocaleString(),
        active:  Math.max(0, inCnt - outCnt).toLocaleString(),
      },
    });
  } catch (error) {
    console.error('[Stats] Error:', error);
    res.status(500).json({ success: false, message: 'Server Error' });
  }
};

// ─────────────────────────────────────────────────────────────────────────────
// Recent Logs (for dashboard)
// ─────────────────────────────────────────────────────────────────────────────
export const getRecentLogs = async (req: Request, res: Response) => {
  try {
    const limit = Math.min(parseInt(req.query.limit as string || '20', 10), 100);
    const [rows]: any = await pool.query(`
      SELECT vl.id, vl.plate_number as plate, vl.direction as dir,
             vl.created_at as time, vl.confidence_score,
             vl.image_quality_score, vl.quality_score,
             vl.processing_time_ms, vl.track_id,
             vl.is_fuzzy_match, vl.original_ocr_text, vl.image_path,
             v.is_staff, v.is_internal, v.is_blacklist
      FROM vehicle_logs vl
      LEFT JOIN vehicles v ON vl.vehicle_id = v.id
      ORDER BY vl.created_at DESC
      LIMIT ?
    `, [limit]);

    const logs = rows.map((row: any) => ({
      id:           row.id,
      plate:        row.plate,
      type:         row.is_blacklist ? 'BLACKLIST'
                    : (row.is_staff ? 'STAFF' : (row.is_internal ? 'INTERNAL' : 'VISITOR')),
      time:         new Date(row.time).toLocaleTimeString('th-TH'),
      dir:          row.dir,
      confidence:   row.confidence_score,
      quality:      row.image_quality_score,
      proc_ms:      row.processing_time_ms,
      track_id:     row.track_id,
      isFuzzyMatch: !!row.is_fuzzy_match,
      originalOcr:  row.original_ocr_text || undefined,
      hasImage:     !!row.image_path,
    }));

    res.json({ success: true, data: logs });
  } catch (error) {
    console.error('[Logs] Error:', error);
    res.status(500).json({ success: false, message: 'Server Error' });
  }
};

// ─────────────────────────────────────────────────────────────────────────────
// Pipeline Metrics (fetches from AI server /metrics proxy)
// ─────────────────────────────────────────────────────────────────────────────
const AI_URL = process.env.AI_URL || 'http://plate-ai:8000';

export const getMetrics = async (_req: Request, res: Response) => {
  try {
    // DB-side metrics: total logs, today, avg processing time, avg quality
    const today = new Date().toISOString().split('T')[0] + '%';
    const [[totalRow], [todayRow], [avgRow]]: any[] = await Promise.all([
      pool.query('SELECT COUNT(*) as total FROM vehicle_logs'),
      pool.query('SELECT COUNT(*) as today FROM vehicle_logs WHERE created_at LIKE ?', [today]),
      pool.query(`
        SELECT
          ROUND(AVG(processing_time_ms), 1)  as avg_proc_ms,
          ROUND(AVG(quality_score), 2)        as avg_quality,
          ROUND(AVG(confidence_score), 4)     as avg_confidence
        FROM vehicle_logs
        WHERE created_at LIKE ?
      `, [today]),
    ]);

    const dbMetrics = {
      total_all_time:   (totalRow as any)[0].total,
      total_today:      (todayRow as any)[0].today,
      avg_proc_ms:      (avgRow   as any)[0].avg_proc_ms,
      avg_quality:      (avgRow   as any)[0].avg_quality,
      avg_confidence:   (avgRow   as any)[0].avg_confidence,
    };

    // Proxy AI server pipeline counters (best-effort, non-fatal)
    let aiMetrics: Record<string, unknown> = {};
    try {
      const controller = new AbortController();
      const timeout    = setTimeout(() => controller.abort(), 2000);
      const aiRes      = await fetch(`${AI_URL}/metrics`, { signal: controller.signal });
      clearTimeout(timeout);
      if (aiRes.ok) aiMetrics = await aiRes.json() as Record<string, unknown>;
    } catch {
      // AI server unreachable — return empty AI metrics
    }

    res.json({
      success: true,
      data: {
        db:  dbMetrics,
        ai:  aiMetrics,
      },
    });
  } catch (error) {
    console.error('[Metrics] Error:', error);
    res.status(500).json({ success: false, message: 'Server Error' });
  }
};

// ─────────────────────────────────────────────────────────────────────────────
// Chart Data
// ─────────────────────────────────────────────────────────────────────────────
export const getChartData = async (_req: Request, res: Response) => {
  try {
    const today = new Date().toISOString().split('T')[0] + '%';
    const [rows]: any = await pool.query(`
      SELECT substr(created_at, 12, 2) as hour, COUNT(*) as count
      FROM vehicle_logs
      WHERE created_at LIKE ?
      GROUP BY hour
      ORDER BY hour ASC
    `, [today]);
    res.json({ success: true, data: rows });
  } catch (error) {
    res.status(500).json({ success: false, message: 'Server Error' });
  }
};
