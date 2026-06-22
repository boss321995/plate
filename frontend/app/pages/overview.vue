<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-display font-bold text-slate-900 dark:text-white">System Overview</h2>
        <p class="text-sm text-slate-500 mt-0.5">Cross-fleet aggregated KPIs — auto-refresh every 30s</p>
      </div>
      <button @click="refresh" class="glass-card px-4 py-2 rounded-xl text-sm font-medium text-accent-cyan hover:bg-accent-cyan/10 transition-colors">
        Refresh
      </button>
    </div>

    <!-- KPI cards -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div v-for="kpi in kpiCards" :key="kpi.label" class="glass-card rounded-2xl p-5">
        <div class="flex items-start justify-between mb-3">
          <span class="text-2xl">{{ kpi.icon }}</span>
          <span class="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full"
                :class="kpi.ok ? 'bg-accent-emerald/10 text-accent-emerald' : 'bg-accent-rose/10 text-accent-rose'">
            {{ kpi.ok ? 'OK' : 'ALERT' }}
          </span>
        </div>
        <div class="text-2xl font-bold font-display" :class="kpi.ok ? 'text-slate-800 dark:text-white' : 'text-accent-rose'">
          {{ kpi.value }}
        </div>
        <div class="text-xs text-slate-500 mt-1">{{ kpi.label }}</div>
        <div class="text-[10px] text-slate-400">Target: {{ kpi.target }}</div>
      </div>
    </div>

    <!-- Fleet summary + Site summary side by side -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <!-- Fleet health -->
      <div class="glass-card rounded-2xl p-6">
        <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-4">Fleet Health</h3>
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <span class="text-sm text-slate-600 dark:text-slate-400">Total Devices</span>
            <span class="font-bold text-slate-800 dark:text-white">{{ fleet.total ?? '—' }}</span>
          </div>
          <div>
            <div class="flex items-center justify-between mb-1">
              <span class="text-sm text-accent-emerald">Online</span>
              <span class="font-bold text-accent-emerald">{{ fleet.online ?? 0 }}</span>
            </div>
            <div class="h-2 bg-slate-100 dark:bg-white/10 rounded-full overflow-hidden">
              <div class="h-full bg-accent-emerald rounded-full transition-all" :style="{ width: fleetOnlinePct }"></div>
            </div>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-accent-amber">Warning</span>
            <span class="font-bold text-accent-amber">{{ fleet.warning ?? 0 }}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-accent-rose">Offline</span>
            <span class="font-bold text-accent-rose">{{ fleet.offline ?? 0 }}</span>
          </div>
          <div class="pt-2 border-t border-slate-100 dark:border-white/[0.06] flex items-center justify-between">
            <span class="text-xs text-slate-500">Fleet Availability</span>
            <span class="font-bold" :class="fleet.health_pct >= 99 ? 'text-accent-emerald' : 'text-accent-amber'">
              {{ fleet.health_pct != null ? fleet.health_pct + '%' : '—' }}
            </span>
          </div>
        </div>
      </div>

      <!-- Sites -->
      <div class="glass-card rounded-2xl p-6">
        <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-4">Sites</h3>
        <div v-if="sites.length === 0" class="text-sm text-slate-400 italic">No sites configured.</div>
        <div v-else class="space-y-2">
          <div v-for="s in sites" :key="s.id"
               class="flex items-center justify-between py-2 border-b border-slate-100 dark:border-white/[0.04] last:border-0">
            <div>
              <div class="text-sm font-medium text-slate-700 dark:text-slate-200">{{ s.site_name }}</div>
              <div class="text-xs text-slate-400">{{ s.address || s.timezone }}</div>
            </div>
            <div class="text-right">
              <div class="text-sm font-bold text-slate-700 dark:text-slate-200">{{ s.device_count ?? 0 }}</div>
              <div class="text-[10px] text-slate-400">devices</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- AI Pipeline KPIs -->
    <div class="glass-card rounded-2xl p-6">
      <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-4">AI Pipeline (Live)</h3>
      <div class="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div v-for="m in pipelineMetrics" :key="m.label" class="text-center">
          <div class="text-2xl font-bold font-display" :class="m.color">{{ m.value }}</div>
          <div class="text-xs text-slate-500 mt-1">{{ m.label }}</div>
        </div>
      </div>
    </div>

    <!-- Active model + version -->
    <div class="glass-card rounded-2xl p-6">
      <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-4">Active Model Registry</h3>
      <div v-if="activeModels.length === 0" class="text-sm text-slate-400 italic">No active models.</div>
      <div v-else class="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div v-for="m in activeModels" :key="m.id" class="bg-slate-50 dark:bg-white/5 rounded-xl px-4 py-3">
          <div class="text-xs text-slate-400 uppercase">{{ m.model_type }}</div>
          <div class="font-semibold text-slate-800 dark:text-white mt-1">{{ m.model_name }}</div>
          <div class="text-sm text-accent-cyan font-mono">v{{ m.model_version }}</div>
          <div class="text-xs text-slate-400 mt-1">
            Accuracy: {{ m.accuracy ? (m.accuracy * 100).toFixed(1) + '%' : '—' }}
          </div>
        </div>
      </div>
    </div>

    <p class="text-xs text-slate-400 text-right">Last updated: {{ lastUpdated || '—' }}</p>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const config  = useRuntimeConfig()
