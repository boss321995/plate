import { Request, Response } from 'express';
import { pool } from '../db';
import { getIo } from '../socket';

// In-Memory Cache for Cooldown (Key: plate_number, Value: timestamp in ms)
const cooldownCache = new Map<string, number>();
const COOLDOWN_TIME_MS = 3 * 60 * 1000; // 3 minutes

// ============================================================
// Fuzzy Match: Levenshtein Distance
// ============================================================
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

// Plate cache for fuzzy matching (refreshed every 60s)
let plateCache: { id: number; plate_number: string; is_staff: boolean; is_internal: boolean; is_blacklist: boolean }[] = [];
let plateCacheTime = 0;
const PLATE_CACHE_TTL = 60_000; // 60 seconds

async function refreshPlateCache() {
  const now = Date.now();
  if (now - plateCacheTime < PLATE_CACHE_TTL && plateCache.length > 0) return;
  try {
    const [rows]: any = await pool.query('SELECT id, plate_number, is_staff, is_internal, is_blacklist FROM vehicles');
    plateCache = rows;
    plateCacheTime = now;
  } catch (e) {
    console.error('[FuzzyCache] Failed to refresh:', e);
  }
}

function fuzzyMatchPlate(ocrPlate: string): { vehicle: any; matched_plate: string; distance: number } | null {
  if (!plateCache.length) return null;

  let bestMatch: any = null;
  let bestDist = Infinity;
  let bestPlate = '';

  for (const v of plateCache) {
    const dist = levenshteinDistance(ocrPlate, v.plate_number);
    if (dist < bestDist) {
      bestDist = dist;
      bestMatch = v;
      bestPlate = v.plate_number;
    }
  }

  // ยอมรับแค่ผิดไม่เกิน 2 ตัว และป้ายต้องยาวอย่างน้อย 3 ตัว
  if (bestDist > 0 && bestDist <= 2 && ocrPlate.length >= 3) {
    return { vehicle: bestMatch, matched_plate: bestPlate, distance: bestDist };
  }
  return null;
}

// ============================================================
// Anomaly Detection: Cosine Similarity for Fingerprints
// ============================================================
function cosineSimilarity(a: number[], b: number[]): number {
  if (!a || !b || a.length !== b.length || a.length === 0) return 0;
  let dot = 0, magA = 0, magB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i]! * b[i]!;
    magA += a[i]! * a[i]!;
    magB += b[i]! * b[i]!;
  }
  const denom = Math.sqrt(magA) * Math.sqrt(magB);
  return denom === 0 ? 0 : dot / denom;
}

