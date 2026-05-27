import { Router } from 'express';
import { login, getMe } from '../controllers/authController';

const router = Router();

router.post('/login', login as any);
router.get('/me', getMe as any);

export default router;
