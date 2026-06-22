import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import http from 'http';
import path from 'path';
import compression from 'compression';

import vehicleRoutes   from './routes/vehicleRoutes';
import detectionRoutes from './routes/detectionRoutes';
import logRoutes       from './routes/logRoutes';
import authRoutes      from './routes/authRoutes';
import cameraRoutes    from './routes/cameraRoutes';
import parkingRoutes   from './routes/parkingRoutes';

import { initSocket } from './socket';
import { startCleanupScheduler } from './cleanupJob';

dotenv.config();

const app  = express();
const PORT = process.env.PORT || 3003;

// ─────────────────────────────────────────────────────────────────────────────
// HTTP Server + Socket.IO
// ─────────────────────────────────────────────────────────────────────────────
const server = http.createServer(app);
initSocket(server);

// ─────────────────────────────────────────────────────────────────────────────
// Middleware
// ─────────────────────────────────────────────────────────────────────────────
// Gzip compression for all API responses — critical for 4G mobile
app.use(compression({
  threshold: 512,                         // Compress responses > 512 bytes
  filter: (req, res) => {
    if (req.headers['x-no-compression']) return false;
    return compression.filter(req, res);
  }
}));

app.use(cors({
  origin: process.env.CORS_ORIGIN || '*',
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization', 'X-API-Key'],
}));

// Increase JSON limit for base64 image uploads
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// ─────────────────────────────────────────────────────────────────────────────
// Static: serve evidence images from logs/ (with cache headers)
// ─────────────────────────────────────────────────────────────────────────────
const LOGS_DIR = path.join(__dirname, '..', 'logs');
app.use('/static/logs', express.static(LOGS_DIR, {
  maxAge: '1d',    // Cache on client for 1 day
  etag:   true,
  lastModified: true,
}));

// ─────────────────────────────────────────────────────────────────────────────
// API Routes
// ─────────────────────────────────────────────────────────────────────────────
app.use('/api/vehicles',  vehicleRoutes);
app.use('/api/detect',    detectionRoutes);
app.use('/api/logs',      logRoutes);
app.use('/api/auth',      authRoutes);
app.use('/api/cameras',   cameraRoutes);
app.use('/api/parking',   parkingRoutes);

// Health check
app.get('/api/health', (_req, res) => {
  res.json({
    status:  'ok',
    message: 'LPR Backend v2 running',
    uptime:  Math.floor(process.uptime()),
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Start Server + Cleanup Scheduler
// ─────────────────────────────────────────────────────────────────────────────
server.listen(PORT, () => {
  console.log(`[Server] ✅ Running on http://localhost:${PORT}`);
  console.log(`[Server] 📁 Evidence images: ${LOGS_DIR}`);

  // Start the daily image cleanup job
  startCleanupScheduler();
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('[Server] SIGTERM received — shutting down gracefully...');
  server.close(() => {
    console.log('[Server] HTTP server closed.');
    process.exit(0);
  });
});
