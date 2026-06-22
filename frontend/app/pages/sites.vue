<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-display font-bold text-slate-900 dark:text-white">Site Manager</h2>
        <p class="text-sm text-slate-500 mt-0.5">Manage physical deployment sites</p>
      </div>
      <button @click="openCreate" class="glass-card px-4 py-2 rounded-xl text-sm font-medium text-accent-cyan hover:bg-accent-cyan/10 transition-colors">
        + New Site
      </button>
    </div>

    <!-- Sites grid -->
    <div v-if="sites.length === 0" class="glass-card rounded-2xl p-8 text-center text-sm text-slate-400 italic">
      No sites configured. Create the first one.
    </div>
    <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <div v-for="s in sites" :key="s.id" class="glass-card rounded-2xl p-5 space-y-3">
        <div class="flex items-start justify-between">
          <div>
            <h3 class="font-semibold text-slate-800 dark:text-white">{{ s.site_name }}</h3>
            <p class="text-xs text-slate-400 mt-0.5">{{ s.address || 'No address' }}</p>
          </div>
          <span class="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase"
                :class="s.status === 'active' ? 'bg-accent-emerald/10 text-accent-emerald' : 'bg-slate-200 dark:bg-white/10 text-slate-500'">
            {{ s.status }}
          </span>
        </div>
        <div class="grid grid-cols-2 gap-2 text-xs">
          <div class="bg-slate-50 dark:bg-white/5 rounded-lg px-3 py-2">
            <div class="text-slate-400">Devices</div>
            <div class="font-bold text-slate-700 dark:text-slate-200 text-lg">{{ s.device_count ?? 0 }}</div>
          </div>
          <div class="bg-slate-50 dark:bg-white/5 rounded-lg px-3 py-2">
            <div class="text-slate-400">Timezone</div>
            <div class="font-medium text-slate-600 dark:text-slate-300 truncate">{{ s.timezone }}</div>
          </div>
        </div>
        <div v-if="s.latitude || s.longitude" class="text-[10px] text-slate-400 font-mono">
          {{ s.latitude?.toFixed(4) }}, {{ s.longitude?.toFixed(4) }}
        </div>
        <div class="flex space-x-2 pt-1">
          <button @click="openEdit(s)"
                  class="flex-1 py-1.5 rounded-lg text-xs font-medium bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-white/10 transition-colors">
            Edit
          </button>
          <button @click="deleteSite(s.id)"
                  class="flex-1 py-1.5 rounded-lg text-xs font-medium bg-accent-rose/10 text-accent-rose hover:bg-accent-rose/20 transition-colors">
            Delete
          </button>
        </div>
      </div>
    </div>

    <!-- Create / Edit modal -->
    <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="closeModal"></div>
      <div class="relative glass-card rounded-2xl p-6 w-full max-w-md shadow-2xl space-y-4">
        <h3 class="text-lg font-display font-bold text-slate-800 dark:text-white">
          {{ editingId ? 'Edit Site' : 'Create Site' }}
        </h3>
        <div class="space-y-3">
          <div>
            <label class="block text-xs font-medium text-slate-500 mb-1">Site Name *</label>
            <input v-model="form.site_name" type="text" placeholder="Headquarters"
                   class="w-full glass-card rounded-xl px-3 py-2 text-sm text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-accent-cyan/30" />
          </div>
          <div>
            <label class="block text-xs font-medium text-slate-500 mb-1">Address</label>
            <input v-model="form.address" type="text" placeholder="123 Main St, Bangkok"
                   class="w-full glass-card rounded-xl px-3 py-2 text-sm text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-accent-cyan/30" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-medium text-slate-500 mb-1">Latitude</label>
              <input v-model="form.latitude" type="number" step="0.0001" placeholder="13.7563"
                     class="w-full glass-card rounded-xl px-3 py-2 text-sm text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-accent-cyan/30" />
            </div>
            <div>
              <label class="block text-xs font-medium text-slate-500 mb-1">Longitude</label>
              <input v-model="form.longitude" type="number" step="0.0001" placeholder="100.5018"
                     class="w-full glass-card rounded-xl px-3 py-2 text-sm text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-accent-cyan/30" />
            </div>
          </div>
          <div>
            <label class="block text-xs font-medium text-slate-500 mb-1">Timezone</label>
            <input v-model="form.timezone" type="text" placeholder="Asia/Bangkok"
                   class="w-full glass-card rounded-xl px-3 py-2 text-sm text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-accent-cyan/30" />
          </div>
        </div>
        <div v-if="formError" class="text-xs text-accent-rose">{{ formError }}</div>
        <div class="flex space-x-3 pt-2">
          <button @click="closeModal" class="flex-1 py-2 rounded-xl text-sm font-medium bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-white/10 transition-colors">Cancel</button>
          <button @click="saveForm" :disabled="saving"
                  class="flex-1 py-2 rounded-xl text-sm font-medium bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20 transition-colors disabled:opacity-50">
            {{ saving ? 'Saving…' : 'Save' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const config  = useRuntimeConfig()
const apiBase = config.public.apiBase || '/api'

const sites     = ref([])
const showModal = ref(false)
const editingId = ref(null)
const saving    = ref(false)
const formError = ref('')
const form      = ref({ site_name: '', address: '', latitude: '', longitude: '', timezone: 'Asia/Bangkok' })

async function loadSites() {
  try {
    const data = await $fetch(`${apiBase}/sites`).catch(() => null)
    sites.value = data?.data ?? []
  } catch {}
}

function openCreate() {
  editingId.value = null
  form.value      = { site_name: '', address: '', latitude: '', longitude: '', timezone: 'Asia/Bangkok' }
  formError.value = ''
  showModal.value = true
}

function openEdit(s) {
  editingId.value = s.id
  form.value      = { site_name: s.site_name, address: s.address || '', latitude: s.latitude || '', longitude: s.longitude || '', timezone: s.timezone || 'Asia/Bangkok' }
  formError.value = ''
  showModal.value = true
}

function closeModal() { showModal.value = false }

async function saveForm() {
  if (!form.value.site_name.trim()) { formError.value = 'Site name is required'; return }
  saving.value = true
  try {
    if (editingId.value) {
      await $fetch(`${apiBase}/sites/${editingId.value}`, { method: 'PUT', body: form.value })
    } else {
      await $fetch(`${apiBase}/sites`, { method: 'POST', body: form.value })
    }
    closeModal()
    await loadSites()
  } catch (e) {
    formError.value = 'Save failed — check console'
  } finally {
    saving.value = false
  }
}

async function deleteSite(id) {
  if (!confirm('Delete this site? Devices will be unlinked.')) return
  try {
    await $fetch(`${apiBase}/sites/${id}`, { method: 'DELETE' })
    await loadSites()
  } catch {}
}

onMounted(loadSites)
</script>
