<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-xl font-display font-bold text-slate-900 dark:text-white">Vehicle Logs</h1>
        <p class="text-sm text-slate-500 mt-0.5">Review historical access logs · {{ totalCount.toLocaleString() }} records</p>
      </div>
      <button
        @click="exportExcel"
        class="btn-glow flex items-center space-x-2 text-white px-5 py-2.5 rounded-xl text-sm font-semibold"
        :disabled="isExporting"
      >
        <svg v-if="!isExporting" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
        <svg v-else class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
        <span class="relative z-10">{{ isExporting ? 'Exporting...' : 'Export Excel' }}</span>
      </button>
    </div>

    <!-- New data banner -->
    <transition name="fade">
      <div v-if="hasNewData" class="bg-brand-500/10 border border-brand-500/30 rounded-xl px-4 py-2.5 text-sm text-brand-600 dark:text-brand-400 flex items-center justify-between">
        <span>🔄 New detections available</span>
        <button @click="goToFirstPage" class="text-xs font-semibold underline">Refresh</button>
      </div>
    </transition>

    <!-- Table -->
    <div class="glass-card rounded-2xl overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-left text-sm whitespace-nowrap">
          <thead class="border-b border-slate-200 dark:border-white/[0.06]">
            <tr>
              <th class="px-5 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Plate Number</th>
              <th class="px-5 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Type</th>
              <th class="px-5 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider hidden md:table-cell">Direction</th>
              <th class="px-5 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Confidence</th>
              <th class="px-5 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider hidden lg:table-cell">Quality</th>
              <th class="px-5 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider hidden sm:table-cell">Time</th>
              <th class="px-5 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider hidden xl:table-cell">Track ID</th>
              <th class="px-5 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Image</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-200 dark:divide-white/[0.04]">
            <tr v-if="loading" class="text-center">
              <td colspan="8" class="px-6 py-12 text-slate-500">
                <svg class="animate-spin w-5 h-5 mx-auto mb-2 text-accent-cyan" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                Loading logs...
              </td>
            </tr>
            <tr v-else-if="logs.length === 0">
              <td colspan="8" class="px-6 py-12 text-center text-slate-500">No logs found.</td>
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
              <td class="px-5 py-3.5 font-mono font-bold text-slate-800 dark:text-white text-sm">
                {{ log.plate_number }}
                <span v-if="log.is_fuzzy_match" class="ml-1.5 text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-300 dark:border-amber-500/30" :title="log.original_ocr_text">🔍</span>
              </td>
              <td class="px-5 py-3.5">
                <span class="px-2.5 py-1 rounded-full text-[10px] font-bold tracking-wide" :class="typeColor(log.vehicle_type || 'VISITOR')">
                  {{ log.vehicle_type || 'VISITOR' }}
                </span>
              </td>
              <td class="px-5 py-3.5 hidden md:table-cell">
                <span class="flex items-center space-x-1.5" :class="log.direction === 'IN' ? 'text-accent-emerald' : 'text-brand-500 dark:text-brand-400'">
                  <span class="text-xs font-semibold">{{ log.direction || 'IN' }}</span>
                </span>
              </td>
              <td class="px-5 py-3.5">
                <div class="flex items-center space-x-2">
                  <div class="w-14 h-1.5 rounded-full bg-slate-200 dark:bg-white/5 overflow-hidden">
                    <div class="h-full rounded-full bg-gradient-to-r from-accent-cyan to-brand-500" :style="{ width: `${(log.confidence_score || 0) * 100}%` }"></div>
                  </div>
                  <span class="text-xs text-slate-500 font-medium">{{ ((log.confidence_score || 0) * 100).toFixed(0) }}%</span>
                </div>
              </td>
              <td class="px-5 py-3.5 hidden lg:table-cell">
                <span v-if="log.image_quality_score" class="text-xs font-medium" :class="log.image_quality_score > 0.6 ? 'text-emerald-500' : log.image_quality_score > 0.3 ? 'text-amber-500' : 'text-rose-500'">
                  {{ (log.image_quality_score * 100).toFixed(0) }}%
                </span>
                <span v-else class="text-slate-400 text-xs">—</span>
              </td>
              <td class="px-5 py-3.5 text-slate-500 dark:text-slate-400 text-xs hidden sm:table-cell">
                {{ formatTime(log.timestamp) }}
              </td>
              <td class="px-5 py-3.5 text-slate-400 text-[10px] font-mono hidden xl:table-cell">
                {{ log.track_id || '—' }}
              </td>
              <td class="px-5 py-3.5">
                <button
                  v-if="log.image_path"
                  @click="openImage(log)"
                  class="w-8 h-8 rounded-lg bg-brand-500/10 hover:bg-brand-500/20 flex items-center justify-center transition-colors"
                  title="View evidence image"
                >
                  <svg class="w-4 h-4 text-brand-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                </button>
                <span v-else class="text-slate-400 text-xs">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="px-6 py-4 border-t border-slate-200 dark:border-white/[0.06] flex items-center justify-between">
        <span class="text-sm text-slate-500">
          Showing <span class="font-semibold text-slate-800 dark:text-white">{{ logs.length }}</span>
          of <span class="font-semibold">{{ totalCount.toLocaleString() }}</span>
        </span>
        <div class="flex space-x-2">
          <button @click="changePage(page - 1)" :disabled="page === 1" class="px-4 py-1.5 glass-card rounded-lg text-sm font-medium text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all">Previous</button>
          <div class="flex items-center px-3 text-xs text-slate-500">{{ page }} / {{ totalPages }}</div>
          <button @click="changePage(page + 1)" :disabled="page >= totalPages" class="px-4 py-1.5 glass-card rounded-lg text-sm font-medium text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all">Next</button>
        </div>
      </div>
    </div>

    <!-- Image Lightbox -->
    <ClientOnly>
      <Teleport to="body">
        <div v-if="lightbox.show" class="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm" @click.self="lightbox.show = false">
          <div class="glass-strong rounded-2xl p-4 max-w-lg w-full relative">
            <button @click="lightbox.show = false" class="absolute top-3 right-3 w-8 h-8 rounded-lg glass-card flex items-center justify-center text-slate-400 hover:text-slate-900 dark:hover:text-white">✕</button>
            <p class="font-mono font-bold text-white mb-3">{{ lightbox.plate }}</p>
            <img :src="lightbox.src" class="w-full rounded-xl" alt="Evidence image" loading="lazy" />
            <p class="text-xs text-slate-500 mt-2">{{ lightbox.time }}</p>
          </div>
        </div>
      </Teleport>
    </ClientOnly>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useSocket } from '~/composables/useSocket'

