import express from 'express';
import {
  getFleet,
  getFleetStats,
  getFleetDevice,
  registerDevice,
  fleetHeartbeat,
  getDeviceConfig,
  updateDeviceConfig,
  getVersion,
  checkUpdate,
  rollbackUpdate,
  getBackupList,
  triggerBackup,
} from '../controllers/fleetController';

const router = express.Router();

// Device registry
router.get('/',                     getFleet);
router.get('/stats',                getFleetStats);
router.get('/:deviceId',            getFleetDevice);
router.post('/register',            registerDevice);
router.post('/heartbeat',           fleetHeartbeat);

// Remote config
router.get('/config/:deviceId',     getDeviceConfig);
router.put('/config/:deviceId',     updateDeviceConfig);

// OTA
router.get('/version',              getVersion);
router.post('/update/check',        checkUpdate);
router.post('/update/rollback',     rollbackUpdate);

// Backup
router.get('/backup/list',          getBackupList);
router.post('/backup/now',          triggerBackup);

export default router;
