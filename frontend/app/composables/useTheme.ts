import { ref, watch, onMounted } from 'vue'

export const useTheme = () => {
  const isDark = ref(true)

  const toggleTheme = () => {
    isDark.value = !isDark.value
    updateTheme()
  }

  const updateTheme = () => {
    if (import.meta.client) {
      if (isDark.value) {
        document.documentElement.classList.add('dark')
        localStorage.setItem('theme', 'dark')
      } else {
        document.documentElement.classList.remove('dark')
        localStorage.setItem('theme', 'light')
      }
    }
  }

  onMounted(() => {
    if (import.meta.client) {
      const savedTheme = localStorage.getItem('theme')
      if (savedTheme === 'light') {
        isDark.value = false
      } else {
        isDark.value = true
      }
      updateTheme()
    }
  })

  return {
    isDark,
    toggleTheme
  }
}
