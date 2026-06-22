<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-display font-bold text-slate-900 dark:text-white">Camera Management</h1>
        <p class="text-slate-500 text-sm mt-0.5">Monitor and manage LPR cameras and gates.</p>
      </div>
      <button @click="openModal" class="btn-glow text-white px-5 py-2.5 rounded-xl font-semibold transition-all flex items-center text-sm">
        <svg class="w-4 h-4 mr-2 relative z-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
        <span class="relative z-10">Add Camera</span>
      </button>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="flex justify-center items-center py-20">
      <svg class="animate-spin w-8 h-8 text-accent-cyan" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
    </div>

    <!-- Cameras Grid -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div v-for="camera in cameras" :key="camera.id" class="glass-card rounded-2xl overflow-hidden flex flex-col group relative">
        <!-- Status Indicator -->
        <div class="absolute top-4 right-4 z-20 flex items-center bg-slate-900/80 backdrop-blur-md px-3 py-1.5 rounded-full border border-white/10 shadow-lg">
          <span :class="camera.status === 'Online' ? 'bg-accent-emerald text-accent-emerald' : 'bg-accent-rose text-accent-rose'" class="w-2 h-2 rounded-full mr-2 neon-dot animate-pulse"></span>
          <span class="text-xs font-bold text-white uppercase tracking-wider">{{ camera.status }}</span>
        </div>

        <!-- Video Placeholder -->
        <div class="h-48 relative bg-slate-800 flex items-center justify-center overflow-hidden border-b border-slate-200 dark:border-white/5">
          <!-- Real Video Feed -->
          <img v-if="camera.liveFeed || (camera.stream_url && camera.status === 'Online')" :src="camera.liveFeed || camera.stream_url" class="absolute inset-0 w-full h-full object-cover z-0" alt="Live Feed" @error="$event.target.style.display='none'" />
          
          <!-- Background Grid for Tech Feel -->
          <div v-if="!camera.liveFeed && !camera.stream_url" class="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAiIGhlaWdodD0iMjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMiIgY3k9IjIiIHI9IjIiIGZpbGw9InJnYmEoMjU1LDI1NSwyNTUsMC4wNSkiLz48L3N2Zz4=')] opacity-50"></div>
          
          <div v-if="!camera.liveFeed && !camera.stream_url && camera.status === 'Online'" class="relative z-10 flex flex-col items-center">
            <div class="w-16 h-16 rounded-full border-2 border-accent-cyan/30 flex items-center justify-center mb-2">
              <div class="w-12 h-12 rounded-full border border-accent-cyan/50 flex items-center justify-center animate-[spin_4s_linear_infinite]">
                <svg class="w-6 h-6 text-accent-cyan" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
              </div>
            </div>
            <span class="text-accent-cyan text-xs font-mono tracking-widest uppercase">Live Feed Active</span>
          </div>
          
          <div v-if="camera.status !== 'Online'" class="relative z-10 flex flex-col items-center opacity-50 bg-slate-900/80 w-full h-full justify-center absolute inset-0">
            <svg class="w-12 h-12 text-slate-500 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"></path></svg>
            <span class="text-slate-400 text-xs font-mono tracking-widest uppercase">Connection Lost</span>
          </div>

          <!-- Decorative Crosshairs -->
          <div class="absolute top-2 left-2 w-4 h-4 border-t border-l border-white/20"></div>
          <div class="absolute top-2 right-2 w-4 h-4 border-t border-r border-white/20"></div>
          <div class="absolute bottom-2 left-2 w-4 h-4 border-b border-l border-white/20"></div>
          <div class="absolute bottom-2 right-2 w-4 h-4 border-b border-r border-white/20"></div>
        </div>

        <!-- Details -->
        <div class="p-5 flex-1 flex flex-col justify-between">
          <div>
            <h3 class="text-lg font-bold text-slate-900 dark:text-white mb-1">{{ camera.name }}</h3>
            <p class="text-sm text-slate-500 dark:text-slate-400 flex items-center">
              <svg class="w-4 h-4 mr-1.5 opacity-70" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
              {{ camera.location }}
            </p>
          </div>
          
          <div class="mt-4 pt-4 border-t border-slate-200 dark:border-white/5 flex items-center justify-between">
            <div class="flex flex-col">
              <span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-0.5">IP Address</span>
              <span class="text-sm font-mono text-slate-700 dark:text-slate-300">{{ camera.ip_address }}</span>
            </div>
            
            <button @click="deleteCamera(camera.id)" class="text-slate-400 hover:text-accent-rose p-2 rounded-lg hover:bg-accent-rose/10 opacity-0 group-hover:opacity-100 transition-all focus:opacity-100 outline-none">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Add Modal -->
    <Teleport to="body">
      <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center p-4" @click.self="closeModal">
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-slate-900/50 dark:bg-dark-950/80 backdrop-blur-sm"></div>
        
        <!-- Modal Card -->
        <div class="glass-strong rounded-2xl shadow-glass w-full max-w-lg overflow-hidden relative animate-fade-in-up border-gradient">
          <!-- Header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-white/[0.06]">
            <h3 class="text-lg font-display font-bold text-slate-900 dark:text-white">Add New Camera</h3>
            <button @click="closeModal" class="text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors w-8 h-8 rounded-lg hover:bg-slate-200 dark:hover:bg-white/5 flex items-center justify-center">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>
          
          <form @submit.prevent="submitForm" class="p-6 space-y-5">
            <div class="space-y-1.5">
              <label class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Camera Name *</label>
              <input v-model="form.name" type="text" required placeholder="e.g. Main Entrance LPR" class="glass-input w-full rounded-xl px-4 py-2.5 text-sm" />
            </div>
            
            <div class="grid grid-cols-2 gap-4">
              <div class="space-y-1.5">
                <label class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Location</label>
                <input v-model="form.location" type="text" placeholder="e.g. Gate A" class="glass-input w-full rounded-xl px-4 py-2.5 text-sm" />
              </div>
              <div class="space-y-1.5">
                <label class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">IP Address</label>
                <input v-model="form.ip_address" type="text" placeholder="e.g. 192.168.1.50" class="glass-input w-full rounded-xl px-4 py-2.5 text-sm font-mono" />
              </div>
            </div>

            <div class="space-y-1.5">
              <label class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Stream URL (MJPEG / Image Link)</label>
              <input v-model="form.stream_url" type="text" placeholder="e.g. http://192.168.1.50:8080/stream/video.mjpeg" class="glass-input w-full rounded-xl px-4 py-2.5 text-sm font-mono" />
            </div>
            
            <div class="space-y-1.5">
              <label class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Status</label>
              <select v-model="form.status" class="glass-input w-full rounded-xl px-4 py-2.5 text-sm">
                <option value="Online">Online</option>
                <option value="Offline">Offline</option>
              </select>
            </div>

            <div class="pt-3 flex justify-end space-x-3">
              <button type="button" @click="closeModal" class="px-5 py-2.5 rounded-xl font-medium text-sm text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white hover:bg-slate-200 dark:hover:bg-white/5 transition-all">Cancel</button>
              <button type="submit" :disabled="isSubmitting" class="btn-glow px-5 py-2.5 rounded-xl font-semibold text-sm text-white disabled:opacity-50 relative">
                <span class="relative z-10">{{ isSubmitting ? 'Saving...' : 'Save Camera' }}</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useSocket } from '~/composables/useSocket'

