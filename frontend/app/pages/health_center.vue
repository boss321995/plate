<template>
  <div class="space-y-6">
    <!-- Page header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-display font-bold text-slate-900 dark:text-white">System Health Center</h2>
        <p class="text-sm text-slate-500 mt-0.5">Real-time diagnostics — auto-refresh every 10s</p>
      </div>
      <button @click="refresh" class="glass-card px-4 py-2 rounded-xl text-sm font-medium text-accent-cyan hover:bg-accent-cyan/10 transition-colors">
        Refresh
      </button>
    </div>

    <!-- Status summary bar -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <StatusCard label="AI Server"     :status="aiStatus"      icon="🤖" />
      <StatusCard label="Backend"       :status="backendStatus" icon="🗄️" />
      <StatusCard label="Camera"        :status="cameraStatus"  icon="📷" />
      <StatusCard label="Uploader"      :status="uploaderStatus" icon="📤" />
    </div>

    <!-- System resources -->
    <div class="glass-card rounded-2xl p-6">
      <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-5">System Resources</h3>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-6">
        <GaugeItem label="CPU"    :value="health.cpu_percent"    unit="%" :warn="70" :crit="85" />
        <GaugeItem label="Memory" :value="health.memory_percent" unit="%" :warn="75" :crit="90" />
        <GaugeItem label="Disk"   :value="diskPct"               unit="%" :warn="80" :crit="90" />
        <GaugeItem label="FPS"    :value="health.fps_current"    unit=" fps" :low="true" :warn="5" :crit="2" />
      </div>
    </div>

    <!-- Camera diagnostics -->
    <div class="glass-card rounded-2xl p-6">
      <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-4">Camera Diagnostics</h3>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <DiagBadge label="Focus Score"    :value="`${diag.focus_score ?? '—'}%`"   :ok="(diag.focus_score ?? 0) >= 60" />
        <DiagBadge label="Brightness"     :value="`${diag.brightness ?? '—'}`"     :ok="inRange(diag.brightness,30,220)" />
        <DiagBadge label="Lens Dirty"     :value="diag.lens_dirty ? 'Yes' : 'No'"  :ok="!diag.lens_dirty" :invert="true" />
        <DiagBadge label="Rain Detected"  :value="diag.rain_detected ? 'Yes' : 'No'" :ok="!diag.rain_detected" :invert="true" />
        <DiagBadge label="Camera Shift"   :value="diag.camera_shift ? 'Yes' : 'No'" :ok="!diag.camera_shift" :invert="true" />
        <DiagBadge label="Vibration"      :value="diag.vibration ? 'Yes' : 'No'"   :ok="!diag.vibration" :invert="true" />
        <DiagBadge label="Blockage"       :value="diag.blockage ? 'Yes' : 'No'"    :ok="!diag.blockage" :invert="true" />
        <DiagBadge label="Over-Exposure"  :value="diag.over_exposure ? 'Yes' : 'No'" :ok="!diag.over_exposure" :invert="true" />
      </div>
      <div v-if="diag.recommendation && diag.recommendation !== 'OK'"
           class="px-4 py-3 rounded-xl text-sm font-medium"
           :class="diag.status === 'CRITICAL'
             ? 'bg-accent-rose/10 text-accent-rose border border-accent-rose/20'
             : 'bg-accent-amber/10 text-accent-amber border border-accent-amber/20'">
        {{ diag.recommendation }}
      </div>
      <div v-else class="px-4 py-3 rounded-xl text-sm text-accent-emerald bg-accent-emerald/10 border border-accent-emerald/20">
        All camera checks passed
      </div>
    </div>

    <!-- Queue + latency -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div class="glass-card rounded-2xl p-5 text-center">
        <div class="text-3xl font-bold font-display" :class="queueColor">{{ health.queue_size ?? '—' }}</div>
        <div class="text-xs text-slate-500 mt-1">Pending Queue</div>
      </div>
      <div class="glass-card rounded-2xl p-5 text-center">
        <div class="text-3xl font-bold font-display text-slate-700 dark:text-slate-100">{{ health.network_latency_ms ?? '—' }}<span class="text-sm font-normal text-slate-400">ms</span></div>
        <div class="text-xs text-slate-500 mt-1">Network Latency</div>
      </div>
      <div class="glass-card rounded-2xl p-5 text-center">
        <div class="text-3xl font-bold font-display text-slate-700 dark:text-slate-100">{{ uptimeLabel }}</div>
        <div class="text-xs text-slate-500 mt-1">AI Uptime</div>
      </div>
    </div>

    <!-- Enterprise Alerts -->
    <div class="glass-card rounded-2xl p-6">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider">Recent Alerts</h3>
        <div class="flex space-x-3 text-xs">
          <span class="text-slate-400">INFO <span class="font-bold text-slate-600 dark:text-slate-300">{{ alertCounts.INFO ?? 0 }}</span></span>
          <span class="text-accent-amber">WARN <span class="font-bold">{{ alertCounts.WARNING ?? 0 }}</span></span>
          <span class="text-accent-rose">CRIT <span class="font-bold">{{ alertCounts.CRITICAL ?? 0 }}</span></span>
        </div>
      </div>
      <div v-if="alerts.length === 0" class="text-sm text-slate-400 italic">No alerts.</div>
      <div v-else class="space-y-2 max-h-72 overflow-y-auto">
        <div
          v-for="a in alerts"
          :key="a.ts"
          class="flex items-start space-x-3 text-sm px-3 py-2 rounded-lg"
          :class="alertRowClass(a.level)"
        >
          <span class="font-bold w-20 shrink-0" :class="alertTextClass(a.level)">{{ a.level }}</span>
          <span class="text-slate-600 dark:text-slate-300 font-medium w-28 shrink-0">{{ a.source }}</span>
          <span class="text-slate-500 flex-1 truncate">{{ a.message }}</span>
          <span class="text-slate-400 text-xs shrink-0">{{ tsLabel(a.ts) }}</span>
        </div>
      </div>
    </div>

    <p class="text-xs text-slate-400 text-right">Last updated: {{ lastUpdated || '—' }}</p>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

