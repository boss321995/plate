<template>
  <div class="flex h-screen overflow-hidden relative z-10">
    <!-- Sidebar -->
    <aside class="w-72 flex-shrink-0 glass-strong flex flex-col border-r border-slate-200 dark:border-white/[0.06] relative">
      <!-- Animated gradient line on the right edge -->
      <div class="absolute top-0 right-0 w-[1px] h-full bg-gradient-to-b from-accent-cyan/40 via-accent-violet/30 to-accent-cyan/40 bg-[length:100%_200%] animate-gradient-shift"></div>

      <!-- Logo -->
      <div class="h-16 flex items-center px-6 border-b border-slate-200 dark:border-white/[0.06]">
        <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-accent-cyan to-brand-500 flex items-center justify-center text-white font-bold text-lg mr-3 shadow-glow-cyan animate-glow-pulse">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"></path>
          </svg>
        </div>
        <div>
          <span class="font-display font-bold text-lg tracking-tight text-gradient">LPR Analytics</span>
          <p class="text-[10px] text-slate-500 -mt-0.5 tracking-wider uppercase">Access Control</p>
        </div>
      </div>
      
      <!-- Navigation -->
      <nav class="flex-1 overflow-y-auto py-6 px-4 space-y-1.5">
        <p class="text-[10px] font-bold text-slate-500 uppercase tracking-widest px-3 mb-3">Main Menu</p>
        
        <NuxtLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-item flex items-center px-3 py-2.5 rounded-xl font-medium transition-all duration-300 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white group relative"
          :class="isActive(item.to) ? 'nav-item-active text-slate-900 dark:text-white' : ''"
        >
          <!-- Active indicator bar -->
          <div v-if="isActive(item.to)" class="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 rounded-full bg-gradient-to-b from-accent-cyan to-brand-500 shadow-glow-cyan"></div>
          
          <div
            class="w-9 h-9 rounded-lg flex items-center justify-center mr-3 transition-all duration-300"
            :class="isActive(item.to) ? 'bg-accent-cyan/10 text-accent-cyan' : 'bg-slate-100 dark:bg-white/5 text-slate-500 group-hover:bg-slate-200 dark:group-hover:bg-white/10 group-hover:text-slate-700 dark:group-hover:text-slate-300'"
            v-html="item.icon"
          ></div>
          <div>
            <span class="text-sm">{{ item.label }}</span>
            <p class="text-[10px] text-slate-500 dark:text-slate-600 group-hover:text-slate-600 dark:group-hover:text-slate-500 transition-colors">{{ item.desc }}</p>
          </div>
        </NuxtLink>
      </nav>

      <!-- User Section -->
      <div class="p-4 border-t border-slate-200 dark:border-white/[0.06] space-y-2">
        <div class="flex items-center px-3 py-2">
          <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-accent-violet to-accent-fuchsia flex items-center justify-center text-white text-xs font-bold mr-3">
            {{ userInitial }}
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{{ user?.displayName || 'Admin' }}</p>
            <p class="text-[10px] text-slate-500 truncate">{{ user?.role || 'administrator' }}</p>
          </div>
        </div>
        <button @click="logout" class="flex items-center w-full px-3 py-2 rounded-xl text-sm font-medium transition-all duration-200 text-slate-500 hover:text-accent-rose hover:bg-accent-rose/10 dark:hover:bg-accent-rose/5 group">
          <svg class="w-4 h-4 mr-3 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
          Sign Out
        </button>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="flex-1 flex flex-col overflow-hidden relative">
      <!-- Header -->
      <header class="h-16 flex-shrink-0 glass border-b border-slate-200 dark:border-white/[0.06] flex items-center justify-between px-8 z-10">
        <div>
          <h1 class="text-lg font-display font-bold text-slate-900 dark:text-white">{{ routeName }}</h1>
          <p class="text-[11px] text-slate-500 -mt-0.5">{{ routeDesc }}</p>
        </div>
        <div class="flex items-center space-x-3">
          <!-- Status Indicator -->
          <div class="glass-card rounded-xl px-3 py-1.5 flex items-center space-x-2">
            <span class="w-2 h-2 rounded-full bg-accent-emerald neon-dot animate-pulse text-accent-emerald"></span>
            <span class="text-xs text-slate-600 dark:text-slate-400 font-medium">System Online</span>
          </div>

          <!-- Theme Toggle Button -->
          <button @click="toggleTheme" class="relative w-9 h-9 rounded-xl glass-card flex items-center justify-center text-slate-500 hover:text-accent-cyan transition-colors">
            <svg v-if="isDark" class="w-4.5 h-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"></path></svg>
            <svg v-else class="w-4.5 h-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"></path></svg>
          </button>

          <!-- Notification Bell -->
          <button class="relative w-9 h-9 rounded-xl glass-card flex items-center justify-center text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors">
            <span class="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-accent-rose neon-dot text-accent-rose border-2 border-white dark:border-dark-950"></span>
            <svg class="w-4.5 h-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"></path></svg>
          </button>

          <!-- User Avatar -->
          <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-accent-cyan/20 to-accent-violet/20 border border-slate-300 dark:border-white/10 overflow-hidden flex items-center justify-center text-accent-cyan font-bold text-sm">
            {{ userInitial }}
          </div>
        </div>
      </header>
      
      <div class="flex-1 overflow-y-auto p-8 z-10">
        <slot />
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useTheme } from '~/composables/useTheme'

const route = useRoute()
const { user, logout } = useAuth()
const { isDark, toggleTheme } = useTheme()

const userInitial = computed(() => {
  const name = user.value?.displayName || 'A'
  return name.charAt(0).toUpperCase()
})

const routeName = computed(() => {
  if (route.path === '/') return 'Dashboard'
  if (route.path === '/logs') return 'Detection Logs'
  if (route.path === '/vehicles') return 'Vehicle Management'
  return 'System'
})

const routeDesc = computed(() => {
  if (route.path === '/') return 'Real-time monitoring & analytics'
  if (route.path === '/logs') return 'Historical access records'
  if (route.path === '/vehicles') return 'Staff & whitelist management'
  return ''
})

const isActive = (path) => {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}

const navItems = [
  {
    to: '/',
    label: 'Dashboard',
    desc: 'Overview & analytics',
    icon: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z"></path></svg>'
  },
  {
    to: '/logs',
    label: 'Detection Logs',
    desc: 'Access history',
    icon: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"></path></svg>'
  },
  {
    to: '/vehicles',
    label: 'Whitelist / Staff',
    desc: 'Vehicle registry',
    icon: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>'
  },
  {
    to: '/cameras',
    label: 'Cameras',
    desc: 'Gate & camera status',
    icon: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>'
  },
  {
    to: '/parking',
    label: 'Active Parking',
    desc: 'Dwell time & overstay',
    icon: '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"></path></svg>'
  },
]
</script>

<style scoped>
.nav-item {
  backdrop-filter: blur(0);
}

.nav-item:hover {
  background: rgba(148, 163, 184, 0.1);
}
html.dark .nav-item:hover {
  background: rgba(255, 255, 255, 0.05);
}

.nav-item-active {
  background: linear-gradient(135deg, rgba(14, 165, 233, 0.1) 0%, rgba(59, 130, 246, 0.05) 100%);
  border: 1px solid rgba(14, 165, 233, 0.2);
}
html.dark .nav-item-active {
  background: linear-gradient(135deg, rgba(6, 182, 212, 0.08) 0%, rgba(59, 130, 246, 0.04) 100%);
  border: 1px solid rgba(6, 182, 212, 0.1);
}
</style>
