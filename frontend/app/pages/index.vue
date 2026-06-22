<template>
  <div class="space-y-6">
    <!-- Stats Row -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
      <div
        v-for="(stat, idx) in stats"
        :key="stat.title"
        class="glass-card rounded-2xl p-5 relative overflow-hidden group cursor-default"
        :style="{ animationDelay: `${idx * 100}ms` }"
      >
        <div class="absolute -right-8 -top-8 w-24 h-24 rounded-full blur-2xl opacity-30 group-hover:opacity-50 transition-opacity duration-500" :style="{ background: stat.glow }"></div>
        <div class="absolute inset-0 overflow-hidden rounded-2xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity">
          <div class="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.03] to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000"></div>
        </div>
        <div class="relative z-10 flex items-center justify-between">
          <div>
            <p class="text-xs font-medium text-slate-500 mb-1 uppercase tracking-wider">{{ stat.title }}</p>
            <h3 class="text-3xl font-display font-bold text-slate-800 dark:text-white tracking-tight">{{ stat.value }}</h3>
          </div>
          <div
            class="w-11 h-11 rounded-xl flex items-center justify-center transition-all duration-300 group-hover:scale-110"
            :style="{ background: stat.iconBg, color: stat.iconColor }"
            v-html="stat.icon"
          ></div>
        </div>
        <div class="relative z-10 mt-3 flex items-center text-[11px] text-slate-500 dark:text-slate-600">
          <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
          Since 00:00 Today
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Chart + Camera Snapshot (lazy loaded) -->
      <div class="lg:col-span-2 space-y-6">
        <!-- Traffic Chart -->
        <div class="glass-card rounded-2xl p-6 relative overflow-hidden">
          <div class="absolute top-0 right-0 w-48 h-48 bg-brand-500/5 rounded-full blur-3xl pointer-events-none"></div>
          <div class="flex items-center justify-between mb-6 relative z-10">
            <div>
              <h2 class="text-base font-display font-bold text-slate-900 dark:text-white">Traffic Overview</h2>
              <p class="text-xs text-slate-500 mt-0.5">Vehicle detections per 2-hour interval</p>
            </div>
          </div>
          <div class="h-52 w-full pt-2 relative z-10">
            <!-- Lazy-loaded chart: only mounted when chart data is ready -->
            <ClientOnly>
              <Suspense>
                <LazyApexChart
                  v-if="chartReady"
                  type="area"
                  height="100%"
                  :options="chartOptions"
                  :series="chartSeries"
                />
                <template #fallback>
                  <div class="h-full flex items-center justify-center text-slate-400 text-sm">Loading chart...</div>
                </template>
              </Suspense>
            </ClientOnly>
          </div>
        </div>

        <!-- Camera Live Snapshot (polling every 2s instead of Base64 stream) -->
        <div class="glass-card rounded-2xl p-4 relative overflow-hidden">
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full bg-rose-500 animate-pulse neon-dot text-rose-500"></span>
              <h2 class="text-sm font-display font-bold text-slate-900 dark:text-white">Live Camera</h2>
            </div>
            <span class="text-[10px] text-slate-500 glass-card rounded-lg px-2 py-1">
              {{ cameraOnline ? '🟢 Online' : '🔴 Offline' }} · {{ snapshotAge }}s ago
            </span>
          </div>
          <!-- Snapshot img: browser caches, we poll by appending timestamp -->
          <div class="relative rounded-xl overflow-hidden bg-slate-900/60 aspect-video">
            <img
              v-if="snapshotSrc"
              :src="snapshotSrc"
              class="w-full h-full object-contain"
              :class="{ 'opacity-50': !cameraOnline }"
              alt="Live camera snapshot"
              loading="lazy"
              decoding="async"
            />
            <div v-else class="absolute inset-0 flex items-center justify-center text-slate-500 text-sm">
              <div class="text-center">
                <svg class="w-8 h-8 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.362a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                Connecting to camera...
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Live Detections (virtual scroll for large lists) -->
      <div class="glass-card rounded-2xl p-6 flex flex-col h-[540px] relative overflow-hidden">
        <div class="absolute bottom-0 left-0 w-48 h-48 bg-accent-emerald/5 rounded-full blur-3xl pointer-events-none"></div>
        <div class="flex items-center justify-between mb-4 relative z-10">
          <div>
            <h2 class="text-base font-display font-bold text-slate-900 dark:text-white flex items-center">
              <span class="w-2 h-2 rounded-full bg-accent-emerald mr-2 neon-dot text-accent-emerald animate-pulse"></span>
              Live Activity
            </h2>
            <p class="text-xs text-slate-500 mt-0.5">Real-time detections</p>
          </div>
          <span class="text-[10px] text-slate-500 font-medium glass-card rounded-lg px-2 py-1">{{ recentLogs.length }} events</span>
        </div>

        <!-- Virtual scroll container — only renders visible rows -->
        <div ref="logListEl" class="flex-1 overflow-y-auto space-y-2.5 pr-1 relative z-10 custom-scrollbar">
          <template v-for="(log, i) in visibleLogs" :key="log.id">
            <div
              :class="[
                'p-3 rounded-xl border transition-all flex items-center justify-between group',
                log.isNew ? 'animate-slide-in' : '',
                log.type === 'BLACKLIST'
                  ? 'bg-rose-500/10 border-rose-500/30 hover:bg-rose-500/20'
                  : 'bg-slate-100/50 dark:bg-white/[0.03] border-slate-200 dark:border-white/[0.05] hover:bg-slate-200/50 dark:hover:bg-white/[0.06]'
              ]"
              :style="{ animationDelay: `${i * 40}ms` }"
            >
              <div>
                <div class="flex items-center space-x-2 flex-wrap gap-1">
                  <span class="font-bold text-slate-800 dark:text-white tracking-wide border border-slate-300 dark:border-white/10 px-2 py-0.5 rounded-lg text-sm bg-white/50 dark:bg-white/5 font-mono">{{ log.plate }}</span>
                  <span :class="typeColor(log.type)" class="text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider">{{ log.type }}</span>
                  <span v-if="log.isFuzzyMatch" class="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-300 dark:border-amber-500/30" :title="`OCR: ${log.originalOcr}`">
                    🔍 Fuzzy
                  </span>
                </div>
                <p class="text-[11px] text-slate-500 mt-1.5 flex items-center">
                  <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                  {{ log.time }}
                  <span v-if="log.quality" class="ml-2 text-slate-400">q={{ (log.quality * 100).toFixed(0) }}%</span>
                </p>
              </div>
              <div :class="log.dir === 'IN' ? 'text-accent-emerald bg-accent-emerald/10 border-accent-emerald/20' : 'text-accent-amber bg-accent-amber/10 border-accent-amber/20'" class="w-10 h-10 rounded-xl flex items-center justify-center font-bold text-xs border flex-shrink-0">
                {{ log.dir }}
              </div>
            </div>
          </template>

          <div v-if="recentLogs.length === 0" class="flex-1 flex items-center justify-center text-slate-400 dark:text-slate-600 text-sm py-12">
            <div class="text-center">
              <svg class="w-8 h-8 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"></path></svg>
              Waiting for detections...
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Blacklist Alert Overlay -->
  <ClientOnly>
    <Teleport to="body">
      <div v-if="blacklistAlert.show" class="fixed inset-0 z-[100] flex items-center justify-center pointer-events-none">
        <div class="absolute inset-0 bg-rose-600/20 animate-pulse"></div>
        <div class="glass-strong rounded-3xl p-8 border-2 border-rose-500 shadow-[0_0_100px_rgba(244,63,94,0.4)] animate-bounce text-center relative z-10 max-w-md w-full mx-4 bg-slate-900/90">
          <div class="w-20 h-20 bg-rose-500/20 rounded-full flex items-center justify-center mx-auto mb-4 border border-rose-500/50">
            <svg class="w-10 h-10 text-rose-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
          </div>
          <h2 class="text-3xl font-display font-bold text-rose-500 mb-2 uppercase tracking-wider">Blacklist Alert</h2>
          <p class="text-slate-300 text-lg mb-4">Unauthorized vehicle detected!</p>
          <div class="bg-black/50 border border-rose-500/30 rounded-xl py-3 px-6 inline-block font-mono text-2xl text-white font-bold tracking-widest shadow-inner">
            {{ blacklistAlert.plate }}
          </div>
          <div class="mt-4 text-rose-400 text-sm font-semibold">Gate: {{ blacklistAlert.dir }} &bull; Just Now</div>
        </div>
      </div>
    </Teleport>
  </ClientOnly>

  <!-- Anomaly Alert -->
  <ClientOnly>
    <Teleport to="body">
      <div v-if="anomalyAlert.show" class="fixed inset-0 z-[100] flex items-center justify-center pointer-events-none">
        <div class="absolute inset-0 bg-amber-600/20 animate-pulse"></div>
        <div class="glass-strong rounded-3xl p-8 border-2 border-amber-500 shadow-[0_0_80px_rgba(245,158,11,0.4)] text-center relative z-10 max-w-md w-full mx-4 bg-slate-900/90">
          <div class="w-20 h-20 bg-amber-500/20 rounded-full flex items-center justify-center mx-auto mb-4 border border-amber-500/50">
            <svg class="w-10 h-10 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path></svg>
          </div>
          <h2 class="text-2xl font-display font-bold text-amber-500 mb-2 uppercase tracking-wider">Anomaly Detected</h2>
          <p class="text-slate-300 text-sm mb-4">{{ anomalyAlert.message }}</p>
          <div class="bg-black/50 border border-amber-500/30 rounded-xl py-3 px-6 inline-block font-mono text-2xl text-white font-bold tracking-widest">
            {{ anomalyAlert.plate }}
          </div>
        </div>
      </div>
    </Teleport>
  </ClientOnly>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useSocket } from '~/composables/useSocket'
