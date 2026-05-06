import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Theme = 'light' | 'dark' | 'rain'

interface ThemeState {
  theme: Theme
  toggleTheme: () => void
  setTheme: (theme: Theme) => void
}

const THEME_CYCLE: Theme[] = ['light', 'dark', 'rain']

function applyThemeClass(theme: Theme) {
  const html = document.documentElement
  html.classList.remove('dark', 'rain')

  if (theme === 'dark') {
    html.classList.add('dark')
  } else if (theme === 'rain') {
    html.classList.add('rain')
  }

  html.setAttribute('data-theme', theme)
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: 'light',

      toggleTheme: () => {
        const current = get().theme
        const currentIndex = THEME_CYCLE.indexOf(current)
        const nextIndex = (currentIndex + 1) % THEME_CYCLE.length
        const nextTheme = THEME_CYCLE[nextIndex]

        applyThemeClass(nextTheme)
        set({ theme: nextTheme })
      },

      setTheme: (theme) => {
        applyThemeClass(theme)
        set({ theme })
      },
    }),
    {
      name: 'theme-storage',
      onRehydrateStorage: () => (state) => {
        if (state) {
          applyThemeClass(state.theme)
        }
      },
    }
  )
)

export function getThemeLabel(theme: Theme): string {
  switch (theme) {
    case 'light':
      return '☀️ 浅色模式'
    case 'dark':
      return '🌙 深色模式'
    case 'rain':
      return '🌧️ 雨天模式'
  }
}
