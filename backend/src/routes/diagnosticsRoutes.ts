import express from 'express';
import {
  getDiagnostics,
  postCameraHealth,
  getAuditLog,
  postAuditEvent,
} from '../controllers/diagnosticsController';

const router = express.Router();

router.get('/',          getDiagnostics);
router.post('/health',   postCameraHealth);
router.get('/audit',     getAuditLog);
router.post('/audit',    postAuditEvent);

export default router;
