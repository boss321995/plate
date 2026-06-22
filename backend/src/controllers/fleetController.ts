import { Request, Response } from 'express';
import { pool } from '../db';

const AI_URL = process.env.AI_URL || 'http://plate-ai:8000';

async function proxyAI(path: string, init: RequestInit = {}, timeoutMs = 3000) {
  const ctrl  = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${AI_URL}${path}`, { ...init, signal: ctrl.signal });
    clearTimeout(timer);
    if (!res.ok) throw new Error(`AI ${res.status}`);
    return await res.json();
  } catch {
    clearTimeout(timer);
    return null;
  }
}

// ─── GET /api/fleet ───────────────────────────────────────────────────────────
// Live fleet from AI server merged with persistent DB device records
export const getFleet = async (req: Request, res: Response) => {
  const siteId = req.query.site_id as string | undefined;

  const url = siteId ? `/fleet?site_id=${siteId}` : '/fleet';
  const live = await proxyAI(url) ?? { devices: [], stats: {} };

  // Enrich each live device with DB inventory row (serial, ip, mac, etc.)
  const deviceIds = (live.devices ?? []).map((d: any) => d.device_id);
  let dbRows: any[] = [];
  if (deviceIds.length > 0) {
    try {
      const placeholders = deviceIds.map(() => '?').join(',');
      const [rows]: any = await pool.query(
        `SELECT * FROM devices WHERE device_id IN (${placeholders})`,
        deviceIds,
      );
      dbRows = rows ?? [];
    } catch { /* table may not exist yet */ }
  }

  const dbMap: Record<string, any> = {};
  for (const row of dbRows) dbMap[row.device_id] = row;

  const merged = (live.devices ?? []).map((d: any) => ({
    ...d,
    ...(dbMap[d.device_id] ?? {}),
  }));

  res.json({ success: true, data: { devices: merged, stats: live.stats ?? {} } });
};

// ─── GET /api/fleet/stats ─────────────────────────────────────────────────────
export const getFleetStats = async (_req: Request, res: Response) => {
  const live = await proxyAI('/fleet') ?? { stats: {} };
  res.json({ success: true, data: live.stats ?? {} });
};

// ─── GET /api/fleet/:deviceId ─────────────────────────────────────────────────
export const getFleetDevice = async (req: Request, res: Response) => {
  const { deviceId } = req.params;
  const live         = await proxyAI(`/fleet/${encodeURIComponent(deviceId)}`);
  let dbRow: any     = null;
  try {
    const [rows]: any = await pool.query(
      'SELECT * FROM devices WHERE device_id = ? LIMIT 1', [deviceId]);
    dbRow = rows?.[0] ?? null;
  } catch { /* ignore */ }

  if (!live && !dbRow) {
    res.status(404).json({ success: false, message: 'Device not found' });
    return;
  }
  res.json({ success: true, data: { ...(dbRow ?? {}), ...(live ?? {}) } });
};

// ─── POST /api/fleet/register ─────────────────────────────────────────────────
// Persists device to DB and forwards to AI server fleet registry
export const registerDevice = async (req: Request, res: Response) => {
  const {
    device_id, serial, hostname, site_id, os_info,
    cpu_model, ram_gb, disk_gb, ip_address, mac_address,
    software_version, camera_count,
  } = req.body;

  if (!device_id) {
    res.status(400).json({ success: false, message: 'device_id required' });
    return;
  }

  try {
    await pool.query(
      `INSERT INTO devices
         (device_id, serial, hostname, site_id, os_info, cpu_model,
          ram_gb, disk_gb, ip_address, mac_address, software_version, camera_count, last_seen)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
       ON CONFLICT(device_id) DO UPDATE SET
         hostname=excluded.hostname, site_id=excluded.site_id,
         ip_address=excluded.ip_address, software_version=excluded.software_version,
         last_seen=CURRENT_TIMESTAMP`,
      [device_id, serial ?? null, hostname ?? device_id,
       site_id ?? null, os_info ?? null, cpu_model ?? null,
       ram_gb ?? 0, disk_gb ?? 0, ip_address ?? null, mac_address ?? null,
       software_version ?? 'unknown', camera_count ?? 1],
    );
  } catch (err) {
    console.error('[Fleet] DB register error:', err);
  }

  // Forward to AI fleet manager (best effort)
  await proxyAI('/fleet/register', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(req.body),
  });

  res.json({ success: true });
};

// ─── POST /api/fleet/heartbeat ────────────────────────────────────────────────
export const fleetHeartbeat = async (req: Request, res: Response) => {
  const { device_id } = req.body;
  if (!device_id) {
    res.status(400).json({ success: false, message: 'device_id required' });
    return;
  }
  // Update last_seen in DB
  try {
    await pool.query(
      'UPDATE devices SET last_seen = CURRENT_TIMESTAMP, status = ? WHERE device_id = ?',
      ['ONLINE', device_id],
    );
  } catch { /* ignore if table not yet migrated */ }

  // Forward to AI fleet manager
  await proxyAI('/fleet/heartbeat', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(req.body),
  });

  res.json({ success: true });
};

// ─── GET /api/fleet/config/:deviceId ─────────────────────────────────────────
export const getDeviceConfig = async (req: Request, res: Response) => {
  const { deviceId } = req.params;
  const cfg = await proxyAI(`/fleet/config/${encodeURIComponent(deviceId)}`);
  if (!cfg) {
    res.status(503).json({ success: false, message: 'AI server unreachable' });
    return;
  }
  res.json({ success: true, data: cfg });
};

// ─── PUT /api/fleet/config/:deviceId ─────────────────────────────────────────
export const updateDeviceConfig = async (req: Request, res: Response) => {
  const { deviceId } = req.params;
  const result = await proxyAI(`/fleet/config/${encodeURIComponent(deviceId)}`, {
    method:  'PUT',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(req.body),
  });
  if (!result) {
    res.status(503).json({ success: false, message: 'AI server unreachable' });
    return;
  }
  res.json({ success: true, data: result });
};

// ─── GET /api/fleet/version ───────────────────────────────────────────────────
export const getVersion = async (_req: Request, res: Response) => {
  const ver = await proxyAI('/updates/version') ?? { version: 'unknown' };
  res.json({ success: true, data: ver });
};

// ─── POST /api/fleet/update/check ────────────────────────────────────────────
export const checkUpdate = async (_req: Request, res: Response) => {
  const result = await proxyAI('/updates/check', { method: 'POST' });
  res.json({ success: true, data: result ?? {} });
};

// ─── POST /api/fleet/update/rollback ─────────────────────────────────────────
export const rollbackUpdate = async (_req: Request, res: Response) => {
  const result = await proxyAI('/updates/rollback', { method: 'POST' });
  res.json({ success: true, data: result ?? {} });
};

// ─── GET /api/fleet/backup/list ──────────────────────────────────────────────
export const getBackupList = async (_req: Request, res: Response) => {
  const result = await proxyAI('/backup/list') ?? { backups: [] };
  res.json({ success: true, data: result });
};

// ─── POST /api/fleet/backup/now ──────────────────────────────────────────────
export const triggerBackup = async (_req: Request, res: Response) => {
  const result = await proxyAI('/backup/now', { method: 'POST' }, 30_000);
  res.json({ success: true, data: result ?? {} });
};
