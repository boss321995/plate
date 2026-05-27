import { Router } from 'express';
import { getActiveVehicles } from '../controllers/parkingController';

const router = Router();

router.get('/active', getActiveVehicles);

export default router;
