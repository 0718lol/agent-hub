import React from 'react'
import ToggleSwitch from './ToggleSwitch'
import styles from './SettingsPanel.module.css'

export default function QualityGateTab({
  isDark, saving, qEnabled, setQEnabled, bestOfN, setBestOfN,
  maxRetries, setMaxRetries, useLlmJudge, setUseLlmJudge, handleSaveQuality,
}) {
  return (
    <>
      <div className={styles.qualityInfoBox} style={{ background: isDark ? 'rgba(99,102,241,0.12)' : '#eef2ff', border: `1px solid ${isDark ? 'rgba(99,102,241,0.25)' : '#c7d2fe'}` }}>
        质量门会自动评估 Agent 输出，不达标时触发重写或择优选择
      </div>

      {/* Enable toggle */}
      <div className={styles.toggleRow} style={{ marginBottom: 16 }}>
        <div>
          <div className={styles.toggleTitle}>启用质量门</div>
          <div className={styles.toggleDesc}>关闭后 Agent 直接输出不评估</div>
        </div>
        <ToggleSwitch checked={qEnabled} onChange={setQEnabled} />
      </div>

      {/* Best of N */}
      <div style={{ marginBottom: 16 }}>
        <label className={styles.label}>多候选择优 (Best-of-N)</label>
        <div style={{ display: 'flex', gap: 8 }}>
          {[1, 2, 3].map((n) => (
            <button key={n} onClick={() => setBestOfN(n)} className={bestOfN === n ? styles.optionBtnActive : styles.optionBtnInactive}>
              {n === 1 ? '关闭' : `${n} 候选`}
            </button>
          ))}
        </div>
        {bestOfN > 1 && (
          <div className={styles.warningText} style={{ color: isDark ? '#fbbf24' : '#d97706' }}>
            ⚠️ 将消耗 {bestOfN}x Token，适合高质量关键输出
          </div>
        )}
      </div>

      {/* Max Retries */}
      <div style={{ marginBottom: 16 }}>
        <label className={styles.label}>不达标自动重写次数</label>
        <div style={{ display: 'flex', gap: 8 }}>
          {[0, 1, 2].map((n) => (
            <button key={n} onClick={() => setMaxRetries(n)} className={maxRetries === n ? styles.optionBtnActive : styles.optionBtnInactive}>
              {n === 0 ? '不重写' : `${n} 次`}
            </button>
          ))}
        </div>
      </div>

      {/* LLM Judge */}
      <div className={styles.toggleRow} style={{ marginBottom: 20 }}>
        <div>
          <div className={styles.toggleTitle}>LLM 深度评审</div>
          <div className={styles.toggleDesc}>用 LLM 做语义级质量评分（额外消耗 Token）</div>
        </div>
        <ToggleSwitch checked={useLlmJudge} onChange={setUseLlmJudge} />
      </div>

      <button onClick={handleSaveQuality} disabled={saving} className={styles.saveBtn} style={{ opacity: saving ? 0.6 : 1 }}>
        {saving ? '保存中...' : '保存质量门配置'}
      </button>
    </>
  )
}
