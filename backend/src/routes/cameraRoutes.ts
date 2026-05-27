import { Router } from 'express';
import { getCameras, addCamera, updateCamera, deleteCamera } from '../controllers/cameraController';

const router = Router();

router.get('/', getCameras);
router.post('/', addCamera);
router.put('/:id', updateCamera);
router.delete('/:id', deleteCamera);

export default router;