definePageMeta({
  middleware: 'auth'
})

const { socket } = useSocket()
const apiBase = useRuntimeConfig().public.apiBase || 'http://localhost:3001'

const cameras = ref([])
const loading = ref(true)
const showModal = ref(false)
const isSubmitting = ref(false)

const form = ref({
  name: '',
  location: '',
  ip_address: '',
  stream_url: '',
  status: 'Online'
})

const API_BASE = 'http://localhost:3001/api/cameras'

const fetchCameras = async () => {
  loading.value = true
  try {
    const res = await fetch(`${apiBase}/api/cameras`)
    const data = await res.json()
    if (data.success) {
      cameras.value = data.data.map(c => ({ ...c, liveFeed: null }))
    }
  } catch (err) {
    console.error('Failed to fetch cameras', err)
  } finally {
    loading.value = false
  }
}

const openModal = () => {
  form.value = { name: '', location: '', ip_address: '', stream_url: '', status: 'Online' }
  showModal.value = true
}

const closeModal = () => {
  showModal.value = false
}

const submitForm = async () => {
  isSubmitting.value = true
  try {
    const res = await fetch(`${apiBase}/api/cameras`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form.value)
    })
    
    if (res.ok) {
      await fetchCameras()
      closeModal()
    } else {
      alert('Failed to add camera')
    }
  } catch (err) {
    console.error('Error submitting form', err)
  } finally {
    isSubmitting.value = false
  }
}

const deleteCamera = async (id) => {
  if (!confirm('Are you sure you want to remove this camera?')) return
  
  try {
    const res = await fetch(`${apiBase}/api/cameras/${id}`, { method: 'DELETE' })
    if (res.ok) {
      cameras.value = cameras.value.filter(c => c.id !== id)
    }
  } catch (err) {
    console.error('Error deleting camera', err)
  }
}

const handleLiveFrame = (data) => {
  if (!data || !data.camera_id || !data.frame) return
  const cam = cameras.value.find(c => c.id === data.camera_id)
  if (cam) {
    cam.liveFeed = data.frame
    cam.status = 'Online' // Auto-set status to online if we receive frames
  }
}

onMounted(async () => {
  await fetchCameras()

  const registerEvents = () => {
    if (!socket.value) return
    socket.value.on('live_frame', handleLiveFrame)
  }

  if (socket.value) {
    registerEvents()
  } else {
    const interval = setInterval(() => {
      if (socket.value) {
        registerEvents()
        clearInterval(interval)
      }
    }, 100)
  }
})

onUnmounted(() => {
  if (socket.value) {
    socket.value.off('live_frame', handleLiveFrame)
  }
})
</script>
