// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  devtools: { enabled: false },

  modules: ['@nuxtjs/tailwindcss'],

  // SPA mode for Nginx static hosting
  ssr: false,

  // ── Route-level optimizations ──────────────────────────────────────────────
  routeRules: {
    '/': { prerender: false },
  },

  // ── App metadata ───────────────────────────────────────────────────────────
  app: {
    baseURL: '/plate/',
    head: {
      title: 'LPR & Access Analytics',
      meta: [
        { name: 'description', content: 'Vehicle License Plate Recognition System' },
        // Critical for mobile performance
        { name: 'viewport',    content: 'width=device-width, initial-scale=1, viewport-fit=cover' },
        { name: 'theme-color', content: '#050a18' },
      ],
      link: [
        // Preconnect to Google Fonts
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
      ]
    },
    // Chunk splitting — lazy load per route
    pageTransition:  { name: 'page',   mode: 'out-in' },
    layoutTransition: { name: 'layout', mode: 'out-in' },
  },

  // ── Runtime Config ─────────────────────────────────────────────────────────
  runtimeConfig: {
    public: {
      apiBase:          '/api/plate',
      snapshotInterval: 2000,   // ms between camera snapshot polls
      socketThrottle:   2000,   // ms to aggregate Socket.IO events
    }
  },

  // ── Vite optimizations ─────────────────────────────────────────────────────
  vite: {
    build: {
      // Split vendor chunks for better caching
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('node_modules/socket.io-client')) return 'socket-io';
            if (id.includes('node_modules/apexcharts'))        return 'charts';
            if (id.includes('node_modules/vue'))               return 'vue-vendor';
          }
        }
      }
    },
    // CSS minification
    css: {
      devSourcemap: false,
    }
  },
})