import { useTheme } from '~/composables/useTheme'

definePageMeta({ middleware: 'auth' })

const { isDark }   = useTheme()
const { socket }   = useSocket()
const config       = useRuntimeConfig()
const apiBase      = config.public.apiBase || ''

// ─── Constants ─────────────────────────────────────────────────────────────
const SNAPSHOT_INTERVAL = config.public.snapshotInterval || 2000   // 2s
const SOCKET_THROTTLE   = config.public.socketThrottle   || 2000   // 2s
const MAX_LOGS          = 50   // Virtual scroll: keep last 50 in memory

// ─── State ─────────────────────────────────────────────────────────────────
const blacklistAlert = ref({ show: false, plate: '', dir: '' })
const anomalyAlert   = ref({ show: false, plate: '', message: '' })
const recentLogs     = ref([])
const chartReady     = ref(false)
const cameraOnline   = ref(false)
const snapshotSrc    = ref(null)
const snapshotAge    = ref(0)

// Virtual scroll: only render last 20 visible entries
const visibleLogs = computed(() => recentLogs.value.slice(0, 20))

// ─── Stats ─────────────────────────────────────────────────────────────────
const stats = ref([
  {
    title: 'Total Vehicles', value: '—',
    glow: 'rgba(6,182,212,0.4)', iconBg: 'rgba(6,182,212,0.1)', iconColor: '#06b6d4',
    icon: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>'
  },
  {
    title: 'Staff / Internal', value: '—',
    glow: 'rgba(16,185,129,0.4)', iconBg: 'rgba(16,185,129,0.1)', iconColor: '#10b981',
    icon: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>'
  },
  {
    title: 'Visitors', value: '—',
    glow: 'rgba(245,158,11,0.4)', iconBg: 'rgba(245,158,11,0.1)', iconColor: '#f59e0b',
    icon: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>'
  },
  {
    title: 'Active Inside', value: '—',
    glow: 'rgba(139,92,246,0.4)', iconBg: 'rgba(139,92,246,0.1)', iconColor: '#8b5cf6',
    icon: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path></svg>'
  },
])

