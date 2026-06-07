import React from 'react'
import ToggleSwitch from './ToggleSwitch'
import { labelStyle, rowStyle, makeBtnStyle } from './sharedStyles'

export default function QualityGateTab({
  qEnabled, setQEnabled, bestOfN, setBestOfN,
  maxRetries, setMaxRetries, useLlmJudge, setUseLlmJudge,
  handleSaveQuality, saving,
}) {
  const btnStyle = makeBtnStyle(saving)

  return (
    <>
      <div style={{ padding: '12px 14px', borderRadius: 8, marginBottom: 20, background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)', fontSize: 12, color: 'var(--accent)' }}>
        质量门会自动评估 Agent 输出，不达标时触发重写或择优选择
      </div>

      {/* Enable toggle */}
      <div style={{ ...rowStyle, marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 14, color: 'var(--text-primary)', fontWeight: 500 }}>启用质量门</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>关闭后 Agent 直接输出不评估</div>
        </div>
        <ToggleSwitch checked={qEnabled} onChange={setQEnabled} />
      </div>

      {/* Best of N */}
      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>多候选择优 (Best-of-N)</label>
        <div style={{ display: 'flex', gap: 8 }}>
          {[1, 2, 3].map((n) => (
            <button key={n} onClick={() => setBestOfN(n)} style={{
              flex: 1, padding: '10px', borderRadius: 8, fontSize: 13,
              background: bestOfN === n ? 'var(--accent)' : 'var(--bg-secondary)',
              border: `1px solid ${bestOfN === n ? 'var(--accent)' : 'var(--border)'}`,
              color: bestOfN === n ? 'white' : 'var(--text-secondary)',
              cursor: 'pointer', fontWeight: bestOfN === n ? 600 : 400,
            }}>
              {n === 1 ? '关闭' : `${n} 候选`}
            </button>
          ))}
        </div>
        {bestOfN > 1 && (
          <div style={{ marginTop: 6, fontSize: 11, color: 'var(--orange)' }}>
            ⚠️ 将消耗 {bestOfN}x Token，适合高质量关键输出
          </div>
        )}
      </div>

      {/* Max Retries */}
      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>不达标自动重写次数</label>
        <div style={{ display: 'flex', gap: 8 }}>
          {[0, 1, 2].map((n) => (
            <button key={n} onClick={() => setMaxRetries(n)} style={{
              flex: 1, padding: '10px', borderRadius: 8, fontSize: 13,
              background: maxRetries === n ? 'var(--accent)' : 'var(--bg-secondary)',
              border: `1px solid ${maxRetries === n ? 'var(--accent)' : 'var(--border)'}`,
              color: maxRetries === n ? 'white' : 'var(--text-secondary)',
              cursor: 'pointer', fontWeight: maxRetries === n ? 600 : 400,
            }}>
              {n === 0 ? '不重写' : `${n} 次`}
            </button>
          ))}
        </div>
      </div>

      {/* LLM Judge */}
      <div style={{ ...rowStyle, marginBottom: 20 }}>
        <div>
          <div style={{ fontSize: 14, color: 'var(--text-primary)', fontWeight: 500 }}>LLM 深度评审</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>用 LLM 做语义级质量评分（额外消耗 Token）</div>
        </div>
        <ToggleSwitch checked={useLlmJudge} onChange={setUseLlmJudge} />
      </div>

      <button onClick={handleSaveQuality} disabled={saving} style={btnStyle}>
        {saving ? '保存中...' : '保存质量门配置'}
      </button>
    </>
  )
}
