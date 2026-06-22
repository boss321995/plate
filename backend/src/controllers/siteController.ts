import { Request, Response } from 'express';
import { pool } from '../db';

// ─── GET /api/sites ───────────────────────────────────────────────────────────
export const getSites = async (_req: Request, res: Response) => {
  try {
    const [rows]: any = await pool.query(
      `SELECT s.*,
         (SELECT COUNT(*) FROM devices d WHERE d.site_id = s.id) AS device_count
       FROM sites s ORDER BY s.site_name`,
    );
    res.json({ success: true, data: rows ?? [] });
  } catch (err) {
    res.status(500).json({ success: false, message: 'DB error' });
  }
};

// ─── GET /api/sites/:id ───────────────────────────────────────────────────────
export const getSite = async (req: Request, res: Response) => {
  const { id } = req.params;
  try {
    const [rows]: any = await pool.query(
      'SELECT * FROM sites WHERE id = ? LIMIT 1', [id]);
    if (!rows?.[0]) {
      res.status(404).json({ success: false, message: 'Site not found' });
      return;
    }
    const [devRows]: any = await pool.query(
      'SELECT * FROM devices WHERE site_id = ?', [id]);
    res.json({ success: true, data: { ...rows[0], devices: devRows ?? [] } });
  } catch (err) {
    res.status(500).json({ success: false, message: 'DB error' });
  }
};

// ─── POST /api/sites ──────────────────────────────────────────────────────────
export const createSite = async (req: Request, res: Response) => {
  const { site_name, address, timezone, latitude, longitude } = req.body;
  if (!site_name) {
    res.status(400).json({ success: false, message: 'site_name required' });
    return;
  }
  try {
    const [result]: any = await pool.query(
      `INSERT INTO sites (site_name, address, timezone, latitude, longitude)
       VALUES (?, ?, ?, ?, ?)`,
      [site_name, address ?? null, timezone ?? 'Asia/Bangkok',
       latitude ?? 0, longitude ?? 0],
    );
    res.json({ success: true, data: { id: result?.insertId } });
  } catch (err) {
    res.status(500).json({ success: false, message: 'DB error' });
  }
};

// ─── PUT /api/sites/:id ───────────────────────────────────────────────────────
export const updateSite = async (req: Request, res: Response) => {
  const { id } = req.params;
  const { site_name, address, timezone, latitude, longitude, status } = req.body;
  try {
    await pool.query(
      `UPDATE sites
       SET site_name=?, address=?, timezone=?, latitude=?, longitude=?, status=?
       WHERE id=?`,
      [site_name, address ?? null, timezone ?? 'Asia/Bangkok',
       latitude ?? 0, longitude ?? 0, status ?? 'active', id],
    );
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ success: false, message: 'DB error' });
  }
};

// ─── DELETE /api/sites/:id ────────────────────────────────────────────────────
export const deleteSite = async (req: Request, res: Response) => {
  const { id } = req.params;
  try {
    await pool.query('DELETE FROM sites WHERE id = ?', [id]);
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ success: false, message: 'DB error' });
  }
};

// ─── GET /api/sites/models ────────────────────────────────────────────────────
// Model registry — kept in siteController for simplicity
export const getModels = async (req: Request, res: Response) => {
  const { model_type } = req.query;
  try {
    const [rows]: any = await pool.query(
      `SELECT * FROM model_registry
       ${model_type ? 'WHERE model_type = ?' : ''}
       ORDER BY created_at DESC`,
      model_type ? [model_type] : [],
    );
    res.json({ success: true, data: rows ?? [] });
  } catch (err) {
    res.status(500).json({ success: false, message: 'DB error' });
  }
};

// ─── POST /api/sites/models ───────────────────────────────────────────────────
export const registerModel = async (req: Request, res: Response) => {
  const { model_name, model_version, model_type, accuracy, file_path, checksum, notes } = req.body;
  if (!model_name || !model_version) {
    res.status(400).json({ success: false, message: 'model_name + model_version required' });
    return;
  }
  try {
    const [result]: any = await pool.query(
      `INSERT INTO model_registry
         (model_name, model_version, model_type, accuracy, file_path, checksum, notes, status)
       VALUES (?,?,?,?,?,?,?,'staged')`,
      [model_name, model_version, model_type ?? 'vehicle',
       accuracy ?? 0, file_path ?? null, checksum ?? null, notes ?? null],
    );
    res.json({ success: true, data: { id: result?.insertId } });
  } catch (err) {
    res.status(500).json({ success: false, message: 'DB error' });
  }
};

// ─── PUT /api/sites/models/:id/activate ──────────────────────────────────────
export const activateModel = async (req: Request, res: Response) => {
  const { id } = req.params;
  try {
    // Get model_type of the target model first
    const [rows]: any = await pool.query(
      'SELECT model_type FROM model_registry WHERE id = ? LIMIT 1', [id]);
    const modelType = rows?.[0]?.model_type ?? 'vehicle';

    // Deactivate all models of same type
    await pool.query(
      'UPDATE model_registry SET is_active = 0, status = ? WHERE model_type = ?',
      ['inactive', modelType],
    );
    // Activate the target
    await pool.query(
      'UPDATE model_registry SET is_active = 1, status = ?, deployed_at = CURRENT_TIMESTAMP WHERE id = ?',
      ['active', id],
    );
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ success: false, message: 'DB error' });
  }
};

// ─── POST /api/sites/models/:id/rollback ─────────────────────────────────────
// Activate the previous active model of the same type
export const rollbackModel = async (req: Request, res: Response) => {
  const { id } = req.params;
  try {
    const [rows]: any = await pool.query(
      'SELECT model_type FROM model_registry WHERE id = ? LIMIT 1', [id]);
    const modelType = rows?.[0]?.model_type ?? 'vehicle';

    const [prevRows]: any = await pool.query(
      `SELECT id FROM model_registry
       WHERE model_type = ? AND id != ? AND status IN ('inactive','staged')
       ORDER BY deployed_at DESC, created_at DESC LIMIT 1`,
      [modelType, id],
    );
    const prevId = prevRows?.[0]?.id;
    if (!prevId) {
      res.status(404).json({ success: false, message: 'No previous model to rollback to' });
      return;
    }

    await pool.query('UPDATE model_registry SET is_active = 0 WHERE model_type = ?', [modelType]);
    await pool.query(
      'UPDATE model_registry SET is_active = 1, status = ?, deployed_at = CURRENT_TIMESTAMP WHERE id = ?',
      ['active', prevId],
    );
    res.json({ success: true, data: { rolled_back_to: prevId } });
  } catch (err) {
    res.status(500).json({ success: false, message: 'DB error' });
  }
};