// ─── Chart ─────────────────────────────────────────────────────────────────
const chartSeries = ref([{ name: 'Vehicles', data: Array(12).fill(0) }])

const chartOptions = computed(() => ({
  chart: {
    type: 'area', toolbar: { show: false },
    fontFamily: 'Inter, sans-serif', background: 'transparent',
    // Disable animation on data updates (much faster on mobile)
    animations: { enabled: true, speed: 400, dynamicAnimation: { enabled: true, speed: 200 } }
  },
  theme:  { mode: isDark.value ? 'dark' : 'light' },
  colors: ['#06b6d4'],
  fill: {
    type: 'gradient',
    gradient: { opacityFrom: 0.35, opacityTo: 0.02, stops: [0, 100] }
  },
  dataLabels: { enabled: false },
  stroke:     { curve: 'smooth', width: 2.5, colors: ['#06b6d4'] },
  xaxis: {
    categories: ['00','02','04','06','08','10','12','14','16','18','20','22'],
    axisBorder: { show: false }, axisTicks: { show: false },
    labels: { style: { colors: '#64748b', fontSize: '11px' } }
  },
  yaxis: { labels: { style: { colors: '#64748b', fontSize: '11px' } } },
  grid: {
    borderColor: isDark.value ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.05)',
    strokeDashArray: 4, xaxis: { lines: { show: false } }
  },
  tooltip: { theme: isDark.value ? 'dark' : 'light', style: { fontSize: '12px' } }
}))

