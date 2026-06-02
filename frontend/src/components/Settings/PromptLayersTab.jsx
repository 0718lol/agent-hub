import React from 'react'
import ToggleSwitch from './ToggleSwitch'
import styles from './SettingsPanel.module.css'

export default function PromptLayersTab({ isDark, layers, toggleLayer }) {
  return (
    <>
      <div className={styles.promptInfoBox} style={{ background: isDark ? 'rgba(99,102,241,0.12)' : '#eef2ff', border: `1px solid ${isDark ? 'rgba(99,102,241,0.25)' : '#c7d2fe'}` }}>
        Prompt 按层级注入，每层可独立开关。高层级（约束）优先级最高。
      </div>

      {layers.map((layer) => (
        <div key={layer.id} className={layer.enabled ? styles.layerRow : styles.layerRowDisabled}>
          <div className={styles.layerBody}>
            <div className={styles.layerName}>
              <span className={styles.levelBadge}>L{layer.level}</span>
              {layer.id}
              {layer.has_condition && <span className={styles.conditionTag} style={{ color: isDark ? '#fbbf24' : '#d97706' }}>条件注入</span>}
            </div>
            <div className={styles.layerPreview}>
              {layer.content_preview}
            </div>
          </div>
          <ToggleSwitch checked={layer.enabled} onChange={(v) => toggleLayer(layer.id, v)} />
        </div>
      ))}
    </>
  )
}
