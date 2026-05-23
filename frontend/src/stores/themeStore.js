import { create } from 'zustand'

const STORAGE_KEY = 'agent-hub-theme'

function getInitialTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch {}
  return 'light'
}

export const useThemeStore = create((set) => ({
  theme: getInitialTheme(),
  toggleTheme: () =>
    set((state) => {
      const next = state.theme === 'light' ? 'dark' : 'light'
      try {
        localStorage.setItem(STORAGE_KEY, next)
      } catch {}
      return { theme: next }
    }),
}))