definePageMeta({ middleware: 'auth' })

const { socket } = useSocket()
const config   = useRuntimeConfig()
const apiBase  = config.public.apiBase || ''

const logs       = ref([])
const page       = ref(1)
const totalPages = ref(1)
const totalCount = ref(0)
const loading    = ref(true)
const isExporting= ref(false)
const hasNewData = ref(false)
const lightbox   = ref({ show: false, src: '', plate: '', time: '' })

const fetchLogs = async () => {
  loading.value = true
  try {
    const res  = await fetch(`${apiBase}/api/logs?page=${page.value}&limit=20`)
    const data = await res.json()
    if (data.success) {
      logs.value       = data.data
      totalPages.value = data.pagination.totalPages
      totalCount.value = data.pagination.total
    }
  } catch (err) {
    console.error('[Logs] Fetch error:', err)
  } finally {
    loading.value = false
  }
}

const changePage = (newPage) => {
  if (newPage >= 1 && newPage <= totalPages.value) {
    page.value = newPage
    hasNewData.value = false
    fetchLogs()
  }
}

const goToFirstPage = () => { page.value = 1; fetchLogs() }

const exportExcel = () => {
  isExporting.value = true
  window.location.href = `${apiBase}/api/logs/export/excel`
  setTimeout(() => { isExporting.value = false }, 2000)
}

const typeColor = (type) => {
  if (type === 'BLACKLIST') return 'bg-accent-rose/15 text-rose-600 dark:text-rose-400'
  if (type === 'STAFF')     return 'bg-accent-emerald/15 text-emerald-600 dark:text-emerald-400'
  if (type === 'INTERNAL')  return 'bg-brand-500/15 text-blue-600 dark:text-blue-400'
  return 'bg-slate-200 dark:bg-white/5 text-slate-600 dark:text-slate-400'
}

const formatTime = (isoString) => {
  if (!isoString) return '—'
  return new Date(isoString).toLocaleString('th-TH', { dateStyle: 'medium', timeStyle: 'medium' })
}

const openImage = (log) => {
  lightbox.value = {
    show:  true,
    src:   `${apiBase}/static/logs/${log.image_path}`,
    plate: log.plate_number,
    time:  formatTime(log.timestamp),
  }
}

const handleNewDetection = (data) => {
  if (page.value !== 1) { hasNewData.value = true; return }
  const newRow = {
    id: data.id || Date.now(), plate_number: data.plate,
    vehicle_type: data.type, direction: data.dir,
    confidence_score: data.confidence || 0,
    image_quality_score: data.quality || 0,
    track_id: data.track_id, timestamp: new Date().toISOString(),
    is_fuzzy_match: data.isFuzzyMatch, original_ocr_text: data.originalOcr,
    image_path: null, isNew: true,
  }
  logs.value.unshift(newRow)
  if (logs.value.length > 20) logs.value.pop()
  setTimeout(() => { newRow.isNew = false }, 700)
  hasNewData.value = true
  setTimeout(() => { hasNewData.value = false }, 3000)
}

onMounted(async () => {
  await fetchLogs()
  const register = () => {
    if (!socket.value) return
    socket.value.on('new_detection', handleNewDetection)
  }
  if (socket.value) { register() }
  else { const iv = setInterval(() => { if (socket.value) { register(); clearInterval(iv) } }, 100) }
})

onUnmounted(() => {
  if (socket.value) socket.value.off('new_detection', handleNewDetection)
})
</script>

<style scoped>
@keyframes slide-in {
  from { opacity: 0; transform: translateX(-8px); }
  to   { opacity: 1; transform: translateX(0); }
}
.animate-slide-in { animation: slide-in 0.3s ease-out both; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to       { opacity: 0; }
</style>
