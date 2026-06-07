import React from 'react'
import ToggleSwitch from './ToggleSwitch'
import { rowStyle } from './sharedStyles'

export default function PromptLayersTab({ layers, toggleLayer }) {
  return (
    <>
      <div style={{ padding: '12px 14px', borderRadius: 8, marginBottom: 20, background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)', fontSize: 12, color: 'var(--accent)' }}>
        Prompt 按层级注入，每层可独立开关。高层级（约束）优先级最高。
      </div>

      {layers.map((layer) => (
        <div key={layer.id} style={{
          ...rowStyle,
          marginBottom: 10, padding: '12px 14px', borderRadius: 10,
          background: layer.enabled ? 'var(--bg-secondary)' : 'var(--bg-tertiary)',
          border: `1px solid ${layer.enabled ? 'var(--border)' : 'var(--border)'}`,
          opacity: layer.enabled ? 1 : 0.5,
        }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>
              <span style={{ fontSize: 11, color: 'var(--accent)', marginRight: 6 }}>L{layer.level}</span>
              {layer.id}
              {layer.has_condition && <span style={{ fontSize: 10, color: 'var(--orange)', marginLeft: 6 }}>条件注入</span>}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>
              {layer.content_preview}
            </div>
          </div>
          <ToggleSwitch checked={layer.enabled} onChange={(v) => toggleLayer(layer.id, v)} />
        </div>
      ))}
    </>
  )
}