// ============================================================
// Main Detection Handler
// ============================================================
export const handleDetection = async (req: Request, res: Response) => {
  try {
    const { plate_number, confidence_score, camera_id, image_path, vehicle_type, vehicle_color, vehicle_fingerprint } = req.body;

    if (!plate_number) {
      res.status(400).json({ success: false, message: 'plate_number is required' });
      return;
    }

    const now = Date.now();
    const lastSeen = cooldownCache.get(plate_number);

    // 1. Cooldown Check
    if (lastSeen && (now - lastSeen) < COOLDOWN_TIME_MS) {
      console.log(`[Cooldown] Ignored plate ${plate_number} (Seen ${Math.round((now - lastSeen)/1000)}s ago)`);
      res.status(200).json({ success: true, message: 'Ignored due to cooldown' });
      return;
    }

    // Update Cache
    cooldownCache.set(plate_number, now);

    // 2. Determine Direction based on Camera ID (e.g., 1 = IN, 2 = OUT)
    const direction = camera_id === 1 ? 'IN' : 'OUT';

    // 3. Check Vehicle Status — Exact Match first, then Fuzzy Match
    let vehicleId = null;
    let isStaff = false;
    let isInternal = false;
    let isBlacklist = false;
    let isFuzzyMatch = false;
    let originalOcrText = plate_number;
    let resolvedPlate = plate_number;

    await refreshPlateCache();

    const [vehicleRows]: any = await pool.query(
      'SELECT id, is_staff, is_internal, is_blacklist FROM vehicles WHERE plate_number = ? LIMIT 1',
      [plate_number]
    );

    if (vehicleRows.length > 0) {
      // ✅ Exact Match
      vehicleId = vehicleRows[0].id;
      isStaff = !!vehicleRows[0].is_staff;
      isInternal = !!vehicleRows[0].is_internal;
      isBlacklist = !!vehicleRows[0].is_blacklist;
    } else {
      // 🔍 Fuzzy Match — OCR อาจอ่านผิด 1-2 ตัว
      const fuzzy = fuzzyMatchPlate(plate_number);
      if (fuzzy) {
        vehicleId = fuzzy.vehicle.id;
        isStaff = !!fuzzy.vehicle.is_staff;
        isInternal = !!fuzzy.vehicle.is_internal;
        isBlacklist = !!fuzzy.vehicle.is_blacklist;
        isFuzzyMatch = true;
        originalOcrText = plate_number;           // เก็บที่ OCR อ่านได้จริง
        resolvedPlate = fuzzy.matched_plate;       // ใช้ป้ายที่ match ได้
        console.log(`[Fuzzy] OCR: "${plate_number}" → Matched: "${resolvedPlate}" (distance=${fuzzy.distance})`);
      }
    }

    const vehicleTypeLabel = isBlacklist ? 'BLACKLIST' : (isStaff ? 'STAFF' : (isInternal ? 'INTERNAL' : 'VISITOR'));
    console.log(`[Detection] Plate: ${resolvedPlate} | Type: ${vehicleTypeLabel} | Dir: ${direction}${isFuzzyMatch ? ' [FUZZY]' : ''}`);

    // 4. Log to Database
    const logQuery = `
      INSERT INTO vehicle_logs (plate_number, vehicle_id, camera_id, direction, confidence_score, image_path, is_fuzzy_match, original_ocr_text)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `;
    const [insertResult]: any = await pool.query(logQuery, [
      resolvedPlate,
      vehicleId,
      camera_id || 1,
      direction,
      confidence_score || 0,
      image_path || null,
      isFuzzyMatch ? 1 : 0,
      isFuzzyMatch ? originalOcrText : null
    ]);

    // 5. Anomaly Detection: Vehicle Fingerprint Check
    let isAnomaly = false;
    let anomalyMessage = '';

    if (vehicleId && vehicle_fingerprint && Array.isArray(vehicle_fingerprint) && vehicle_fingerprint.length > 0) {
      try {
        // ดึง fingerprint เฉลี่ย 5 ครั้งล่าสุด
        const [prevRows]: any = await pool.query(
          'SELECT fingerprint, vehicle_color FROM vehicle_fingerprints WHERE vehicle_id = ? ORDER BY id DESC LIMIT 5',
          [vehicleId]
        );

        if (prevRows.length > 0) {
          // คำนวณ average fingerprint จากรอบก่อนๆ
          const prevFingerprints: number[][] = prevRows
            .map((r: any) => { try { return JSON.parse(r.fingerprint); } catch { return null; } })
            .filter((f: any) => f !== null);

          if (prevFingerprints.length > 0) {
            const avgFingerprint = prevFingerprints[0]!.map((_: number, i: number) =>
              prevFingerprints.reduce((sum, fp) => sum + fp[i]!, 0) / prevFingerprints.length
            );

            const similarity = cosineSimilarity(avgFingerprint, vehicle_fingerprint);
            const prevColor = prevRows[0].vehicle_color;
            const colorMatch = !prevColor || !vehicle_color || prevColor === vehicle_color;

            // ⚠️ similarity < 0.65 AND สีไม่ตรง → เป็น anomaly ชัดเจน
            if (similarity < 0.65 && !colorMatch) {
              isAnomaly = true;
              anomalyMessage = `รถป้าย ${resolvedPlate} หน้าตาไม่เหมือนเดิม! ` +
                `(สีเดิม: ${prevColor}, สีใหม่: ${vehicle_color}, ` +
                `ความคล้าย: ${(similarity * 100).toFixed(0)}%)`;
              console.warn(`[ANOMALY] ${anomalyMessage}`);
            }
          }
        }

        // บันทึก fingerprint ใหม่ (เก็บแค่ 5 ครั้งล่าสุด)
        await pool.query(
          'INSERT INTO vehicle_fingerprints (vehicle_id, fingerprint, vehicle_color) VALUES (?, ?, ?)',
          [vehicleId, JSON.stringify(vehicle_fingerprint), vehicle_color || '']
        );
        // ลบอันเก่าเกิน 5 ครั้ง
        await pool.query(
          `DELETE FROM vehicle_fingerprints WHERE vehicle_id = ? AND id NOT IN (
            SELECT id FROM vehicle_fingerprints WHERE vehicle_id = ? ORDER BY id DESC LIMIT 5
          )`,
          [vehicleId, vehicleId]
        );
      } catch (fpErr) {
        console.warn('[Fingerprint] Error:', fpErr);
      }
    }

    // 6. Emit Socket.IO events
    const io = getIo();
    if (io) {
      const payload = {
        id: insertResult.insertId,
        plate: resolvedPlate,
        type: vehicleTypeLabel,
        dir: direction,
        time: new Date().toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        confidence: confidence_score,
        isBlacklist: isBlacklist,
        isFuzzyMatch: isFuzzyMatch,
        originalOcr: isFuzzyMatch ? originalOcrText : undefined,
      };
      io.emit('new_detection', payload);

      // Anomaly Alert
      if (isAnomaly) {
        io.emit('anomaly_alert', {
          plate: resolvedPlate,
          message: anomalyMessage,
          vehicle_color: vehicle_color,
        });
      }

      // Stats update
      try {
        const today = new Date().toISOString().split('T')[0] + '%';
        const [totalRows]: any = await pool.query('SELECT COUNT(*) as cnt FROM vehicle_logs WHERE created_at LIKE ?', [today]);
        const [typeRows]: any = await pool.query(`
          SELECT v.is_staff, v.is_internal, COUNT(*) as cnt
          FROM vehicle_logs vl
          LEFT JOIN vehicles v ON vl.vehicle_id = v.id
          WHERE vl.created_at LIKE ?
          GROUP BY v.is_staff, v.is_internal
        `, [today]);
        const [inRows]: any = await pool.query("SELECT COUNT(*) as cnt FROM vehicle_logs WHERE direction = 'IN' AND created_at LIKE ?", [today]);
        const [outRows]: any = await pool.query("SELECT COUNT(*) as cnt FROM vehicle_logs WHERE direction = 'OUT' AND created_at LIKE ?", [today]);

        let staffCnt = 0, visitorCnt = 0;
        for (const row of typeRows) {
          if (row.is_staff || row.is_internal) staffCnt += row.cnt;
          else visitorCnt += row.cnt;
        }

        io.emit('stats_update', {
          total: totalRows[0].cnt.toLocaleString(),
          staff: staffCnt.toLocaleString(),
          visitor: visitorCnt.toLocaleString(),
          active: Math.max(0, inRows[0].cnt - outRows[0].cnt).toLocaleString()
        });
      } catch (statsErr) {
        console.warn('[Socket] Could not emit stats_update:', statsErr);
      }
    }

    res.status(200).json({
      success: true,
      message: 'Detection logged successfully',
      data: { plate_number: resolvedPlate, vehicleTypeLabel, direction, isFuzzyMatch, isAnomaly }
    });

  } catch (error) {
    console.error('Error handling detection:', error);
    res.status(500).json({ success: false, message: 'Server Error' });
  }
};

