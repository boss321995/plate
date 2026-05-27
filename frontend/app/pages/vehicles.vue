<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-display font-bold text-slate-900 dark:text-white">Vehicle Management</h1>
        <p class="text-slate-500 text-sm mt-0.5">Manage staff, internal vehicles, and whitelisted plates.</p>
      </div>
      <button @click="openModal" class="btn-glow text-white px-5 py-2.5 rounded-xl font-semibold transition-all flex items-center text-sm">
        <svg class="w-4 h-4 mr-2 relative z-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
        <span class="relative z-10">Add Vehicle</span>
      </button>
    </div>

    <!-- Vehicles Table -->
    <div class="glass-card rounded-2xl overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead class="border-b border-slate-200 dark:border-white/[0.06]">
            <tr>
              <th class="px-6 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Plate Number</th>
              <th class="px-6 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Owner Name</th>
              <th class="px-6 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Vehicle Type</th>
              <th class="px-6 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">Role</th>
              <th class="px-6 py-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-200 dark:divide-white/[0.04]">
            <tr v-if="loading">
              <td colspan="5" class="px-6 py-12 text-center text-slate-500">
                <svg class="animate-spin w-5 h-5 mx-auto mb-2 text-accent-cyan" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                Loading vehicles...
              </td>
            </tr>
            <tr v-else-if="vehicles.length === 0">
              <td colspan="5" class="px-6 py-12 text-center text-slate-500">No vehicles found. Click "Add Vehicle" to create one.</td>
            </tr>
            <tr v-else v-for="vehicle in vehicles" :key="vehicle.id" class="hover:bg-slate-100/50 dark:hover:bg-white/[0.03] transition-colors group">
              <td class="px-6 py-3.5">
                <div class="flex items-center">
                  <div class="font-mono font-bold text-slate-800 dark:text-white bg-slate-200/50 dark:bg-white/5 px-3 py-1 rounded-lg border border-slate-300 dark:border-white/10 text-sm">{{ vehicle.plate_number }}</div>
                  <span class="ml-3 text-xs text-slate-500">{{ vehicle.province }}</span>
                </div>
              </td>
              <td class="px-6 py-3.5 font-medium text-slate-700 dark:text-slate-300">{{ vehicle.owner_name || '-' }}</td>
              <td class="px-6 py-3.5 text-slate-600 dark:text-slate-400">{{ vehicle.vehicle_type }}</td>
              <td class="px-6 py-3.5">
                <span v-if="vehicle.is_blacklist" class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-accent-rose/15 text-rose-600 dark:text-rose-400 tracking-wide">BLACKLIST</span>
                <span v-else-if="vehicle.is_staff" class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-accent-emerald/15 text-emerald-600 dark:text-emerald-400 tracking-wide">STAFF</span>
                <span v-else-if="vehicle.is_internal" class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-brand-500/15 text-blue-600 dark:text-blue-400 tracking-wide">INTERNAL</span>
                <span v-else class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-slate-200 dark:bg-white/5 text-slate-600 dark:text-slate-400 tracking-wide">WHITELIST</span>
              </td>
              <td class="px-6 py-3.5 text-right">
                <button @click="deleteVehicle(vehicle.id)" class="text-slate-500 hover:text-accent-rose p-2 rounded-lg hover:bg-accent-rose/10 opacity-0 group-hover:opacity-100 transition-all">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
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
            <h3 class="text-lg font-display font-bold text-slate-900 dark:text-white">Add New Vehicle</h3>
            <button @click="closeModal" class="text-slate-500 hover:text-slate-900 dark:hover:text-white transition-colors w-8 h-8 rounded-lg hover:bg-slate-200 dark:hover:bg-white/5 flex items-center justify-center">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>
          
          <form @submit.prevent="submitForm" class="p-6 space-y-5">
            <div class="grid grid-cols-2 gap-4">
              <div class="space-y-1.5">
                <label class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Plate Number *</label>
                <input v-model="form.plate_number" type="text" required placeholder="e.g. 1กข 1234" class="glass-input w-full rounded-xl px-4 py-2.5 text-sm" />
              </div>
              <div class="space-y-1.5">
                <label class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Province</label>
                <input v-model="form.province" type="text" placeholder="e.g. กรุงเทพมหานคร" class="glass-input w-full rounded-xl px-4 py-2.5 text-sm" />
              </div>
            </div>
            
            <div class="space-y-1.5">
              <label class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Owner Name</label>
              <input v-model="form.owner_name" type="text" placeholder="Owner Name" class="glass-input w-full rounded-xl px-4 py-2.5 text-sm" />
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div class="space-y-1.5">
                <label class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Vehicle Type</label>
                <select v-model="form.vehicle_type" class="glass-input w-full rounded-xl px-4 py-2.5 text-sm">
                  <option value="CAR">Car</option>
                  <option value="MOTORCYCLE">Motorcycle</option>
                  <option value="OTHER">Other</option>
                </select>
              </div>
              <div class="space-y-1.5">
                <label class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Role</label>
                <select v-model="form.role" class="glass-input w-full rounded-xl px-4 py-2.5 text-sm">
                  <option value="STAFF">Staff</option>
                  <option value="INTERNAL">Internal Use</option>
                  <option value="BLACKLIST" class="text-accent-rose font-bold">Blacklist</option>
                </select>
              </div>
            </div>

            <div class="pt-3 flex justify-end space-x-3">
              <button type="button" @click="closeModal" class="px-5 py-2.5 rounded-xl font-medium text-sm text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white hover:bg-slate-200 dark:hover:bg-white/5 transition-all">Cancel</button>
              <button type="submit" :disabled="isSubmitting" class="btn-glow px-5 py-2.5 rounded-xl font-semibold text-sm text-white disabled:opacity-50 relative">
                <span class="relative z-10">{{ isSubmitting ? 'Saving...' : 'Save Vehicle' }}</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

