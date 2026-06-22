<template>
  <div class="space-y-6">
    <!-- Header row -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-display font-bold text-slate-900 dark:text-white">Pipeline Debug</h2>
        <p class="text-sm text-slate-500 mt-0.5">Real-time AI pipeline counters & system metrics</p>
      </div>
      <div class="flex items-center space-x-3">
        <span class="text-xs text-slate-400">Auto-refresh every 5s</span>
        <button
          @click="fetchMetrics"
          class="glass-card px-4 py-2 rounded-xl text-sm font-medium text-accent-cyan hover:bg-accent-cyan/10 transition-colors"
        >
          Refresh Now
        </button>
      </div>
    </div>

    <!-- Error banner -->
    <div v-if="error" class="glass-card border border-accent-rose/30 rounded-2xl p-4 text-accent-rose text-sm">
      {{ error }}
    </div>

    <!-- Pipeline stage funnel -->
    <div class="glass-card rounded-2xl p-6">
      <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4 uppercase tracking-wider">
        AI Pipeline Stages (Thin Client)
      </h3>
      <div class="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div v-for="stage in pipelineStages" :key="stage.key" class="text-center">
          <div
            class="text-2xl font-bold font-display"
            :class="stage.color"
          >
            {{ aiCounter(stage.key) }}
          </div>
          <div class="text-xs text-slate-500 mt-1 leading-tight">{{ stage.label }}</div>
          <div v-if="stage.rate !== undefined" class="text-[10px] text-slate-400 mt-0.5">
            {{ stage.rate }}
          </div>
        </div>
      </div>

      <!-- Yield & OCR rate bars -->
      <div class="mt-6 space-y-3">
        <div>
          <div class="flex justify-between text-xs text-slate-500 mb-1">
            <span>Yield Rate (vehicle → saved)</span>
            <span class="font-medium">{{ yieldPct }}%</span>
          </div>
          <div class="h-2 bg-slate-200 dark:bg-white/10 rounded-full overflow-hidden">
            <div
              class="h-full bg-gradient-to-r from-accent-cyan to-brand-500 rounded-full transition-all duration-700"
              :style="{ width: yieldPct + '%' }"
            ></div>
          </div>
        </div>
        <div>
          <div class="flex justify-between text-xs text-slate-500 mb-1">
            <span>OCR Success Rate (plate detected → OCR ok)</span>
            <span class="font-medium">{{ ocrPct }}%</span>
          </div>
          <div class="h-2 bg-slate-200 dark:bg-white/10 rounded-full overflow-hidden">
            <div
              class="h-full bg-gradient-to-r from-accent-emerald to-accent-cyan rounded-full transition-all duration-700"
              :style="{ width: ocrPct + '%' }"
            ></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Rejection breakdown -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div
        v-for="rej in rejections"
        :key="rej.key"
        class="glass-card rounded-2xl p-5 flex items-center space-x-4"
      >
        <div class="w-12 h-12 rounded-xl flex items-center justify-center" :class="rej.bg">
          <span class="text-xl" v-html="rej.icon"></span>
        </div>
        <div>
          <div class="text-2xl font-bold font-display" :class="rej.color">
            {{ aiCounter(rej.key) }}
          </div>
          <div class="text-xs text-slate-500">{{ rej.label }}</div>
        </div>
      </div>
    </div>

    <!-- DB Metrics -->
    <div class="glass-card rounded-2xl p-6">
      <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4 uppercase tracking-wider">
        Database Metrics (Backend)
      </h3>
      <div class="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div
          v-for="m in dbMetricsList"
          :key="m.label"
          class="text-center p-3 bg-slate-50 dark:bg-white/5 rounded-xl"
        >
          <div class="text-xl font-bold font-display text-slate-800 dark:text-slate-100">
            {{ m.value }}
          </div>
          <div class="text-[11px] text-slate-500 mt-0.5">{{ m.label }}</div>
        </div>
      </div>
    </div>

    <!-- OCR Correction Cache -->
    <div class="glass-card rounded-2xl p-6">
      <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4 uppercase tracking-wider">
        OCR Correction Cache
      </h3>
      <div class="mb-4">
        <span class="text-2xl font-bold font-display text-accent-violet">
          {{ metrics?.ai?.correction_cache?.learned_count ?? 0 }}
        </span>
        <span class="text-sm text-slate-500 ml-2">learned corrections</span>
      </div>
      <div v-if="topCorrections.length > 0">
        <p class="text-xs text-slate-500 uppercase tracking-wider mb-2">Top Corrections</p>
        <div class="space-y-2">
          <div
            v-for="c in topCorrections"
            :key="c.ocr"
            class="flex items-center space-x-3 text-sm"
          >
            <span class="font-mono text-accent-rose bg-accent-rose/10 px-2 py-0.5 rounded">{{ c.ocr }}</span>
            <span class="text-slate-400">→</span>
            <span class="font-mono text-accent-emerald bg-accent-emerald/10 px-2 py-0.5 rounded">{{ c.confirmed }}</span>
            <span class="text-xs text-slate-400 ml-auto">× {{ c.count }}</span>
          </div>
        </div>
      </div>
      <p v-else class="text-sm text-slate-400 italic">No corrections learned yet.</p>
    </div>

    <!-- Last updated -->
    <p class="text-xs text-slate-400 text-right">
      Last updated: {{ lastUpdated || '—' }}
    </p>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const config  = useRuntimeConfig()
