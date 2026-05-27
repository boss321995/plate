import { Router } from 'express';
import { getLogs, exportLogsExcel } from '../controllers/logController';

const router = Router();

router.get('/', getLogs);
router.get('/export/excel', exportLogsExcel);

export default router;