// ── Sub-components (defined inline) ─────────────────────────────────────────
const StatusCard = {
  props: ['label', 'status', 'icon'],
  template: `
    <div class="glass-card rounded-2xl p-4 flex items-center space-x-3">
      <span class="text-2xl">{{ icon }}</span>
      <div>
        <div class="text-xs text-slate-500">{{ label }}</div>
        <div class="text-sm font-bold mt-0.5"
          :class="status==='ok' ? 'text-accent-emerald' : status==='warn' ? 'text-accent-amber' : 'text-accent-rose'">
          {{ status === 'ok' ? 'Online' : status === 'warn' ? 'Degraded' : 'Offline' }}
        </div>
      </div>
    </div>
  `,
}

const GaugeItem = {
  props: ['label','value','unit','warn','crit','low'],
  computed: {
    color() {
      if (this.value == null) return 'text-slate-400'
      const v = parseFloat(this.value)
      if (this.low) {
        // Low values are bad (e.g. FPS)
        return v <= this.crit ? 'text-accent-rose' : v <= this.warn ? 'text-accent-amber' : 'text-accent-emerald'
      }
      return v >= this.crit ? 'text-accent-rose' : v >= this.warn ? 'text-accent-amber' : 'text-accent-emerald'
    }
  },
  template: `
    <div class="text-center">
      <div class="text-2xl font-bold font-display" :class="color">
        {{ value != null ? value : '—' }}<span class="text-sm font-normal text-slate-400">{{ unit }}</span>
      </div>
      <div class="text-xs text-slate-500 mt-1">{{ label }}</div>
    </div>
  `,
}

const DiagBadge = {
  props: ['label','value','ok'],
  template: `
    <div class="flex items-center justify-between p-3 rounded-xl bg-slate-50 dark:bg-white/5">
      <span class="text-xs text-slate-500">{{ label }}</span>
      <span class="text-xs font-bold" :class="ok ? 'text-accent-emerald' : 'text-accent-rose'">{{ value }}</span>
    </div>
  `,
}

// ── Data ─────────────────────────────────────────────────────────────────────
const config  = useRuntimeConfig()
const apiBase = config.public.apiBase || '/api'
const AI_URL  = config.public.aiBase  || 'http://localhost:8000'

const health      = ref({})
const diag        = ref({})
const alerts      = ref([])
const alertCounts = ref({})
const lastUpdated = ref(null)
let   timer       = null

// ── Computed status ───────────────────────────────────────────────────────────
const aiStatus      = computed(() => health.value.status === 'ok' ? 'ok' : 'error')
const backendStatus = computed(() => health.value.uptime_sec > 0 ? 'ok' : 'error')
const cameraStatus  = computed(() => {
  const cs = health.value.camera_status || {}
  const vals = Object.values(cs)
  if (vals.every(v => v === 'ok')) return 'ok'
  if (vals.some(v => v === 'lost')) return 'error'
  return 'warn'
})
const uploaderStatus = computed(() => {
  const q = health.value.queue_size ?? 0
  return q > 100 ? 'warn' : 'ok'
})

const diskPct     = computed(() => {
  const free = health.value.disk_free_gb
  if (free == null) return null
  // approximate: assume 50GB total disk
  return null  // backend doesn't expose total yet
})

const queueColor  = computed(() => {
  const q = health.value.queue_size ?? 0
  return q > 100 ? 'text-accent-rose' : q > 20 ? 'text-accent-amber' : 'text-accent-emerald'
})

const uptimeLabel = computed(() => {
  const s = health.value.uptime_sec
  if (s == null) return '—'
  if (s < 60)   return `${Math.floor(s)}s`
  if (s < 3600) return `${Math.floor(s/60)}m`
  return `${Math.floor(s/3600)}h ${Math.floor((s%3600)/60)}m`
})

// ── Helpers ───────────────────────────────────────────────────────────────────
function inRange(v, lo, hi) { return v != null && v >= lo && v <= hi }
function tsLabel(ts) {
  return new Date(ts * 1000).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
function alertRowClass(level) {
  return level === 'CRITICAL' ? 'bg-accent-rose/5' : level === 'WARNING' ? 'bg-accent-amber/5' : 'bg-slate-50 dark:bg-white/5'
}
function alertTextClass(level) {
  return level === 'CRITICAL' ? 'text-accent-rose' : level === 'WARNING' ? 'text-accent-amber' : 'text-slate-400'
}

// ── Fetch ─────────────────────────────────────────────────────────────────────
async function refresh() {
  try {
    // AI server health
    const h = await $fetch(`${AI_URL}/health`).catch(() => ({}))
    health.value = h || {}

    // AI server diagnostics
    const d = await $fetch(`${AI_URL}/diagnostics`).catch(() => ({}))
    diag.value = d || {}

    // AI server alerts
    const a = await $fetch(`${AI_URL}/alerts?n=30`).catch(() => ({ alerts: [], counts: {} }))
    alerts.value      = a?.alerts  || []
    alertCounts.value = a?.counts  || {}

    lastUpdated.value = new Date().toLocaleTimeString('th-TH')
  } catch (e) {
    console.error('[HealthCenter]', e)
  }
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 10_000)
})
onUnmounted(() => clearInterval(timer))
</script>