// ─── Helpers ───────────────────────────────────────────────────────────────
const typeColor = (type) => {
  if (type === 'BLACKLIST') return 'bg-accent-rose/15 text-rose-600 dark:text-rose-400'
  if (type === 'STAFF')     return 'bg-accent-emerald/15 text-emerald-500 dark:text-emerald-400'
  if (type === 'INTERNAL')  return 'bg-brand-500/15 text-blue-500 dark:text-blue-400'
  return 'bg-accent-amber/15 text-amber-500 dark:text-amber-400'
}

const playAlertSound = () => {
  try {
    const a = new Audio('https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3')
    a.play().catch(() => {})
  } catch (_) {}
}

// ─── Initial Data Fetch ────────────────────────────────────────────────────
const fetchDashboardData = async () => {
  try {
    const [statsRes, logsRes, chartRes] = await Promise.all([
      fetch(`${apiBase}/api/detect/stats`),
      fetch(`${apiBase}/api/detect/logs?limit=20`),
      fetch(`${apiBase}/api/detect/chart`),
    ])

    if (statsRes.ok) {
      const d = await statsRes.json()
      if (d.success) updateStats(d.data)
    }
    if (logsRes.ok) {
      const d = await logsRes.json()
      if (d.success) recentLogs.value = d.data
    }
    if (chartRes.ok) {
      const d = await chartRes.json()
      if (d.success) updateChart(d.data)
    }

    // Defer chart mount until initial data is ready (avoids layout shift)
    chartReady.value = true
  } catch (err) {
    console.error('[Dashboard] Fetch error:', err)
    chartReady.value = true  // Show chart anyway
  }
}

const updateStats = (data) => {
  stats.value[0].value = data.total
  stats.value[1].value = data.staff
  stats.value[2].value = data.visitor
  stats.value[3].value = data.active
}

const updateChart = (rows) => {
  const counts = Array(12).fill(0)
  rows.forEach(d => {
    const slot = Math.floor(parseInt(d.hour) / 2)
    if (slot >= 0 && slot < 12) counts[slot] += d.count
  })
  // Update data only — do NOT replace series object (avoids full re-render)
  chartSeries.value[0].data = counts
  chartSeries.value = [...chartSeries.value]
}

// ─── Camera Snapshot Polling (every 2s) ────────────────────────────────────
let snapshotTimer = null
let snapshotTs    = 0

const pollSnapshot = async () => {
  const AI_URL = config.public.aiSnapshotUrl || `${apiBase}/api/cameras/snapshot`
  try {
    // Append timestamp to bust browser cache per poll
    snapshotSrc.value = `${AI_URL}?t=${Date.now()}`
    cameraOnline.value = true
    snapshotTs         = Math.floor(Date.now() / 1000)
  } catch (_) {
    cameraOnline.value = false
  }
}

