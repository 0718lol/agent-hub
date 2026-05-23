import React from 'react'
import { Moon, Sun } from 'lucide-react'
import { useThemeStore } from '../stores/themeStore'

export default function ThemeToggle() {
  const theme = useThemeStore((s) => s.theme)
  const toggleTheme = useThemeStore((s) => s.toggleTheme)
  const isDark = theme === 'tech-dark'

  return (
    <button
      className="theme-toggle"
      onClick={toggleTheme}
      title={isDark ? '切换至现代活力风格' : '切换至科技深色风格'}
      aria-label={isDark ? '切换到浅色主题' : '切换到深色主题'}
    >
      <span className="theme-toggle-icon">
        {isDark ? <Moon size={17} /> : <Sun size={17} />}
      </span>
    </button>
  )
}
