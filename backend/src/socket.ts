import { Server as SocketIOServer } from 'socket.io';
import { Server as HttpServer } from 'http';

let io: SocketIOServer | null = null;

// ─────────────────────────────────────────────────────────────────────────────
// Part 13: Server-side throttle for high-frequency broadcasts
// Prevents stats_update spam when many vehicles are detected simultaneously.
// ─────────────────────────────────────────────────────────────────────────────
const STATS_THROTTLE_MS = parseInt(process.env.SOCKET_STATS_THROTTLE_MS || '2000', 10);

let _pendingStats: any = null;
let _statsTimer: NodeJS.Timeout | null = null;

function flushStats() {
  if (_pendingStats && io) {
    io.emit('stats_update', _pendingStats);
    _pendingStats = null;
  }
  _statsTimer = null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Extend Socket.IO Server with throttled emit helper
// ─────────────────────────────────────────────────────────────────────────────
type IoType = SocketIOServer & {
  emitThrottled: (event: string, data: any) => void;
};

export const initSocket = (httpServer: HttpServer): IoType => {
  const server = new SocketIOServer(httpServer, {
    cors: {
      origin:  process.env.CORS_ORIGIN || '*',
      methods: ['GET', 'POST'],
    },
    // Part 13: compress Socket.IO frames
    perMessageDeflate: true,
  }) as IoType;

  // Attach throttled emit — only stats_update is throttled; other events emit immediately
  server.emitThrottled = (event: string, data: any) => {
    if (event === 'stats_update') {
      _pendingStats = data;    // Overwrite with latest
      if (!_statsTimer) {
        _statsTimer = setTimeout(flushStats, STATS_THROTTLE_MS);
      }
    } else {
      server.emit(event, data);
    }
  };

  server.on('connection', (socket) => {
    console.log(`[Socket] Client connected: ${socket.id}`);
    socket.on('disconnect', () => {
      console.log(`[Socket] Client disconnected: ${socket.id}`);
    });
  });

  io = server;
  return server;
};

export const getIo = (): IoType | null => {
  if (!io) {
    console.warn('[Socket] Socket.io not initialized yet');
  }
  return io as IoType | null;
};
