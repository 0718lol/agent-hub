import { create } from 'zustand'

const STORAGE_KEY = 'agent-hub-theme'

function getInitialTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'tech-dark' || stored === 'vibrant') return stored
  } catch {}
  return 'tech-dark'
}

export const useThemeStore = create((set) => ({
  theme: getInitialTheme(),
  toggleTheme: () =>
    set((state) => {
      const next = state.theme === 'tech-dark' ? 'vibrant' : 'tech-dark'
      try {
        localStorage.setItem(STORAGE_KEY, next)
      } catch {}
      return { theme: next }
    }),
}))
