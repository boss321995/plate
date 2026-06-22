<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-display font-bold text-slate-900 dark:text-white">Device Inventory</h2>
        <p class="text-sm text-slate-500 mt-0.5">Physical edge device registry</p>
      </div>
      <div class="flex space-x-2">
        <select v-model="filterSite" class="glass-card rounded-xl px-3 py-2 text-sm text-slate-700 dark:text-slate-300 outline-none">
          <option value="">All Sites</option>
          <option v-for="s in sites" :key="s.id" :value="s.id">{{ s.site_name }}</option>
        </select>
        <button @click="refresh" class="glass-card px-4 py-2 rounded-xl text-sm font-medium text-accent-cyan hover:bg-accent-cyan/10 transition-colors">
          Refresh
        </button>
      </div>
    </div>

    <!-- Table -->
    <div class="glass-card rounded-2xl overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-200 dark:border-white/[0.06]">
              <th class="text-left px-6 py-3">Device ID</th>
              <th class="text-left px-4 py-3">Hostname</th>
              <th class="text-left px-4 py-3">Serial</th>
              <th class="text-left px-4 py-3">Site</th>
              <th class="text-left px-4 py-3">IP Address</th>
              <th class="text-left px-4 py-3">MAC</th>
              <th class="text-left px-4 py-3">OS</th>
              <th class="text-right px-4 py-3">RAM</th>
              <th class="text-right px-4 py-3">Disk</th>
              <th class="text-left px-4 py-3">Version</th>
              <th class="text-center px-4 py-3">Status</th>
              <th class="text-right px-4 py-3">Last Seen</th>
            </tr>
          </thead>
          <tbody v-if="filteredDevices.length > 0" class="divide-y divide-slate-100 dark:divide-white/[0.04]">
            <tr v-for="d in filteredDevices" :key="d.id"
                class="hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
              <td class="px-6 py-3 font-mono text-xs text-accent-cyan">{{ d.device_id }}</td>
              <td class="px-4 py-3 font-medium text-slate-800 dark:text-slate-200">{{ d.hostname || '—' }}</td>
              <td class="px-4 py-3 font-mono text-xs text-slate-500">{{ d.serial || '—' }}</td>
              <td class="px-4 py-3 text-slate-600 dark:text-slate-400">{{ siteName(d.site_id) }}</td>
              <td class="px-4 py-3 font-mono text-xs text-slate-500">{{ d.ip_address || '—' }}</td>
              <td class="px-4 py-3 font-mono text-xs text-slate-400">{{ d.mac_address || '—' }}</td>
              <td class="px-4 py-3 text-xs text-slate-500">{{ d.os_info || '—' }}</td>
              <td class="px-4 py-3 text-right text-slate-600 dark:text-slate-300">{{ d.ram_gb ? d.ram_gb + ' GB' : '—' }}</td>
              <td class="px-4 py-3 text-right text-slate-600 dark:text-slate-300">{{ d.disk_gb ? d.disk_gb + ' GB' : '—' }}</td>
              <td class="px-4 py-3 font-mono text-xs text-slate-500">{{ d.software_version || '—' }}</td>
              <td class="px-4 py-3 text-center">
                <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase"
                      :class="statusClass(d.status)">{{ d.status || 'UNKNOWN' }}</span>
              </td>
              <td class="px-4 py-3 text-right text-xs text-slate-400">{{ formatDate(d.last_seen) }}</td>
            </tr>
          </tbody>
          <tbody v-else>
            <tr><td colspan="12" class="py-10 text-center text-sm text-slate-400 italic">No devices in inventory.</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const config  = useRuntimeConfig()
const apiBase = config.public.apiBase || '/api'

const devices    = ref([])
const sites      = ref([])
const filterSite = ref('')

const filteredDevices = computed(() =>
  filterSite.value
    ? devices.value.filter(d => String(d.site_id) === String(filterSite.value))
    : devices.value
)

const siteMap = computed(() => {
  const m = {}
  sites.value.forEach(s => { m[s.id] = s.site_name })
  return m
})

function siteName(id) { return siteMap.value[id] || '—' }

function statusClass(s) {
  if (s === 'ONLINE')  return 'bg-accent-emerald/10 text-accent-emerald'
  if (s === 'WARNING') return 'bg-accent-amber/10 text-accent-amber'
  return 'bg-slate-200 dark:bg-white/10 text-slate-500'
}

function formatDate(dt) {
  if (!dt) return '—'
  return new Date(dt).toLocaleString('th-TH', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function refresh() {
  try {
    const [devData, siteData] = await Promise.all([
      $fetch(`${apiBase}/fleet`).catch(() => null),
      $fetch(`${apiBase}/sites`).catch(() => null),
    ])
    devices.value = devData?.data?.devices ?? []
    sites.value   = siteData?.data         ?? []
  } catch {}
}

onMounted(refresh)
</script>
