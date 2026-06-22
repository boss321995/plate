<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-display font-bold text-slate-900 dark:text-white">Fleet Manager</h2>
        <p class="text-sm text-slate-500 mt-0.5">All registered edge devices — auto-refresh every 30s</p>
      </div>
      <button @click="refresh" class="glass-card px-4 py-2 rounded-xl text-sm font-medium text-accent-cyan hover:bg-accent-cyan/10 transition-colors">
        Refresh
      </button>
    </div>

    <!-- Summary cards -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div v-for="card in summaryCards" :key="card.label" class="glass-card rounded-2xl p-5 text-center">
        <div class="text-3xl font-bold font-display" :class="card.color">{{ card.value }}</div>
        <div class="text-xs text-slate-500 mt-1">{{ card.label }}</div>
      </div>
    </div>

    <!-- Device table -->
    <div class="glass-card rounded-2xl overflow-hidden">
      <div class="px-6 py-4 border-b border-slate-200 dark:border-white/[0.06] flex items-center justify-between">
        <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider">Devices</h3>
        <span class="text-xs text-slate-400">{{ devices.length }} registered</span>
      </div>
      <div v-if="devices.length === 0" class="p-8 text-center text-sm text-slate-400 italic">No devices registered.</div>
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-200 dark:border-white/[0.06]">
              <th class="text-left px-6 py-3">Device</th>
              <th class="text-left px-4 py-3">Site</th>
              <th class="text-left px-4 py-3">Version</th>
              <th class="text-right px-4 py-3">CPU</th>
              <th class="text-right px-4 py-3">MEM</th>
              <th class="text-right px-4 py-3">Disk</th>
              <th class="text-right px-4 py-3">FPS</th>
              <th class="text-right px-4 py-3">Cameras</th>
              <th class="text-center px-4 py-3">Status</th>
              <th class="text-right px-4 py-3">Last Seen</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-white/[0.04]">
            <tr v-for="d in devices" :key="d.device_id"
                class="hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
              <td class="px-6 py-3 font-medium text-slate-800 dark:text-slate-200">
                <div>{{ d.hostname || d.device_id }}</div>
                <div class="text-[10px] text-slate-400">{{ d.device_id }}</div>
              </td>
              <td class="px-4 py-3 text-slate-600 dark:text-slate-400">{{ d.site_id || '—' }}</td>
              <td class="px-4 py-3 text-slate-500 font-mono text-xs">{{ d.software_version || '—' }}</td>
              <td class="px-4 py-3 text-right" :class="pctColor(d.cpu, 70, 85)">{{ d.cpu != null ? d.cpu + '%' : '—' }}</td>
              <td class="px-4 py-3 text-right" :class="pctColor(d.memory, 75, 90)">{{ d.memory != null ? d.memory + '%' : '—' }}</td>
              <td class="px-4 py-3 text-right" :class="pctColor(d.disk, 80, 90)">{{ d.disk != null ? d.disk + '%' : '—' }}</td>
              <td class="px-4 py-3 text-right text-slate-600 dark:text-slate-300">{{ d.fps != null ? d.fps : '—' }}</td>
              <td class="px-4 py-3 text-right text-slate-600 dark:text-slate-300">{{ d.camera_count ?? '—' }}</td>
              <td class="px-4 py-3 text-center">
                <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase"
                      :class="statusClass(d.status)">{{ d.status }}</span>
              </td>
              <td class="px-4 py-3 text-right text-xs text-slate-400">{{ ageLabel(d.age_sec) }}</td>
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

const devices     = ref([])
const stats       = ref({})
const lastUpdated = ref(null)
let   timer       = null

const summaryCards = computed(() => [
  { label: 'Total Devices', value: stats.value.total   ?? 0, color: 'text-slate-700 dark:text-slate-100' },
  { label: 'Online',        value: stats.value.online  ?? 0, color: 'text-accent-emerald' },
  { label: 'Warning',       value: stats.value.warning ?? 0, color: 'text-accent-amber' },
  { label: 'Offline',       value: stats.value.offline ?? 0, color: 'text-accent-rose' },
])

function pctColor(v, warn, crit) {
  if (v == null) return 'text-slate-400'
  if (v >= crit) return 'text-accent-rose font-semibold'
  if (v >= warn) return 'text-accent-amber'
  return 'text-slate-600 dark:text-slate-300'
}

function statusClass(s) {
  if (s === 'ONLINE')  return 'bg-accent-emerald/10 text-accent-emerald'
  if (s === 'WARNING') return 'bg-accent-amber/10 text-accent-amber'
  return 'bg-accent-rose/10 text-accent-rose'
}

function ageLabel(sec) {
  if (sec == null) return '—'
  if (sec < 60)   return `${Math.floor(sec)}s ago`
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`
  return `${Math.floor(sec / 3600)}h ago`
}

async function refresh() {
  try {
    const data = await $fetch(`${apiBase}/fleet`).catch(() => null)
    if (data?.success) {
      devices.value     = data.data?.devices ?? []
      stats.value       = data.data?.stats   ?? {}
      lastUpdated.value = new Date().toLocaleTimeString('th-TH')
    }
  } catch (e) {
    console.error('[Fleet]', e)
  }
}

onMounted(() => { refresh(); timer = setInterval(refresh, 30_000) })
onUnmounted(() => clearInterval(timer))
</script>
