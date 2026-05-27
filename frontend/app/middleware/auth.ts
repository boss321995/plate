export default defineNuxtRouteMiddleware((to) => {
  if (import.meta.server) return

  const { isAuthenticated } = useAuth()

  // If going to login page and already authenticated, redirect to dashboard
  if (to.path === '/login' && isAuthenticated.value) {
    return navigateTo('/')
  }

  // If not going to login page and not authenticated, redirect to login
  if (to.path !== '/login' && !isAuthenticated.value) {
    return navigateTo('/login')
  }
})