const apiBase = config.public.apiBase || '/api'

const metrics     = ref(null)
const error       = ref(null)
const lastUpdated = ref(null)
let   interval    = null

async function fetchMetrics() {
  try {
    const data = await $fetch(`${apiBase}/plate/metrics`)
    metrics.value     = data?.data ?? data
    lastUpdated.value = new Date().toLocaleTimeString('th-TH')
    error.value       = null
  } catch (e) {
    error.value = `Failed to load metrics: ${e?.message ?? e}`
  }
}

// Pipeline stage definitions
const pipelineStages = [
  { key: 'vehicle_seen',        label: 'Vehicles Seen',      color: 'text-slate-700 dark:text-slate-100' },
  { key: 'best_frame_selected', label: 'Best Frame',         color: 'text-accent-cyan' },
  { key: 'plate_detected',      label: 'Plate Detected',     color: 'text-accent-violet' },
  { key: 'ocr_success',         label: 'OCR Success',        color: 'text-accent-emerald' },
  { key: 'backend_saved',       label: 'Saved to DB',        color: 'text-brand-500' },
]

const rejections = [
  { key: 'rejected_blur',        label: 'Blur Rejected',       color: 'text-accent-amber',  bg: 'bg-accent-amber/10',  icon: '〰️' },
  { key: 'rejected_reflection',  label: 'Reflection Rejected', color: 'text-accent-rose',   bg: 'bg-accent-rose/10',   icon: '💡' },
  { key: 'rejected_plate_size',  label: 'Plate Too Small',     color: 'text-slate-500',     bg: 'bg-slate-100 dark:bg-white/5',  icon: '🔍' },
  { key: 'duplicate_suppressed', label: 'Duplicate Suppressed',color: 'text-slate-400',     bg: 'bg-slate-100 dark:bg-white/5',  icon: '🔁' },
]

function aiCounter(key) {
  return metrics.value?.ai?.pipeline?.[key] ?? '—'
}

const yieldPct = computed(() => {
  const y = metrics.value?.ai?.pipeline?.yield_rate
  return y != null ? Math.round(y * 100) : 0
})

const ocrPct = computed(() => {
  const r = metrics.value?.ai?.pipeline?.ocr_success_rate
  return r != null ? Math.round(r * 100) : 0
})

const topCorrections = computed(() => {
  return metrics.value?.ai?.correction_cache?.top_corrections ?? []
})

const dbMetricsList = computed(() => {
  const db = metrics.value?.db ?? {}
  return [
    { label: 'All-time Logs',     value: db.total_all_time  ?? '—' },
    { label: 'Today Logs',        value: db.total_today     ?? '—' },
    { label: 'Avg Proc (ms)',     value: db.avg_proc_ms     ?? '—' },
    { label: 'Avg Quality',       value: db.avg_quality     ?? '—' },
    { label: 'Avg Confidence',    value: db.avg_confidence  ?? '—' },
  ]
})

onMounted(() => {
  fetchMetrics()
  interval = setInterval(fetchMetrics, 5000)
})

onUnmounted(() => clearInterval(interval))
</script>
