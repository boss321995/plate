<template>
  <div class="min-h-screen flex items-center justify-center relative z-10 p-4">
    <!-- Extra glow behind card -->
    <div class="absolute w-[500px] h-[500px] bg-accent-cyan/10 rounded-full blur-[150px] pointer-events-none"></div>
    <div class="absolute w-[400px] h-[400px] bg-accent-violet/10 rounded-full blur-[120px] translate-x-32 translate-y-20 pointer-events-none"></div>

    <!-- Login Card -->
    <div class="w-full max-w-md animate-fade-in-up">
      <div class="glass-card rounded-3xl p-8 border-gradient shadow-glass relative overflow-hidden">
        <!-- Shimmer overlay -->
        <div class="absolute inset-0 overflow-hidden rounded-3xl pointer-events-none">
          <div class="absolute inset-0 bg-gradient-to-r from-transparent via-slate-500/10 dark:via-white/5 to-transparent -translate-x-full animate-shimmer"></div>
        </div>

        <!-- Logo & Brand -->
        <div class="relative z-10 text-center mb-8">
          <div class="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-accent-cyan to-brand-500 shadow-glow-cyan mb-4 animate-float">
            <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"></path>
            </svg>
          </div>
          <h1 class="text-2xl font-display font-bold text-gradient mb-1">LPR Analytics</h1>
          <p class="text-slate-500 dark:text-slate-400 text-sm">Vehicle License Plate Recognition System</p>
        </div>

        <!-- Error Message -->
        <div v-if="errorMessage" class="relative z-10 mb-6 p-3 rounded-xl bg-accent-rose/10 border border-accent-rose/20 text-accent-rose text-sm flex items-center">
          <svg class="w-4 h-4 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          {{ errorMessage }}
        </div>

        <!-- Login Form -->
        <form @submit.prevent="handleLogin" class="relative z-10 space-y-5">
          <div class="space-y-1.5">
            <label class="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Username</label>
            <div class="relative">
              <div class="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path>
                </svg>
              </div>
              <input
                v-model="username"
                type="text"
                placeholder="Enter username"
                required
                class="glass-input w-full pl-11 pr-4 py-3 rounded-xl text-sm font-medium"
                autocomplete="username"
              />
            </div>
          </div>

          <div class="space-y-1.5">
            <label class="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Password</label>
            <div class="relative">
              <div class="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
                </svg>
              </div>
              <input
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                placeholder="Enter password"
                required
                class="glass-input w-full pl-11 pr-11 py-3 rounded-xl text-sm font-medium"
                autocomplete="current-password"
              />
              <button type="button" @click="showPassword = !showPassword" class="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors">
                <svg v-if="!showPassword" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                </svg>
                <svg v-else class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"></path>
                </svg>
              </button>
            </div>
          </div>

          <div class="flex items-center justify-between">
            <label class="flex items-center cursor-pointer group">
              <div class="relative">
                <input v-model="rememberMe" type="checkbox" class="sr-only peer" />
                <div class="w-9 h-5 rounded-full bg-slate-300 dark:bg-white/10 peer-checked:bg-accent-cyan/30 transition-colors"></div>
                <div class="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white dark:bg-slate-400 peer-checked:bg-accent-cyan peer-checked:translate-x-4 transition-all shadow-sm"></div>
              </div>
              <span class="ml-2.5 text-sm text-slate-500 dark:text-slate-400 group-hover:text-slate-700 dark:group-hover:text-slate-300 transition-colors">Remember me</span>
            </label>
          </div>

          <button
            type="submit"
            :disabled="isLoading"
            class="btn-glow w-full py-3.5 rounded-xl text-white font-semibold text-sm tracking-wide disabled:opacity-50 disabled:cursor-not-allowed relative"
          >
            <span v-if="!isLoading" class="relative z-10 flex items-center justify-center">
              <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1"></path>
              </svg>
              Sign In
            </span>
            <span v-else class="relative z-10 flex items-center justify-center">
              <svg class="animate-spin w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Authenticating...
            </span>
          </button>
        </form>

        <!-- Footer -->
        <div class="relative z-10 mt-6 pt-6 border-t border-slate-200 dark:border-white/5 text-center">
          <p class="text-xs text-slate-400 dark:text-slate-500">Protected System · Authorized Personnel Only</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

definePageMeta({
  layout: false,
  middleware: 'auth'
})

const { login, isLoading } = useAuth()

const username = ref('')
const password = ref('')
const showPassword = ref(false)
const rememberMe = ref(false)
const errorMessage = ref('')

const handleLogin = async () => {
  errorMessage.value = ''
  const result = await login(username.value, password.value)
  if (result.success) {
    navigateTo('/')
  } else {
    errorMessage.value = result.message || 'Invalid credentials'
  }
}
</script>
