import { Request, Response } from 'express';
import { pool } from '../db';
import ExcelJS from 'exceljs';

export const getLogs = async (req: Request, res: Response) => {
  try {
    const page = parseInt(req.query.page as string) || 1;
    const limit = parseInt(req.query.limit as string) || 20;
    const offset = (page - 1) * limit;

    const [rows]: any = await pool.query(
      `SELECT 
         vl.id, 
         vl.plate_number, 
         vl.confidence_score, 
         vl.camera_id, 
         vl.direction, 
         v.vehicle_type, 
         vl.created_at as timestamp 
       FROM vehicle_logs vl 
       LEFT JOIN vehicles v ON vl.vehicle_id = v.id 
       ORDER BY vl.created_at DESC LIMIT ? OFFSET ?`,
      [limit, offset]
    );

    const [countResult]: any = await pool.query('SELECT COUNT(*) as total FROM vehicle_logs');
    const total = countResult[0].total;

    res.json({
      success: true,
      data: rows,
      pagination: {
        total,
        page,
        limit,
        totalPages: Math.ceil(total / limit)
      }
    });
  } catch (error) {
    console.error('Error fetching logs:', error);
    res.status(500).json({ success: false, message: 'Server error' });
  }
};

export const exportLogsExcel = async (req: Request, res: Response) => {
  try {
    const [rows]: any = await pool.query(
      `SELECT 
         vl.id, 
         vl.plate_number, 
         vl.confidence_score, 
         vl.camera_id, 
         vl.direction, 
         v.vehicle_type, 
         vl.created_at as timestamp 
       FROM vehicle_logs vl 
       LEFT JOIN vehicles v ON vl.vehicle_id = v.id 
       ORDER BY vl.created_at DESC`
    );

    const workbook = new ExcelJS.Workbook();
    const worksheet = workbook.addWorksheet('Vehicle Logs');

    worksheet.columns = [
      { header: 'ID', key: 'id', width: 10 },
      { header: 'Plate Number', key: 'plate_number', width: 20 },
      { header: 'Type', key: 'vehicle_type', width: 15 },
      { header: 'Direction', key: 'direction', width: 10 },
      { header: 'Confidence (%)', key: 'confidence_score', width: 15 },
      { header: 'Timestamp', key: 'timestamp', width: 30 }
    ];

    // Add styling to header
    worksheet.getRow(1).font = { bold: true };

    rows.forEach((row: any) => {
      worksheet.addRow({
        id: row.id,
        plate_number: row.plate_number,
        vehicle_type: row.vehicle_type || 'VISITOR',
        direction: row.direction || 'IN',
        confidence_score: (row.confidence_score * 100).toFixed(2),
        timestamp: new Date(row.timestamp).toLocaleString('th-TH')
      });
    });

    res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    res.setHeader('Content-Disposition', 'attachment; filename=' + 'vehicle_logs.xlsx');

    await workbook.xlsx.write(res);
    res.end();
  } catch (error) {
    console.error('Error exporting logs:', error);
    res.status(500).json({ success: false, message: 'Server error during export' });
  }
};