export const getChartData = async (req: Request, res: Response) => {
  try {
    const today = new Date().toISOString().split('T')[0] + '%';
    const query = `
      SELECT substr(created_at, 12, 2) as hour, COUNT(*) as count 
      FROM vehicle_logs 
      WHERE created_at LIKE ?
      GROUP BY hour
      ORDER BY hour ASC
    `;
    const [rows]: any = await pool.query(query, [today]);
    res.status(200).json({ success: true, data: rows });
  } catch (error) {
    console.error('Error fetching chart data:', error);
    res.status(500).json({ success: false, message: 'Server Error' });
  }
};

export const getRecentLogs = async (req: Request, res: Response) => {
  try {
    const query = `
      SELECT vl.id, vl.plate_number as plate, vl.direction as dir, vl.created_at as time, 
             vl.is_fuzzy_match, vl.original_ocr_text,
             v.is_staff, v.is_internal, v.is_blacklist
      FROM vehicle_logs vl
      LEFT JOIN vehicles v ON vl.vehicle_id = v.id
      ORDER BY vl.created_at DESC
      LIMIT 20
    `;
    const [rows]: any = await pool.query(query);
    
    const logs = rows.map((row: any) => {
      const type = row.is_blacklist ? 'BLACKLIST' : (row.is_staff ? 'STAFF' : (row.is_internal ? 'INTERNAL' : 'VISITOR'));
      return {
        id: row.id,
        plate: row.plate,
        type: type,
        time: new Date(row.time).toLocaleTimeString(), 
        dir: row.dir,
        isFuzzyMatch: !!row.is_fuzzy_match,
        originalOcr: row.original_ocr_text || undefined,
      };
    });

    res.status(200).json({ success: true, data: logs });
  } catch (error) {
    console.error('Error fetching logs:', error);
    res.status(500).json({ success: false, message: 'Server Error' });
  }
};

export const getStats = async (req: Request, res: Response) => {
  try {
    const today = new Date().toISOString().split('T')[0] + '%';
    
    const [totalRows]: any = await pool.query('SELECT COUNT(*) as count FROM vehicle_logs WHERE created_at LIKE ?', [today]);
    
    const [typeRows]: any = await pool.query(`
      SELECT v.is_staff, v.is_internal, COUNT(*) as count 
      FROM vehicle_logs vl
      LEFT JOIN vehicles v ON vl.vehicle_id = v.id
      WHERE vl.created_at LIKE ?
      GROUP BY v.is_staff, v.is_internal
    `, [today]);

    let total = totalRows[0].count;
    let staffCount = 0;
    let visitorCount = 0;

    for (const row of typeRows) {
      if (row.is_staff || row.is_internal) {
        staffCount += row.count;
      } else {
        visitorCount += row.count;
      }
    }

    const [inRows]: any = await pool.query("SELECT COUNT(*) as count FROM vehicle_logs WHERE direction = 'IN' AND created_at LIKE ?", [today]);
    const [outRows]: any = await pool.query("SELECT COUNT(*) as count FROM vehicle_logs WHERE direction = 'OUT' AND created_at LIKE ?", [today]);
    const activeInside = Math.max(0, inRows[0].count - outRows[0].count);

    res.status(200).json({
      success: true,
      data: {
        total: total.toLocaleString(),
        staff: staffCount.toLocaleString(),
        visitor: visitorCount.toLocaleString(),
        active: activeInside.toLocaleString()
      }
    });
  } catch (error) {
    console.error('Error fetching stats:', error);
    res.status(500).json({ success: false, message: 'Server Error' });
  }
};
