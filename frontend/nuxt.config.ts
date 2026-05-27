// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  devtools: { enabled: false },
  modules: ['@nuxtjs/tailwindcss'],
  ssr: false, // For Nginx Static Hosting
  app: {
    head: {
      title: 'LPR & Access Analytics',
      meta: [
        { name: 'description', content: 'Vehicle License Plate Recognition System' }
      ]
    }
  }
})
