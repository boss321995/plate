import { ref, computed } from 'vue'

interface User {
  id: number
  username: string
  displayName: string
  role: string
}

const user = ref<User | null>(null)
const token = ref<string | null>(null)
const isLoading = ref(false)

// Initialize from localStorage
if (import.meta.client) {
  const savedToken = localStorage.getItem('auth_token')
  const savedUser = localStorage.getItem('auth_user')
  if (savedToken && savedUser) {
    token.value = savedToken
    try {
      user.value = JSON.parse(savedUser)
    } catch {
      localStorage.removeItem('auth_token')
      localStorage.removeItem('auth_user')
    }
  }
}

export const useAuth = () => {
  const isAuthenticated = computed(() => !!token.value && !!user.value)

  const login = async (username: string, password: string): Promise<{ success: boolean; message?: string }> => {
    isLoading.value = true
    try {
      const res = await fetch('http://localhost:3001/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      })
      const data = await res.json()

      if (data.success) {
        token.value = data.data.token
        user.value = data.data.user
        localStorage.setItem('auth_token', data.data.token)
        localStorage.setItem('auth_user', JSON.stringify(data.data.user))
        return { success: true }
      } else {
        return { success: false, message: data.message || 'Login failed' }
      }
    } catch (error) {
      return { success: false, message: 'Cannot connect to server' }
    } finally {
      isLoading.value = false
    }
  }

  const logout = () => {
    token.value = null
    user.value = null
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_user')
    navigateTo('/login')
  }

  const checkAuth = async (): Promise<boolean> => {
    if (!token.value) return false
    try {
      const res = await fetch('http://localhost:3001/api/auth/me', {
        headers: { Authorization: `Bearer ${token.value}` }
      })
      const data = await res.json()
      if (data.success) {
        user.value = data.data
        return true
      } else {
        logout()
        return false
      }
    } catch {
      return false
    }
  }

  return {
    user,
    token,
    isLoading,
    isAuthenticated,
    login,
    logout,
    checkAuth
  }
}
