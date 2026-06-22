<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-display font-bold text-slate-900 dark:text-white">Vehicle Logs</h1>
        <p class="text-sm text-slate-500 mt-0.5">Review historical access logs and export to Excel.</p>
      </div>
      <button 
        @click="exportExcel" 
        class="btn-glow flex items-center space-x-2 text-white px-5 py-2.5 rounded-xl text-sm font-semibold"
        :disabled="isExporting"
      >
        <svg v-if="!isExporting" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
        <svg v-else class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
        <span class="relative z-10">{{ isExporting ? 'Exporting...' : 'Export to Excel' }}</span>
      </button>
    </div>

    <!-- Table -->
    <div class="glass-card rounded-2xl overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-left text-sm whitespace-nowrap">
          <thead class="border-b border-slate-200 dark:border-white/[0.06]">
            <tr>
              <th class="px-6 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Plate Number</th>
              <th class="px-6 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Type</th>
              <th class="px-6 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Direction</th>
              <th class="px-6 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Confidence</th>
              <th class="px-6 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Time</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-200 dark:divide-white/[0.04]">
            <tr v-if="loading" class="text-center">
              <td colspan="5" class="px-6 py-12 text-slate-500">
                <svg class="animate-spin w-5 h-5 mx-auto mb-2 text-accent-cyan" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                Loading logs...
              </td>
            </tr>
            <tr v-else-if="logs.length === 0" class="text-center">
              <td colspan="5" class="px-6 py-12 text-slate-500">No logs found.</td>
            </tr>
            <tr
              v-else
              v-for="log in logs"
              :key="log.id"
              :class="[
                'hover:bg-slate-100/50 dark:hover:bg-white/[0.03] transition-colors',
                log.isNew ? 'animate-slide-in' : ''
              ]"
            >
              <td class="px-6 py-3.5 font-mono font-bold text-slate-800 dark:text-white text-sm">
                {{ log.plate_number }}
              </td>
              <td class="px-6 py-3.5">
                <span class="px-2.5 py-1 rounded-full text-[10px] font-bold tracking-wide" :class="typeColor(log.vehicle_type || 'VISITOR')">
                  {{ log.vehicle_type || 'VISITOR' }}
                </span>
              </td>
              <td class="px-6 py-3.5">
                <span class="flex items-center space-x-1.5" :class="log.direction === 'IN' ? 'text-accent-emerald' : 'text-brand-500 dark:text-brand-400'">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path v-if="log.direction === 'IN'" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1"></path>
                    <path v-else stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l4-4m-4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path>
                  </svg>
                  <span class="text-xs font-semibold">{{ log.direction || 'IN' }}</span>
                </span>
              </td>
              <td class="px-6 py-3.5">
                <div class="flex items-center space-x-2">
                  <div class="w-16 h-1.5 rounded-full bg-slate-200 dark:bg-white/5 overflow-hidden">
                    <div class="h-full rounded-full bg-gradient-to-r from-accent-cyan to-brand-500 transition-all" :style="{ width: `${log.confidence_score * 100}%` }"></div>
                  </div>
                  <span class="text-xs text-slate-500 dark:text-slate-400 font-medium">{{ (log.confidence_score * 100).toFixed(0) }}%</span>
                </div>
              </td>
              <td class="px-6 py-3.5 text-slate-500 dark:text-slate-400 text-xs">
                {{ formatTime(log.timestamp) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      
      <!-- Pagination -->
      <div class="px-6 py-4 border-t border-slate-200 dark:border-white/[0.06] flex items-center justify-between">
        <span class="text-sm text-slate-500">
          Showing <span class="font-semibold text-slate-800 dark:text-white">{{ logs.length }}</span> entries
        </span>
        <div class="flex space-x-2">
          <button @click="changePage(page - 1)" :disabled="page === 1" class="px-4 py-1.5 glass-card rounded-lg text-sm font-medium text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all">Previous</button>
          <div class="flex items-center px-3 text-xs text-slate-500">Page {{ page }} / {{ totalPages }}</div>
          <button @click="changePage(page + 1)" :disabled="page >= totalPages" class="px-4 py-1.5 glass-card rounded-lg text-sm font-medium text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all">Next</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useSocket } from '~/composables/useSocket'

definePageMeta({
  middleware: 'auth'
})

const { socket } = useSocket()
const apiBase = useRuntimeConfig().public.apiBase || 'http://localhost:3001'

const logs = ref([])
const page = ref(1)
const totalPages = ref(1)
const loading = ref(true)
const isExporting = ref(false)
// Live dot: blinks when new data arrives
const hasNewData = ref(false)

const fetchLogs = async () => {
  loading.value = true
  try {
    const res = await fetch(`${apiBase}/api/logs?page=${page.value}&limit=15`)
    const data = await res.json()
    if (data.success) {
      logs.value = data.data
      totalPages.value = data.pagination.totalPages
    }
  } catch (error) {
    console.error('Error fetching logs:', error)
  } finally {
    loading.value = false
  }
}

const changePage = (newPage) => {
  if (newPage >= 1 && newPage <= totalPages.value) {
    page.value = newPage
    fetchLogs()
  }
}

const exportExcel = async () => {
  isExporting.value = true
  try {
    window.location.href = `${apiBase}/api/logs/export/excel`
  } catch (error) {
    console.error('Export failed', error)
  }
  setTimeout(() => { isExporting.value = false }, 2000)
}

const typeColor = (type) => {
  if (type === 'BLACKLIST') return 'bg-accent-rose/15 text-rose-600 dark:text-rose-400'
  if (type === 'STAFF') return 'bg-accent-emerald/15 text-emerald-600 dark:text-emerald-400'
  if (type === 'INTERNAL') return 'bg-brand-500/15 text-blue-600 dark:text-blue-400'
  if (type === 'VISITOR' || type === 'UNKNOWN') return 'bg-slate-200 dark:bg-white/5 text-slate-600 dark:text-slate-400'
  return 'bg-accent-amber/15 text-amber-600 dark:text-amber-400'
}

const formatTime = (isoString) => {
  const date = new Date(isoString)
  return date.toLocaleString('th-TH', { dateStyle: 'medium', timeStyle: 'medium' })
}

// ─── Realtime: New detection - prepend row on page 1 only ──────────────────
const handleNewDetection = (data) => {
  if (page.value !== 1) {
    // User is on page 2+ — just flash a "new data" indicator, don't disrupt pagination
    hasNewData.value = true
    return
  }

  // Map socket payload to the same shape as the logs table expects
  const newRow = {
    id: data.id || Date.now(),
    plate_number: data.plate,
    vehicle_type: data.type,
    direction: data.dir,
    confidence_score: data.confidence || 0,
    timestamp: new Date().toISOString(),
    isNew: true,  // triggers slide-in animation
  }

  logs.value.unshift(newRow)
  if (logs.value.length > 15) logs.value.pop()

  // Remove animation flag after animation completes
  setTimeout(() => { newRow.isNew = false }, 700)

  // Flash indicator
  hasNewData.value = true
  setTimeout(() => { hasNewData.value = false }, 2000)
}

onMounted(async () => {
  await fetchLogs()

  const register = () => {
    if (!socket.value) return
    socket.value.on('new_detection', handleNewDetection)
  }

  if (socket.value) {
    register()
  } else {
    const iv = setInterval(() => { if (socket.value) { register(); clearInterval(iv) } }, 100)
  }
})

onUnmounted(() => {
  if (socket.value) socket.value.off('new_detection', handleNewDetection)
})
</script>
