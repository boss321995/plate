<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-display font-bold text-slate-900 dark:text-white">Backup Center</h2>
        <p class="text-sm text-slate-500 mt-0.5">Daily automated backups — 7-day retention</p>
      </div>
      <button @click="triggerBackup" :disabled="triggering"
              class="glass-card px-4 py-2 rounded-xl text-sm font-medium text-accent-cyan hover:bg-accent-cyan/10 transition-colors disabled:opacity-50">
        {{ triggering ? 'Backing up…' : 'Backup Now' }}
      </button>
    </div>

    <!-- Last backup banner -->
    <div v-if="backups.length" class="glass-card rounded-2xl p-5 border border-accent-emerald/20 bg-accent-emerald/[0.03] flex items-center space-x-4">
      <svg class="w-6 h-6 text-accent-emerald shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
      </svg>
      <div>
        <p class="text-sm font-semibold text-slate-800 dark:text-white">Last backup: {{ backups[0].name }}</p>
        <p class="text-xs text-slate-500">{{ backups[0].size_mb }} MB · {{ formatDate(backups[0].created_at) }}</p>
      </div>
    </div>

    <!-- What's backed up -->
    <div class="glass-card rounded-2xl p-6">
      <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-4">Backup Contents</h3>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div v-for="item in contents" :key="item.label" class="bg-slate-50 dark:bg-white/5 rounded-xl p-3 flex items-center space-x-3">
          <span class="text-xl">{{ item.icon }}</span>
          <div>
            <div class="text-xs font-semibold text-slate-700 dark:text-slate-300">{{ item.label }}</div>
            <div class="text-[10px] text-slate-400">{{ item.desc }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Backup list -->
    <div class="glass-card rounded-2xl overflow-hidden">
      <div class="px-6 py-4 border-b border-slate-200 dark:border-white/[0.06]">
        <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider">
          Backup Archive
          <span class="ml-2 text-slate-400 font-normal normal-case">({{ backups.length }} backups)</span>
        </h3>
      </div>
      <div v-if="backups.length === 0" class="p-8 text-center text-sm text-slate-400 italic">No backups yet. Click "Backup Now" to create one.</div>
      <div v-else class="divide-y divide-slate-100 dark:divide-white/[0.04]">
        <div v-for="b in backups" :key="b.name"
             class="flex items-center px-6 py-3 hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
          <div class="flex-1 min-w-0">
            <p class="text-sm font-medium text-slate-800 dark:text-slate-200 font-mono">{{ b.name }}</p>
            <p class="text-xs text-slate-400 mt-0.5">{{ b.size_mb }} MB · {{ formatDate(b.created_at) }}</p>
          </div>
          <div class="flex items-center space-x-2 shrink-0">
            <div class="flex items-center">
              <div class="h-1.5 w-16 bg-slate-200 dark:bg-white/10 rounded-full overflow-hidden">
                <div class="h-full bg-accent-cyan/60 rounded-full" :style="{ width: sizePct(b.size_mb) }"></div>
              </div>
              <span class="ml-2 text-xs text-slate-400">{{ b.size_mb }} MB</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Schedule info -->
    <div class="glass-card rounded-2xl p-5">
      <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-3">Schedule &amp; Retention Policy</h3>
      <div class="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
        <div>
          <div class="text-xs text-slate-400">Schedule</div>
          <div class="font-semibold text-slate-700 dark:text-slate-200">Daily at 02:00</div>
        </div>
        <div>
          <div class="text-xs text-slate-400">Retention</div>
          <div class="font-semibold text-slate-700 dark:text-slate-200">7 days</div>
        </div>
        <div>
          <div class="text-xs text-slate-400">Storage</div>
          <div class="font-semibold text-slate-700 dark:text-slate-200">backups/daily/</div>
        </div>
      </div>
    </div>

    <p class="text-xs text-slate-400 text-right">Last refreshed: {{ lastUpdated || '—' }}</p>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const config  = useRuntimeConfig()
const AI_URL  = config.public.aiBase || 'http://localhost:8000'

const backups    = ref([])
const triggering = ref(false)
const lastUpdated = ref(null)

const contents = [
  { icon: '🗄️', label: 'Database',     desc: 'database.sqlite' },
  { icon: '⚙️', label: 'Config',        desc: 'config_store.json' },
  { icon: '🧩', label: 'Profiles',      desc: 'profiles/*.json' },
  { icon: '📁', label: 'Logs (7d)',      desc: 'backend/logs/' },
]

const maxSize = computed(() => Math.max(...backups.value.map(b => b.size_mb), 1))
function sizePct(mb) { return Math.round(mb / maxSize.value * 100) + '%' }

function formatDate(ts) {
  if (!ts) return '—'
  const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts)
  return d.toLocaleString('th-TH', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function loadBackups() {
  try {
    const data = await $fetch(`${AI_URL}/backup/list`).catch(() => null)
    backups.value     = data?.backups ?? []
    lastUpdated.value = new Date().toLocaleTimeString('th-TH')
  } catch {}
}

async function triggerBackup() {
  triggering.value = true
  try {
    await $fetch(`${AI_URL}/backup/now`, { method: 'POST' })
    await loadBackups()
  } catch {} finally { triggering.value = false }
}

onMounted(loadBackups)
</script>
