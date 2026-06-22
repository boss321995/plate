import { Router } from 'express';
import { getActiveVehicles, getParkingStats } from '../controllers/parkingController';

const router = Router();

router.get('/active', getActiveVehicles);
router.get('/stats', getParkingStats);

export default router;