definePageMeta({
  middleware: 'auth'
})

const vehicles = ref([])
const loading = ref(true)
const showModal = ref(false)
const isSubmitting = ref(false)

const form = ref({
  plate_number: '',
  province: '',
  owner_name: '',
  vehicle_type: 'CAR',
  role: 'STAFF'
})

const API_BASE = 'http://localhost:3001/api/vehicles'

const fetchVehicles = async () => {
  loading.value = true
  try {
    const res = await fetch(API_BASE)
    const data = await res.json()
    if (data.success) {
      vehicles.value = data.data
    }
  } catch (err) {
    console.error('Failed to fetch vehicles', err)
  } finally {
    loading.value = false
  }
}

const openModal = () => {
  form.value = { plate_number: '', province: '', owner_name: '', vehicle_type: 'CAR', role: 'STAFF' }
  showModal.value = true
}

const closeModal = () => {
  showModal.value = false
}

const submitForm = async () => {
  isSubmitting.value = true
  try {
    const payload = {
      plate_number: form.value.plate_number,
      province: form.value.province,
      owner_name: form.value.owner_name,
      vehicle_type: form.value.vehicle_type,
      is_staff: form.value.role === 'STAFF',
      is_internal: form.value.role === 'INTERNAL',
      is_blacklist: form.value.role === 'BLACKLIST',
      plate_type: 'NORMAL'
    }

    const res = await fetch(API_BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    
    if (res.ok) {
      await fetchVehicles()
      closeModal()
    } else {
      alert('Failed to add vehicle')
    }
  } catch (err) {
    console.error('Error submitting form', err)
  } finally {
    isSubmitting.value = false
  }
}

const deleteVehicle = async (id) => {
  if (!confirm('Are you sure you want to delete this vehicle?')) return
  
  try {
    const res = await fetch(`${API_BASE}/${id}`, { method: 'DELETE' })
    if (res.ok) {
      vehicles.value = vehicles.value.filter(v => v.id !== id)
    }
  } catch (err) {
    console.error('Error deleting vehicle', err)
  }
}

onMounted(() => {
  fetchVehicles()
})
</script>
