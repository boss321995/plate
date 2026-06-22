import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import http from 'http';
import path from 'path';
import compression from 'compression';

import vehicleRoutes      from './routes/vehicleRoutes';
import detectionRoutes    from './routes/detectionRoutes';
import logRoutes          from './routes/logRoutes';
import authRoutes         from './routes/authRoutes';
import cameraRoutes       from './routes/cameraRoutes';
import parkingRoutes      from './routes/parkingRoutes';
import diagnosticsRoutes  from './routes/diagnosticsRoutes';
import fleetRoutes        from './routes/fleetRoutes';
import siteRoutes         from './routes/siteRoutes';

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
// Security hardening (Part 13) — helmet + rate-limiting
// Loaded with require() so missing packages degrade gracefully at runtime.
// ─────────────────────────────────────────────────────────────────────────────
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const helmetFn = require('helmet');
  app.use(helmetFn());
  console.log('[Security] helmet enabled');
} catch {
  console.warn('[Security] helmet not installed — run: npm install helmet');
}

try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { rateLimit } = require('express-rate-limit');

  // Strict limit for auth endpoints (brute-force protection)
  const authLimiter = rateLimit({
    windowMs: 15 * 60 * 1000,   // 15 min
    max: 30,
    standardHeaders: true,
    legacyHeaders: false,
    message: { success: false, message: 'Too many requests — try again later' },
  });

  // General API limiter
  const apiLimiter = rateLimit({
    windowMs: 60 * 1000,   // 1 min
    max: parseInt(process.env.RATE_LIMIT_RPM || '300', 10),
    standardHeaders: true,
    legacyHeaders: false,
  });

  app.use('/api/auth',   authLimiter);
  app.use('/api/',       apiLimiter);
  console.log('[Security] rate-limiting enabled');
} catch {
  console.warn('[Security] express-rate-limit not installed — run: npm install express-rate-limit');
}

// ─────────────────────────────────────────────────────────────────────────────
// Middleware
// ─────────────────────────────────────────────────────────────────────────────
// Gzip compression for all API responses — critical for 4G mobile
app.use(compression({
  threshold: 512,
  filter: (req, res) => {
    if (req.headers['x-no-compression']) return false;
    return compression.filter(req, res);
  },
}));

const corsOrigin = process.env.CORS_ORIGIN || '*';
app.use(cors({
  origin: corsOrigin === '*' ? '*' : corsOrigin.split(',').map(s => s.trim()),
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization', 'X-API-Key',
                   'X-Track-Id', 'X-Camera-Id', 'X-Direction',
                   'X-Quality-Score', 'X-Frame-Index'],
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
app.use('/api/vehicles',    vehicleRoutes);
app.use('/api/detect',      detectionRoutes);
app.use('/api/logs',        logRoutes);
app.use('/api/auth',        authRoutes);
app.use('/api/cameras',     cameraRoutes);
app.use('/api/parking',     parkingRoutes);
app.use('/api/diagnostics', diagnosticsRoutes);
app.use('/api/fleet',       fleetRoutes);
app.use('/api/sites',       siteRoutes);

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
