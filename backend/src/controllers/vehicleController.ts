import { Request, Response } from 'express';
import { pool } from '../db';

export const getVehicles = async (req: Request, res: Response) => {
  try {
    const [rows] = await pool.query('SELECT * FROM vehicles');
    res.json({ success: true, data: rows });
  } catch (error) {
    console.error('Error fetching vehicles:', error);
    res.status(500).json({ success: false, message: 'Server Error' });
  }
};

export const addVehicle = async (req: Request, res: Response) => {
  try {
    const { plate_number, province, plate_type, vehicle_type, is_staff, is_internal, is_blacklist, owner_name } = req.body;
    
    if (!plate_number) {
       res.status(400).json({ success: false, message: 'plate_number is required' });
       return;
    }

    const query = `
      INSERT INTO vehicles (plate_number, province, plate_type, vehicle_type, is_staff, is_internal, is_blacklist, owner_name)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `;
    const [result] = await pool.query(query, [plate_number, province, plate_type, vehicle_type, is_staff || false, is_internal || false, is_blacklist || false, owner_name]);
    
    res.status(201).json({ success: true, message: 'Vehicle added successfully', data: result });
  } catch (error) {
    console.error('Error adding vehicle:', error);
    res.status(500).json({ success: false, message: 'Server Error' });
  }
};

export const deleteVehicle = async (req: Request, res: Response) => {
  try {
    const { id } = req.params;
    await pool.query('DELETE FROM vehicles WHERE id = ?', [id]);
    res.json({ success: true, message: 'Vehicle deleted successfully' });
  } catch (error) {
    console.error('Error deleting vehicle:', error);
    res.status(500).json({ success: false, message: 'Server Error' });
  }
};
