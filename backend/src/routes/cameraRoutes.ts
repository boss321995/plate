import { Router } from 'express';
import { getCameras, addCamera, updateCamera, deleteCamera, handleLiveFrame } from '../controllers/cameraController';

const router = Router();

router.get('/', getCameras);
router.post('/', addCamera);
router.post('/live_frame', handleLiveFrame);
router.put('/:id', updateCamera);
router.delete('/:id', deleteCamera);

export default router;
