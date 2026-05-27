import sqlite3 from 'sqlite3';
import { open, Database } from 'sqlite';
import mysql from 'mysql2/promise';
import dotenv from 'dotenv';

dotenv.config();

const dbClient = process.env.DB_CLIENT || 'sqlite';

let sqliteDb: Database;
let mysqlPool: mysql.Pool;

const initDb = async () => {
  if (dbClient === 'mysql') {
    mysqlPool = mysql.createPool({
      host: process.env.DB_HOST || 'localhost',
      user: process.env.DB_USER || 'root',
      password: process.env.DB_PASSWORD || '',
      database: process.env.DB_NAME || 'lpr_db',
      waitForConnections: true,
      connectionLimit: 10,
      queueLimit: 0
    });
    console.log('MySQL Database pool initialized.');
  } else {
    sqliteDb = await open({
      filename: process.env.SQLITE_FILENAME || './database.sqlite',
      driver: sqlite3.Database
    });

    await sqliteDb.exec(`
      CREATE TABLE IF NOT EXISTS vehicles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plate_number TEXT UNIQUE NOT NULL,
        province TEXT,
        plate_type TEXT,
        vehicle_type TEXT,
        is_staff BOOLEAN DEFAULT 0,
        is_internal BOOLEAN DEFAULT 0,
        owner_name TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE IF NOT EXISTS cameras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        location TEXT,
        ip_address TEXT,
        stream_url TEXT,
        status TEXT DEFAULT 'Online',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE IF NOT EXISTS vehicle_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plate_number TEXT NOT NULL,
        vehicle_id INTEGER,
        camera_id INTEGER,
        direction TEXT,
        confidence_score REAL,
        image_path TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(vehicle_id) REFERENCES vehicles(id)
      );
    `);
    console.log('SQLite Database initialized successfully.');
  }
};

initDb().catch(console.error);

export const pool = {
  query: async (sql: string, params: any[] = []) => {
    if (dbClient === 'mysql') {
      if (!mysqlPool) await initDb();
      // mysql2/promise returns [rows, fields]
      return mysqlPool.query(sql, params);
    } else {
      if (!sqliteDb) await initDb();
      
      const isSelect = sql.trim().toUpperCase().startsWith('SELECT');
      try {
        if (isSelect) {
          const rows = await sqliteDb.all(sql, params);
          return [rows, null];
        } else {
          const result = await sqliteDb.run(sql, params);
          return [{ insertId: result.lastID, affectedRows: result.changes }, null];
        }
      } catch (err) {
        console.error("SQLite DB Query Error:", err, "SQL:", sql);
        throw err;
      }
    }
  }
};
