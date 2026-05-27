import { Request, Response } from 'express';
import { pool } from '../db';

export const getCameras = async (req: Request, res: Response) => {
  try {
    const [rows] = await pool.query('SELECT * FROM cameras ORDER BY id ASC');
    res.json({ success: true, data: rows });
  } catch (error) {
    console.error('Error fetching cameras:', error);
    res.status(500).json({ success: false, message: 'Server Error' });
  }
};

export const addCamera = async (req: Request, res: Response) => {
  try {
    const { name, location, ip_address, stream_url, status } = req.body;
    
    if (!name) {
       res.status(400).json({ success: false, message: 'Name is required' });
       return;
    }

    const query = `
      INSERT INTO cameras (name, location, ip_address, stream_url, status)
      VALUES (?, ?, ?, ?, ?)
    `;
    const [result] = await pool.query(query, [name, location || '', ip_address || '', stream_url || '', status || 'Online']);
    
    res.status(201).json({ success: true, message: 'Camera added successfully', data: result });
  } catch (error) {
    console.error('Error adding camera:', error);
    res.status(500).json({ success: false, message: 'Server Error' });
  }
};

export const updateCamera = async (req: Request, res: Response) => {
  try {
    const { id } = req.params;
    const { name, location, ip_address, stream_url, status } = req.body;
    
    const query = `
      UPDATE cameras 
      SET name = ?, location = ?, ip_address = ?, stream_url = ?, status = ?
      WHERE id = ?
    `;
    await pool.query(query, [name, location, ip_address, stream_url, status, id]);
    
    res.json({ success: true, message: 'Camera updated successfully' });
  } catch (error) {
    console.error('Error updating camera:', error);
    res.status(500).json({ success: false, message: 'Server Error' });
  }
};

export const deleteCamera = async (req: Request, res: Response) => {
  try {
    const { id } = req.params;
    await pool.query('DELETE FROM cameras WHERE id = ?', [id]);
    res.json({ success: true, message: 'Camera deleted successfully' });
  } catch (error) {
    console.error('Error deleting camera:', error);
    res.status(500).json({ success: false, message: 'Server Error' });
  }
};