// Track snapshot age (displayed next to camera status)
let ageTimer = null
const updateAge = () => {
  snapshotAge.value = snapshotTs ? Math.floor(Date.now() / 1000) - snapshotTs : 0
}

// ─── Socket.IO — Throttled event aggregation (2s batch) ───────────────────
let socketBatch = { detections: [], statsUpdate: null, anomaly: null }
let batchTimer  = null

const flushBatch = () => {
  // Apply all queued detections at once
  if (socketBatch.detections.length > 0) {
    const newEntries = socketBatch.detections.map(d => ({ ...d, isNew: true }))
    recentLogs.value = [...newEntries, ...recentLogs.value].slice(0, MAX_LOGS)
    // Clear isNew after animation
    setTimeout(() => {
      newEntries.forEach(e => { e.isNew = false })
    }, 600)
    socketBatch.detections = []

    // Blacklist alert (last one in batch)
    const blacklisted = newEntries.find(e => e.isBlacklist || e.type === 'BLACKLIST')
    if (blacklisted) {
      blacklistAlert.value = { show: true, plate: blacklisted.plate, dir: blacklisted.dir }
      playAlertSound()
      setTimeout(() => { blacklistAlert.value.show = false }, 5000)
    }
  }

  // Stats — apply only the most recent update
  if (socketBatch.statsUpdate) {
    updateStats(socketBatch.statsUpdate)
    // Bump chart slot
    const slot = Math.floor(new Date().getHours() / 2)
    chartSeries.value[0].data[slot] = (chartSeries.value[0].data[slot] || 0) + socketBatch.detections.length || 1
    chartSeries.value = [...chartSeries.value]
    socketBatch.statsUpdate = null
  }

  // Anomaly
  if (socketBatch.anomaly) {
    anomalyAlert.value = { show: true, ...socketBatch.anomaly }
    playAlertSound()
    setTimeout(() => { anomalyAlert.value.show = false }, 8000)
    socketBatch.anomaly = null
  }

  batchTimer = null
}

const scheduleBatch = () => {
  if (!batchTimer) {
    batchTimer = setTimeout(flushBatch, SOCKET_THROTTLE)
  }
}

const handleNewDetection = (data) => {
  socketBatch.detections.push(data)
  scheduleBatch()
}

const handleStatsUpdate = (data) => {
  socketBatch.statsUpdate = data
  scheduleBatch()
}

const handleAnomalyAlert = (data) => {
  socketBatch.anomaly = data
  scheduleBatch()
}

// ─── Lifecycle ─────────────────────────────────────────────────────────────
onMounted(async () => {
  await fetchDashboardData()

  // Start camera snapshot poll
  pollSnapshot()
  snapshotTimer = setInterval(pollSnapshot, SNAPSHOT_INTERVAL)
  ageTimer      = setInterval(updateAge, 1000)

  // Register socket events
  const tryRegister = () => {
    if (!socket.value) return
    socket.value.on('new_detection', handleNewDetection)
    socket.value.on('stats_update',  handleStatsUpdate)
    socket.value.on('anomaly_alert', handleAnomalyAlert)
  }

  if (socket.value) {
    tryRegister()
  } else {
    const poll = setInterval(() => {
      if (socket.value) { tryRegister(); clearInterval(poll) }
    }, 100)
  }
})

onUnmounted(() => {
  clearInterval(snapshotTimer)
  clearInterval(ageTimer)
  clearTimeout(batchTimer)
  if (socket.value) {
    socket.value.off('new_detection', handleNewDetection)
    socket.value.off('stats_update',  handleStatsUpdate)
    socket.value.off('anomaly_alert', handleAnomalyAlert)
  }
})
</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 3px; }
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb);
  border-radius: 3px;
}

/* Slide-in animation for new log entries */
@keyframes slide-in {
  from { opacity: 0; transform: translateY(-8px); }
  to   { opacity: 1; transform: translateY(0); }
}
.animate-slide-in {
  animation: slide-in 0.3s ease-out both;
}
</style>
