import express from 'express';
import {
  getSites,
  getSite,
  createSite,
  updateSite,
  deleteSite,
  getModels,
  registerModel,
  activateModel,
  rollbackModel,
} from '../controllers/siteController';

const router = express.Router();

// Sites CRUD
router.get('/',     getSites);
router.get('/:id',  getSite);
router.post('/',    createSite);
router.put('/:id',  updateSite);
router.delete('/:id', deleteSite);

// Model registry (scoped under /api/sites/models for discovery)
router.get('/models',               getModels);
router.post('/models',              registerModel);
router.put('/models/:id/activate',  activateModel);
router.post('/models/:id/rollback', rollbackModel);

export default router;
