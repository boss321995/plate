/**
 * useSocket.ts
 * Shared Socket.IO composable — connects once, shared across all pages.
 * Emits: new_detection, stats_update
 */
import { ref, onMounted, onUnmounted } from 'vue'
import { io } from 'socket.io-client'

// Singleton socket instance (shared across all pages in the same tab)
let _socket: any = null
let _refCount = 0

const getSocket = () => {
  if (!_socket) {
    const base = useRuntimeConfig().public.apiBase || 'http://localhost:3001'
    _socket = io(base, {
      transports: ['websocket', 'polling'],
      reconnectionAttempts: 10,
      reconnectionDelay: 2000,
    })
    _socket.on('connect', () => console.log('[Socket] Connected:', _socket.id))
    _socket.on('disconnect', () => console.log('[Socket] Disconnected'))
  }
  return _socket
}

export const useSocket = () => {
  const socket = ref<any>(null)

  onMounted(() => {
    _refCount++
    socket.value = getSocket()
  })

  onUnmounted(() => {
    _refCount--
    // Only disconnect if no other component is using the socket
    if (_refCount <= 0 && _socket) {
      _socket.disconnect()
      _socket = null
      _refCount = 0
    }
  })

  return { socket }
}