const apiBase = config.public.apiBase || '/api'
const AI_URL  = config.public.aiBase  || 'http://localhost:8000'

const fleet        = ref({})
const sites        = ref([])
const metrics      = ref({})
const activeModels = ref([])
const lastUpdated  = ref(null)
let   timer        = null

const fleetOnlinePct = computed(() => {
  const total = fleet.value.total ?? 0
  return total ? Math.round((fleet.value.online ?? 0) / total * 100) + '%' : '0%'
})

const kpiCards = computed(() => {
  const pipe   = metrics.value?.pipeline ?? {}
  const ocr    = metrics.value?.ocr_performance ?? {}
  const seen   = pipe.vehicle_seen ?? 0
  const saved  = pipe.backend_saved ?? 0
  const yield_ = seen ? Math.round(saved / seen * 100) : 0
  const ocrPct = Math.round((ocr.success_rate ?? 0) * 100)
  const fp     = fleet.value.health_pct ?? 100
  const avg_ms = pipe.avg_latency_ms ?? 0

  return [
    {
      icon: '✅', label: 'Fleet Availability', value: fp + '%',
      ok: fp >= 99.9, target: '>99.95%',
    },
    {
      icon: '🔍', label: 'Detection Yield', value: yield_ + '%',
      ok: yield_ >= 99, target: '>99%',
    },
    {
      icon: '🔤', label: 'OCR Success Rate', value: ocrPct + '%',
      ok: ocrPct >= 95, target: '>95%',
    },
    {
      icon: '⚡', label: 'Avg Latency', value: avg_ms ? avg_ms + ' ms' : '—',
      ok: avg_ms < 1000 || avg_ms === 0, target: '<1000 ms',
    },
  ]
})

const pipelineMetrics = computed(() => {
  const p = metrics.value?.pipeline?.counters ?? {}
  return [
    { label: 'Vehicles Seen',   value: p.vehicle_seen     ?? 0, color: 'text-slate-700 dark:text-slate-100' },
    { label: 'Plates Detected', value: p.plate_detected   ?? 0, color: 'text-accent-cyan' },
    { label: 'OCR Success',     value: p.ocr_success      ?? 0, color: 'text-accent-emerald' },
    { label: 'Sent to Backend', value: p.backend_saved    ?? 0, color: 'text-accent-violet' },
    { label: 'Duplicates',      value: p.duplicate_suppressed ?? 0, color: 'text-slate-400' },
  ]
})

async function refresh() {
  try {
    const [fleetData, siteData, metricsData, modelData] = await Promise.all([
      $fetch(`${apiBase}/fleet`).catch(() => null),
      $fetch(`${apiBase}/sites`).catch(() => null),
      $fetch(`${AI_URL}/metrics`).catch(() => null),
      $fetch(`${apiBase}/sites/models`).catch(() => null),
    ])

    fleet.value        = fleetData?.data?.stats  ?? {}
    sites.value        = siteData?.data           ?? []
    metrics.value      = metricsData              ?? {}
    const allModels    = modelData?.data           ?? []
    activeModels.value = allModels.filter(m => m.is_active)
    lastUpdated.value  = new Date().toLocaleTimeString('th-TH')
  } catch (e) {
    console.error('[Overview]', e)
  }
}

onMounted(() => { refresh(); timer = setInterval(refresh, 30_000) })
onUnmounted(() => clearInterval(timer))
</script>
