import { Request, Response } from 'express';
import { pool } from '../db';
import { getIo } from '../socket';

// In-Memory Cache for Cooldown (Key: plate_number, Value: timestamp in ms)
const cooldownCache = new Map<string, number>();
const COOLDOWN_TIME_MS = 3 * 60 * 1000; // 3 minutes

export const handleDetection = async (req: Request, res: Response) => {
  try {
    const { plate_number, confidence_score, camera_id, image_path } = req.body;

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

    // 3. Check Vehicle Status (Staff/Internal vs Visitor)
    let vehicleId = null;
    let isStaff = false;
    let isInternal = false;
    let isBlacklist = false;

    const [vehicleRows]: any = await pool.query(
      'SELECT id, is_staff, is_internal, is_blacklist FROM vehicles WHERE plate_number = ? LIMIT 1',
      [plate_number]
    );

    if (vehicleRows.length > 0) {
      vehicleId = vehicleRows[0].id;
      isStaff = !!vehicleRows[0].is_staff;
      isInternal = !!vehicleRows[0].is_internal;
      isBlacklist = !!vehicleRows[0].is_blacklist;
    }

    const vehicleTypeLabel = isBlacklist ? 'BLACKLIST' : (isStaff ? 'STAFF' : (isInternal ? 'INTERNAL' : 'VISITOR'));
    console.log(`[Detection] Plate: ${plate_number} | Type: ${vehicleTypeLabel} | Dir: ${direction}`);

    // 4. Log to Database
    const logQuery = `
      INSERT INTO vehicle_logs (plate_number, vehicle_id, camera_id, direction, confidence_score, image_path)
      VALUES (?, ?, ?, ?, ?, ?)
    `;
    const [insertResult]: any = await pool.query(logQuery, [
      plate_number,
      vehicleId, // Nullable
      camera_id || 1,
      direction,
      confidence_score || 0,
      image_path || null
    ]);

    // 5. Emit Socket.IO event for real-time dashboard updates
    const io = getIo();
    if (io) {
      const payload = {
        id: insertResult.insertId,
        plate: plate_number,
        type: vehicleTypeLabel,
        dir: direction,
        time: new Date().toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        confidence: confidence_score,
        isBlacklist: isBlacklist
      };
      io.emit('new_detection', payload);

      // Also emit updated stats so dashboard cards update without re-fetching DB
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
      data: { plate_number, vehicleTypeLabel, direction }
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
    
    // Create an array of 12 slots for the chart (e.g. 06:00 to 18:00)
    // For simplicity, just return the raw hour data and let frontend handle it
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
             v.is_staff, v.is_internal, v.is_blacklist
      FROM vehicle_logs vl
      LEFT JOIN vehicles v ON vl.vehicle_id = v.id
      ORDER BY vl.created_at DESC
      LIMIT 20
    `;
    const [rows]: any = await pool.query(query);
    
    // Map to frontend expected format
    const logs = rows.map((row: any) => {
      const type = row.is_blacklist ? 'BLACKLIST' : (row.is_staff ? 'STAFF' : (row.is_internal ? 'INTERNAL' : 'VISITOR'));
      // format time dynamically or just let frontend format it
      return {
        id: row.id,
        plate: row.plate,
        type: type,
        time: new Date(row.time).toLocaleTimeString(), 
        dir: row.dir
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
    
    // Total today
    const [totalRows]: any = await pool.query('SELECT COUNT(*) as count FROM vehicle_logs WHERE created_at LIKE ?', [today]);
    
    // Types today
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

    // Active Inside (IN - OUT for today)
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
