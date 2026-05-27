<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-display font-bold text-slate-900 dark:text-white">Active Parking</h1>
        <p class="text-slate-500 text-sm mt-0.5">Real-time dwell time monitoring for vehicles currently inside.</p>
      </div>
      <div class="flex space-x-3">
        <div class="glass-card px-4 py-2 rounded-xl flex items-center">
          <span class="w-2 h-2 rounded-full bg-accent-amber mr-2 animate-pulse"></span>
          <span class="text-sm font-semibold text-slate-700 dark:text-slate-200">Overstaying: <span class="text-accent-rose">{{ overstayCount }}</span></span>
        </div>
        <div class="glass-card px-4 py-2 rounded-xl flex items-center">
          <span class="w-2 h-2 rounded-full bg-accent-cyan mr-2"></span>
          <span class="text-sm font-semibold text-slate-700 dark:text-slate-200">Total Active: <span class="text-accent-cyan">{{ activeVehicles.length }}</span></span>
        </div>
      </div>
    </div>

    <!-- Active Vehicles Table -->
    <div class="glass-card rounded-2xl overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead class="border-b border-slate-200 dark:border-white/[0.06]">
            <tr>
              <th class="px-6 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Plate Number</th>
              <th class="px-6 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Type</th>
              <th class="px-6 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Entry Time</th>
              <th class="px-6 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Dwell Time</th>
              <th class="px-6 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Status</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-200 dark:divide-white/[0.04]">
            <tr v-if="loading">
              <td colspan="5" class="px-6 py-12 text-center text-slate-500">
                <svg class="animate-spin w-5 h-5 mx-auto mb-2 text-accent-cyan" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                Loading active vehicles...
              </td>
            </tr>
            <tr v-else-if="activeVehicles.length === 0">
              <td colspan="5" class="px-6 py-12 text-center text-slate-500">No vehicles are currently inside.</td>
            </tr>
            <tr v-else v-for="vehicle in activeVehicles" :key="vehicle.id" 
                :class="vehicle.is_overstay ? 'bg-rose-50/50 hover:bg-rose-100/50 dark:bg-rose-500/5 dark:hover:bg-rose-500/10' : 'hover:bg-slate-100/50 dark:hover:bg-white/[0.03]'" 
                class="transition-colors group">
              <td class="px-6 py-3.5">
                <div class="font-mono font-bold text-slate-800 dark:text-white inline-block bg-slate-200/50 dark:bg-white/5 px-3 py-1 rounded-lg border border-slate-300 dark:border-white/10 text-sm">
                  {{ vehicle.plate }}
                </div>
              </td>
              <td class="px-6 py-3.5">
                <span :class="typeColor(vehicle.role)" class="text-[10px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wider">{{ vehicle.role }}</span>
              </td>
              <td class="px-6 py-3.5 text-slate-600 dark:text-slate-400">
                {{ formatDate(vehicle.entry_time) }}
              </td>
              <td class="px-6 py-3.5">
                <div class="flex items-center space-x-2">
                  <svg class="w-4 h-4" :class="vehicle.is_overstay ? 'text-accent-rose' : 'text-slate-400'" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                  <span class="font-mono text-sm" :class="vehicle.is_overstay ? 'text-accent-rose font-bold' : 'text-slate-700 dark:text-slate-300'">{{ vehicle.duration_formatted }}</span>
                </div>
              </td>
              <td class="px-6 py-3.5 text-right">
                <span v-if="vehicle.is_overstay" class="inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold bg-accent-rose text-white shadow-glow-rose tracking-wide animate-pulse">
                  OVERSTAY
                </span>
                <span v-else class="inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold bg-accent-emerald/20 text-emerald-600 dark:text-emerald-400 tracking-wide">
                  OK
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, onUnmounted } from 'vue'

definePageMeta({
  middleware: 'auth'
})

const activeVehicles = ref([])
const loading = ref(true)
let refreshInterval = null

const overstayCount = computed(() => {
  return activeVehicles.value.filter(v => v.is_overstay).length
})

const fetchActiveVehicles = async () => {
  try {
    const res = await fetch('http://localhost:3001/api/parking/active')
    const data = await res.json()
    if (data.success) {
      activeVehicles.value = data.data
    }
  } catch (err) {
    console.error('Failed to fetch active vehicles', err)
  } finally {
    loading.value = false
  }
}

const typeColor = (type) => {
  if (type === 'BLACKLIST') return 'bg-accent-rose/15 text-rose-600 dark:text-rose-400'
  if (type === 'STAFF') return 'bg-accent-emerald/15 text-emerald-600 dark:text-emerald-400'
  if (type === 'INTERNAL') return 'bg-brand-500/15 text-blue-600 dark:text-blue-400'
  return 'bg-accent-amber/15 text-amber-600 dark:text-amber-400'
}

const formatDate = (dateString) => {
  const date = new Date(dateString)
  const options = { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }
  return date.toLocaleDateString('en-GB', options)
}

onMounted(() => {
  fetchActiveVehicles()
  // Refresh data every 60 seconds to update duration
  refreshInterval = setInterval(fetchActiveVehicles, 60000)
})

onUnmounted(() => {
  if (refreshInterval) clearInterval(refreshInterval)
})
</script>
