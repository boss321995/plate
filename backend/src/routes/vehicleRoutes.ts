import { Router } from 'express';
import { getVehicles, addVehicle, deleteVehicle } from '../controllers/vehicleController';

const router = Router();

router.get('/', getVehicles);
router.post('/', addVehicle);
router.delete('/:id', deleteVehicle);

export default router;
