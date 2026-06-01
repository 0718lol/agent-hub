import React from 'react'
import { useThemeStore } from '../../stores/themeStore'

export default function ToggleSwitch({ checked, onChange }) {
  const isDark = useThemeStore((s) => s.theme === 'dark')
  return (
    <div onClick={() => onChange(!checked)} style={{
      width: 44, height: 24, borderRadius: 12, cursor: 'pointer',
      background: checked ? '#4f46e5' : (isDark ? 'rgba(255,255,255,0.15)' : '#d1d5db'),
      border: `1px solid ${checked ? '#4f46e5' : (isDark ? 'rgba(255,255,255,0.15)' : '#d1d5db')}`,
      position: 'relative', transition: 'all 0.2s', flexShrink: 0,
    }}>
      <div style={{
        width: 18, height: 18, borderRadius: 9,
        background: 'white', position: 'absolute', top: 2,
        left: checked ? 22 : 3, transition: 'left 0.2s',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
      }} />
    </div>
  )
}
