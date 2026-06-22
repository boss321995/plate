import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import http from 'http';
import vehicleRoutes from './routes/vehicleRoutes';
import detectionRoutes from './routes/detectionRoutes';
import logRoutes from './routes/logRoutes';
import authRoutes from './routes/authRoutes';
import cameraRoutes from './routes/cameraRoutes';
import parkingRoutes from './routes/parkingRoutes';
import { initSocket } from './socket';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3003;

// Create HTTP server
const server = http.createServer(app);

// Initialize Socket.io
initSocket(server);

app.use(cors());
app.use(express.json());

app.use('/api/vehicles', vehicleRoutes);
app.use('/api/detect', detectionRoutes);
app.use('/api/logs', logRoutes);
app.use('/api/auth', authRoutes);
app.use('/api/cameras', cameraRoutes);
app.use('/api/parking', parkingRoutes);

app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', message: 'LPR Backend is running' });
});

server.listen(PORT, () => {
  console.log(`Server is running on http://localhost:${PORT}`);
});
