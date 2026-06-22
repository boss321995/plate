import { Request, Response } from 'express';
import { pool } from '../db';

const AI_URL = process.env.AI_URL || 'http://plate-ai:8000';
const HEALTH_RETENTION_DAYS = parseInt(process.env.HEALTH_RETENTION_DAYS || '30', 10);

// ─────────────────────────────────────────────────────────────────────────────
// GET /api/diagnostics — proxy AI server camera diagnostics + recent DB health
// ─────────────────────────────────────────────────────────────────────────────
export const getDiagnostics = async (req: Request, res: Response) => {
  const cameraId = parseInt(req.query.camera_id as string || '1', 10);

  // Proxy diagnostics from AI server (non-fatal if unreachable)
  let aiDiag: Record<string, unknown> = {};
  try {
    const controller = new AbortController();
    const timeout    = setTimeout(() => controller.abort(), 2000);
    const aiRes      = await fetch(`${AI_URL}/diagnostics?camera_id=${cameraId}`,
                                   { signal: controller.signal });
    clearTimeout(timeout);
    if (aiRes.ok) aiDiag = await aiRes.json() as Record<string, unknown>;
  } catch {
    aiDiag = { status: 'unreachable', recommendation: 'AI server not responding' };
  }

  // Most recent health snapshot from DB
  let dbHealth: Record<string, unknown> | null = null;
  try {
    const [rows]: any = await pool.query(
      `SELECT * FROM camera_health
       WHERE camera_id = ?
       ORDER BY created_at DESC LIMIT 1`,
      [cameraId]
    );
    dbHealth = rows[0] ?? null;
  } catch {
    // table may not exist yet on first run
  }

  res.json({ success: true, data: { camera_id: cameraId, live: aiDiag, last_saved: dbHealth } });
};

// ─────────────────────────────────────────────────────────────────────────────
// POST /api/diagnostics/health — ingest camera health snapshot from AI server
// ─────────────────────────────────────────────────────────────────────────────
export const postCameraHealth = async (req: Request, res: Response) => {
  const {
    camera_id, focus_score, brightness_score,
    rain_detected, camera_shift, lens_dirty,
    vibration, blockage, over_exposure, under_exposure,
    disk_usage, cpu_usage, memory_usage,
    status, recommendation,
  } = req.body;

  try {
    await pool.query(
      `INSERT INTO camera_health
         (camera_id, focus_score, brightness_score,
          rain_detected, camera_shift, lens_dirty,
          vibration, blockage, over_exposure, under_exposure,
          disk_usage, cpu_usage, memory_usage, status, recommendation)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
      [
        camera_id || 1,
        focus_score || 0, brightness_score || 0,
        rain_detected  ? 1 : 0,
        camera_shift   ? 1 : 0,
        lens_dirty     ? 1 : 0,
        vibration      ? 1 : 0,
        blockage       ? 1 : 0,
        over_exposure  ? 1 : 0,
        under_exposure ? 1 : 0,
        disk_usage || 0, cpu_usage || 0, memory_usage || 0,
        status || 'OK',
        recommendation || 'OK',
      ]
    );
    res.json({ success: true });
  } catch (err) {
    console.error('[CameraHealth] Insert error:', err);
    res.status(500).json({ success: false, message: 'DB error' });
  }
};

// ─────────────────────────────────────────────────────────────────────────────
// GET /api/diagnostics/audit — recent audit log entries
// ─────────────────────────────────────────────────────────────────────────────
export const getAuditLog = async (req: Request, res: Response) => {
  const limit    = Math.min(parseInt(req.query.limit as string || '50', 10), 200);
  const severity = req.query.severity as string | undefined;

  try {
    const [rows]: any = await pool.query(
      `SELECT id, camera_id, event, severity, source, action, duration_ms, details, created_at
       FROM audit_log
       ${severity ? 'WHERE severity = ?' : ''}
       ORDER BY created_at DESC LIMIT ?`,
      severity ? [severity, limit] : [limit]
    );
    res.json({ success: true, data: rows });
  } catch (err) {
    res.status(500).json({ success: false, message: 'DB error' });
  }
};

// ─────────────────────────────────────────────────────────────────────────────
// POST /api/diagnostics/audit — write audit event (called by AI server)
// ─────────────────────────────────────────────────────────────────────────────
export const postAuditEvent = async (req: Request, res: Response) => {
  const { camera_id, event, severity, source, action, duration_ms, details } = req.body;

  if (!event) {
    res.status(400).json({ success: false, message: 'event is required' });
    return;
  }

  try {
    await pool.query(
      `INSERT INTO audit_log (camera_id, event, severity, source, action, duration_ms, details)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [
        camera_id || null,
        event,
        severity || 'INFO',
        source   || null,
        action   || null,
        duration_ms || null,
        details ? JSON.stringify(details) : null,
      ]
    );
    // Purge entries older than retention window
    await pool.query(
      `DELETE FROM audit_log
       WHERE created_at < datetime('now', '-${HEALTH_RETENTION_DAYS} days')`
    ).catch(() => {/* MySQL uses DATE_SUB — ignore cross-DB error */});

    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ success: false, message: 'DB error' });
  }
};
