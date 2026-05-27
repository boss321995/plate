import express from 'express';
import { handleDetection, getRecentLogs, getStats, getChartData } from '../controllers/detectionController';

const router = express.Router();

router.post('/', handleDetection);
router.get('/logs', getRecentLogs);
router.get('/stats', getStats);
router.get('/chart', getChartData);

export default router;
