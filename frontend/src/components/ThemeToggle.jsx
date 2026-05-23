import React from 'react'
import { Moon, Sun } from 'lucide-react'
import { useThemeStore } from '../stores/themeStore'

export default function ThemeToggle() {
  const theme = useThemeStore((s) => s.theme)
  const toggleTheme = useThemeStore((s) => s.toggleTheme)
  const isDark = theme === 'dark'

  return (
    <button
      className="theme-toggle"
      onClick={toggleTheme}
      title={isDark ? '切换到浅色模式' : '切换到深色模式'}
      aria-label={isDark ? '切换到浅色模式' : '切换到深色模式'}
    >
      {isDark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  )
}
