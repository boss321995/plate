import express from 'express';
import { handleDetection, getRecentLogs, getStats, getChartData, getMetrics } from '../controllers/detectionController';

const router = express.Router();

router.post('/', handleDetection);
router.get('/logs', getRecentLogs);
router.get('/stats', getStats);
router.get('/chart', getChartData);
router.get('/metrics', getMetrics);

export default router;
