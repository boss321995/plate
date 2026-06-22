<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-display font-bold text-slate-900 dark:text-white">Model Registry</h2>
        <p class="text-sm text-slate-500 mt-0.5">AI model versioning, activation and rollback</p>
      </div>
      <button @click="showCreate = true" class="glass-card px-4 py-2 rounded-xl text-sm font-medium text-accent-cyan hover:bg-accent-cyan/10 transition-colors">
        + Register Model
      </button>
    </div>

    <!-- Active model banner -->
    <div v-if="activeModel" class="glass-card rounded-2xl p-5 border border-accent-emerald/20 bg-accent-emerald/[0.03]">
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-3">
          <span class="w-2.5 h-2.5 rounded-full bg-accent-emerald neon-dot animate-pulse"></span>
          <div>
            <p class="text-sm font-bold text-slate-800 dark:text-white">{{ activeModel.model_name }} v{{ activeModel.model_version }}</p>
            <p class="text-xs text-slate-500">{{ activeModel.model_type }} · Accuracy {{ activeModel.accuracy ? (activeModel.accuracy * 100).toFixed(1) + '%' : '—' }} · Deployed {{ formatDate(activeModel.deployed_at) }}</p>
          </div>
        </div>
        <span class="px-3 py-1 rounded-full text-xs font-bold bg-accent-emerald/10 text-accent-emerald uppercase">Active</span>
      </div>
    </div>

    <!-- Model table -->
    <div class="glass-card rounded-2xl overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-200 dark:border-white/[0.06]">
              <th class="text-left px-6 py-3">Model</th>
              <th class="text-left px-4 py-3">Version</th>
              <th class="text-left px-4 py-3">Type</th>
              <th class="text-right px-4 py-3">Accuracy</th>
              <th class="text-left px-4 py-3">Checksum</th>
              <th class="text-center px-4 py-3">Status</th>
              <th class="text-right px-4 py-3">Registered</th>
              <th class="text-center px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody v-if="models.length > 0" class="divide-y divide-slate-100 dark:divide-white/[0.04]">
            <tr v-for="m in models" :key="m.id"
                class="hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors"
                :class="m.is_active ? 'bg-accent-emerald/[0.02]' : ''">
              <td class="px-6 py-3 font-semibold text-slate-800 dark:text-slate-200">{{ m.model_name }}</td>
              <td class="px-4 py-3 font-mono text-xs text-accent-cyan">v{{ m.model_version }}</td>
              <td class="px-4 py-3 text-slate-500 capitalize">{{ m.model_type }}</td>
              <td class="px-4 py-3 text-right" :class="m.accuracy >= 0.95 ? 'text-accent-emerald' : m.accuracy >= 0.90 ? 'text-accent-amber' : 'text-accent-rose'">
                {{ m.accuracy ? (m.accuracy * 100).toFixed(1) + '%' : '—' }}
              </td>
              <td class="px-4 py-3 font-mono text-[10px] text-slate-400 max-w-[120px] truncate">{{ m.checksum ? m.checksum.slice(0, 12) + '…' : '—' }}</td>
              <td class="px-4 py-3 text-center">
                <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase"
                      :class="statusClass(m.status, m.is_active)">{{ m.is_active ? 'ACTIVE' : m.status }}</span>
              </td>
              <td class="px-4 py-3 text-right text-xs text-slate-400">{{ formatDate(m.created_at) }}</td>
              <td class="px-4 py-3 text-center">
                <div class="flex items-center justify-center space-x-2">
                  <button v-if="!m.is_active" @click="activate(m.id)"
                          class="px-2.5 py-1 rounded-lg text-[10px] font-bold bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20 transition-colors">
                    Activate
                  </button>
                  <button v-if="!m.is_active" @click="rollback(m.id)"
                          class="px-2.5 py-1 rounded-lg text-[10px] font-bold bg-slate-100 dark:bg-white/5 text-slate-500 hover:bg-slate-200 dark:hover:bg-white/10 transition-colors">
                    Rollback
                  </button>
                  <span v-if="m.is_active" class="text-[10px] text-slate-400 italic">Running</span>
                </div>
              </td>
            </tr>
          </tbody>
          <tbody v-else>
            <tr><td colspan="8" class="py-10 text-center text-sm text-slate-400 italic">No models registered.</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Register model modal -->
    <div v-if="showCreate" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="showCreate = false"></div>
      <div class="relative glass-card rounded-2xl p-6 w-full max-w-md shadow-2xl space-y-4">
        <h3 class="text-lg font-display font-bold text-slate-800 dark:text-white">Register Model Version</h3>
        <div class="space-y-3">
          <div>
            <label class="block text-xs font-medium text-slate-500 mb-1">Model Name *</label>
            <input v-model="newModel.model_name" type="text" placeholder="yolov8n-plate"
                   class="w-full glass-card rounded-xl px-3 py-2 text-sm text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-accent-cyan/30" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-medium text-slate-500 mb-1">Version *</label>
              <input v-model="newModel.model_version" type="text" placeholder="1.2.0"
                     class="w-full glass-card rounded-xl px-3 py-2 text-sm text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-accent-cyan/30" />
            </div>
            <div>
              <label class="block text-xs font-medium text-slate-500 mb-1">Type</label>
              <select v-model="newModel.model_type" class="w-full glass-card rounded-xl px-3 py-2 text-sm text-slate-800 dark:text-white outline-none">
                <option value="vehicle">vehicle</option>
                <option value="plate">plate</option>
                <option value="ocr">ocr</option>
              </select>
            </div>
          </div>
          <div>
            <label class="block text-xs font-medium text-slate-500 mb-1">Accuracy (0.0–1.0)</label>
            <input v-model="newModel.accuracy" type="number" step="0.001" min="0" max="1" placeholder="0.960"
                   class="w-full glass-card rounded-xl px-3 py-2 text-sm text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-accent-cyan/30" />
          </div>
          <div>
            <label class="block text-xs font-medium text-slate-500 mb-1">SHA-256 Checksum</label>
            <input v-model="newModel.checksum" type="text" placeholder="abc123…"
                   class="w-full glass-card rounded-xl px-3 py-2 text-sm text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-accent-cyan/30 font-mono" />
          </div>
          <div>
            <label class="block text-xs font-medium text-slate-500 mb-1">Notes</label>
            <textarea v-model="newModel.notes" rows="2" placeholder="Trained on Thai plates v3 dataset"
                      class="w-full glass-card rounded-xl px-3 py-2 text-sm text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-accent-cyan/30 resize-none"></textarea>
          </div>
        </div>
        <div class="flex space-x-3 pt-2">
          <button @click="showCreate = false" class="flex-1 py-2 rounded-xl text-sm font-medium bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-400">Cancel</button>
          <button @click="saveModel" :disabled="saving"
                  class="flex-1 py-2 rounded-xl text-sm font-medium bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20 transition-colors disabled:opacity-50">
            {{ saving ? 'Saving…' : 'Register' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const config  = useRuntimeConfig()
const apiBase = config.public.apiBase || '/api'

const models     = ref([])
const showCreate = ref(false)
const saving     = ref(false)
const newModel   = ref({ model_name: '', model_version: '', model_type: 'vehicle', accuracy: '', checksum: '', notes: '' })

const activeModel = computed(() => models.value.find(m => m.is_active))

function statusClass(status, isActive) {
  if (isActive)           return 'bg-accent-emerald/10 text-accent-emerald'
  if (status === 'staged') return 'bg-accent-amber/10 text-accent-amber'
  return 'bg-slate-100 dark:bg-white/10 text-slate-500'
}

function formatDate(dt) {
  if (!dt) return '—'
  return new Date(dt).toLocaleString('th-TH', { month: 'short', day: 'numeric', year: 'numeric' })
}

async function loadModels() {
  try {
    const data = await $fetch(`${apiBase}/sites/models`).catch(() => null)
    models.value = data?.data ?? []
  } catch {}
}

async function activate(id) {
  try {
    await $fetch(`${apiBase}/sites/models/${id}/activate`, { method: 'PUT' })
    await loadModels()
  } catch {}
}

async function rollback(id) {
  try {
    const data = await $fetch(`${apiBase}/sites/models/${id}/rollback`, { method: 'POST' })
    if (data?.success) await loadModels()
  } catch {}
}

async function saveModel() {
  if (!newModel.value.model_name || !newModel.value.model_version) return
  saving.value = true
  try {
    await $fetch(`${apiBase}/sites/models`, { method: 'POST', body: newModel.value })
    showCreate.value = false
    newModel.value   = { model_name: '', model_version: '', model_type: 'vehicle', accuracy: '', checksum: '', notes: '' }
    await loadModels()
  } catch {} finally { saving.value = false }
}

onMounted(loadModels)
</script>
