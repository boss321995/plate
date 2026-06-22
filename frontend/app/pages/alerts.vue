<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-display font-bold text-slate-900 dark:text-white">Enterprise Alert Center</h2>
        <p class="text-sm text-slate-500 mt-0.5">Live alerts from all AI and system components</p>
      </div>
      <div class="flex items-center space-x-2">
        <select v-model="levelFilter" class="glass-card rounded-xl px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none">
          <option value="">All Levels</option>
          <option value="CRITICAL">CRITICAL</option>
          <option value="WARNING">WARNING</option>
          <option value="INFO">INFO</option>
        </select>
        <button @click="refresh" class="glass-card px-4 py-2 rounded-xl text-sm font-medium text-accent-cyan hover:bg-accent-cyan/10 transition-colors">
          Refresh
        </button>
      </div>
    </div>

    <!-- Count cards -->
    <div class="grid grid-cols-3 gap-4">
      <div class="glass-card rounded-2xl p-5 text-center">
        <div class="text-3xl font-bold font-display text-accent-rose">{{ counts.CRITICAL ?? 0 }}</div>
        <div class="text-xs text-slate-500 mt-1">Critical</div>
      </div>
      <div class="glass-card rounded-2xl p-5 text-center">
        <div class="text-3xl font-bold font-display text-accent-amber">{{ counts.WARNING ?? 0 }}</div>
        <div class="text-xs text-slate-500 mt-1">Warning</div>
      </div>
      <div class="glass-card rounded-2xl p-5 text-center">
        <div class="text-3xl font-bold font-display text-slate-600 dark:text-slate-300">{{ counts.INFO ?? 0 }}</div>
        <div class="text-xs text-slate-500 mt-1">Info</div>
      </div>
    </div>

    <!-- Alert feed -->
    <div class="glass-card rounded-2xl overflow-hidden">
      <div class="px-6 py-4 border-b border-slate-200 dark:border-white/[0.06]">
        <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider">
          {{ levelFilter ? levelFilter : 'All Alerts' }}
          <span class="ml-2 text-slate-400 font-normal normal-case">— {{ filteredAlerts.length }} shown</span>
        </h3>
      </div>
      <div v-if="filteredAlerts.length === 0" class="p-8 text-center text-sm text-slate-400 italic">No alerts matching filter.</div>
      <div v-else class="divide-y divide-slate-100 dark:divide-white/[0.04] max-h-[60vh] overflow-y-auto">
        <div v-for="a in filteredAlerts" :key="a.ts"
             class="flex items-start space-x-4 px-6 py-3 hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors"
             :class="rowBg(a.level)">
          <div class="shrink-0 mt-0.5">
            <span class="w-2 h-2 rounded-full block mt-1" :class="dotColor(a.level)"></span>
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center space-x-2">
              <span class="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full" :class="badgeClass(a.level)">{{ a.level }}</span>
              <span class="text-xs font-semibold text-slate-700 dark:text-slate-300">{{ a.source }}</span>
              <span class="text-[10px] text-slate-400 ml-auto shrink-0">{{ tsLabel(a.ts) }}</span>
            </div>
            <p class="text-sm text-slate-600 dark:text-slate-400 mt-1">{{ a.message }}</p>
            <pre v-if="a.data && Object.keys(a.data).length"
                 class="text-[10px] text-slate-400 mt-1 font-mono bg-slate-50 dark:bg-white/5 rounded px-2 py-1 overflow-x-auto">{{ JSON.stringify(a.data, null, 2) }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- Audit log -->
    <div class="glass-card rounded-2xl overflow-hidden">
      <div class="px-6 py-4 border-b border-slate-200 dark:border-white/[0.06]">
        <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider">Audit Log</h3>
      </div>
      <div v-if="auditRows.length === 0" class="p-6 text-center text-sm text-slate-400 italic">No audit entries.</div>
      <div v-else class="overflow-x-auto max-h-72">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-200 dark:border-white/[0.06]">
              <th class="text-left px-6 py-2">Time</th>
              <th class="text-left px-4 py-2">Severity</th>
              <th class="text-left px-4 py-2">Event</th>
              <th class="text-left px-4 py-2">Source</th>
              <th class="text-left px-4 py-2">Action</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-white/[0.04]">
            <tr v-for="row in auditRows" :key="row.id" class="hover:bg-slate-50 dark:hover:bg-white/[0.02]">
              <td class="px-6 py-2 text-xs text-slate-400">{{ formatDate(row.created_at) }}</td>
              <td class="px-4 py-2">
                <span class="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full" :class="badgeClass(row.severity)">{{ row.severity }}</span>
              </td>
              <td class="px-4 py-2 text-slate-700 dark:text-slate-300">{{ row.event }}</td>
              <td class="px-4 py-2 text-xs text-slate-500">{{ row.source || '—' }}</td>
              <td class="px-4 py-2 text-xs text-slate-500 truncate max-w-xs">{{ row.action || '—' }}</td>
            </tr>
          </tbody>
        </table>
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

const alerts      = ref([])
const counts      = ref({})
const auditRows   = ref([])
const lastUpdated = ref(null)
const levelFilter = ref('')
let   timer       = null

const filteredAlerts = computed(() =>
  levelFilter.value ? alerts.value.filter(a => a.level === levelFilter.value) : alerts.value
)

function rowBg(level) {
  if (level === 'CRITICAL') return 'bg-accent-rose/[0.03]'
  if (level === 'WARNING')  return 'bg-accent-amber/[0.03]'
  return ''
}
function dotColor(level) {
  if (level === 'CRITICAL') return 'bg-accent-rose'
  if (level === 'WARNING')  return 'bg-accent-amber'
  return 'bg-slate-400'
}
function badgeClass(level) {
  if (level === 'CRITICAL') return 'bg-accent-rose/10 text-accent-rose'
  if (level === 'WARNING')  return 'bg-accent-amber/10 text-accent-amber'
  return 'bg-slate-100 dark:bg-white/10 text-slate-500'
}
function tsLabel(ts) {
  return new Date(ts * 1000).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
function formatDate(dt) {
  if (!dt) return '—'
  return new Date(dt).toLocaleString('th-TH', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function refresh() {
  try {
    const [alertData, auditData] = await Promise.all([
      $fetch(`${AI_URL}/alerts?n=100${levelFilter.value ? '&level=' + levelFilter.value : ''}`).catch(() => null),
      $fetch(`${apiBase}/diagnostics/audit?limit=30`).catch(() => null),
    ])
    if (alertData) {
      alerts.value = alertData.alerts ?? []
      counts.value = alertData.counts ?? {}
    }
    auditRows.value   = auditData?.data ?? []
    lastUpdated.value = new Date().toLocaleTimeString('th-TH')
  } catch (e) {
    console.error('[Alerts]', e)
  }
}

onMounted(() => { refresh(); timer = setInterval(refresh, 15_000) })
onUnmounted(() => clearInterval(timer))
</script>
