import React from 'react'

export default function ToggleSwitch({ checked, onChange }) {
  return (
    <div onClick={() => onChange(!checked)} style={{
      width: 44, height: 24, borderRadius: 12, cursor: 'pointer',
      background: checked ? 'var(--accent)' : 'var(--border)',
      border: `1px solid ${checked ? 'var(--accent)' : 'var(--border)'}`,
      position: 'relative', transition: 'all 0.2s', flexShrink: 0,
    }}>
      <div style={{
        width: 18, height: 18, borderRadius: 9,
        background: 'var(--bg-primary)', position: 'absolute', top: 2,
        left: checked ? 22 : 3, transition: 'left 0.2s',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
      }} />
    </div>
  )
}
