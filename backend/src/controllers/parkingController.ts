import { Request, Response } from 'express';
import { pool } from '../db';

export const getActiveVehicles = async (req: Request, res: Response) => {
  try {
    const query = `
      SELECT t1.id, t1.plate_number as plate, t1.created_at as entry_time,
             v.is_staff, v.is_internal, v.is_blacklist
      FROM vehicle_logs t1
      INNER JOIN (
          SELECT plate_number, MAX(id) as max_id
          FROM vehicle_logs
          GROUP BY plate_number
      ) t2 ON t1.id = t2.max_id
      LEFT JOIN vehicles v ON t1.vehicle_id = v.id
      WHERE t1.direction = 'IN'
      ORDER BY t1.created_at DESC
    `;
    
    const [rows]: any = await pool.query(query);

    const now = Date.now();
    
    const activeVehicles = rows.map((row: any) => {
      let role = 'VISITOR';
      if (row.is_blacklist) role = 'BLACKLIST';
      else if (row.is_staff) role = 'STAFF';
      else if (row.is_internal) role = 'INTERNAL';

      const entryTime = new Date(row.entry_time).getTime();
      const diffMs = Math.max(0, now - entryTime);
      
      const hours = Math.floor(diffMs / (1000 * 60 * 60));
      const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
      
      // Overstay logic (e.g. Visitors > 12 hours)
      const isOverstay = role === 'VISITOR' && hours >= 12;

      return {
        id: row.id,
        plate: row.plate,
        role: role,
        entry_time: row.entry_time,
        duration_formatted: `${hours}h ${minutes}m`,
        duration_minutes: hours * 60 + minutes,
        is_overstay: isOverstay
      };
    });

    res.json({ success: true, data: activeVehicles });
  } catch (error) {
    console.error('Error fetching active vehicles:', error);
    res.status(500).json({ success: false, message: 'Server Error' });
  }
};
