import React from 'react'
import ToggleSwitch from './ToggleSwitch'
import styles from './SettingsPanel.module.css'

export default function LLMTab({
  isDark, saving, configured, provider, setProvider, apiKey, setApiKey,
  baseUrl, setBaseUrl, model, setModel, temperature, setTemperature,
  maxTokens, setMaxTokens, activeProvider, activeModel,
  ollamaModels, ollamaLoading, ollamaError, fetchOllamaModels,
  presets, applyPreset, presetsRef, highlightPresets,
  setHighlightPresets, handleSave, handleDisconnect,
  getProviderDisplayName,
}) {
  return (
    <>
      {/* Status banner */}
      <div className={styles.statusBanner} style={{
        background: configured ? (isDark ? 'rgba(34,197,94,0.12)' : '#ecfdf5') : (isDark ? 'rgba(245,158,11,0.12)' : '#fffbeb'),
        border: `1px solid ${configured ? (isDark ? 'rgba(34,197,94,0.25)' : '#a7f3d0') : (isDark ? 'rgba(245,158,11,0.25)' : '#fde68a')}`,
        color: configured ? 'var(--text-primary)' : (isDark ? '#fbbf24' : '#d97706'),
      }}>
        <span className={styles.statusText}>
          {configured
            ? `✅ 已连接 ${getProviderDisplayName(activeProvider, activeModel)}`
            : '⚠️ 未配置 — Agent 使用 Mock 回复'}
        </span>
        {configured && (
          <div className={styles.statusActions}>
            <button onClick={handleDisconnect} disabled={saving} className={styles.disconnectBtn} style={{
              border: `1px solid ${isDark ? 'rgba(34,197,94,0.25)' : '#a7f3d0'}`,
            }}>断开接入</button>
            <button onClick={() => {
              setHighlightPresets(true)
              presetsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
              setTimeout(() => setHighlightPresets(false), 1500)
            }} className={styles.switchBtn}>切换 LLM</button>
          </div>
        )}
      </div>

      {/* Presets */}
      <div ref={presetsRef} className={styles.presetsContainer} style={{
        padding: highlightPresets ? '8px' : 0,
        borderRadius: 8,
        background: highlightPresets ? (isDark ? 'rgba(34,197,94,0.12)' : '#ecfdf5') : 'transparent',
        border: highlightPresets ? `1px solid ${isDark ? 'rgba(34,197,94,0.25)' : '#a7f3d0'}` : '1px solid transparent',
      }}>
        <label className={styles.label}>快速选择</label>
        <div className={styles.presetGroup}>
          {presets.map((p) => (
            <button key={p.label} onClick={() => applyPreset(p)} className={styles.presetBtn} style={{
              background: isDark ? 'rgba(99,102,241,0.12)' : '#eef2ff', border: `1px solid ${isDark ? 'rgba(99,102,241,0.25)' : '#c7d2fe'}`,
            }}>{p.label}</button>
          ))}
        </div>
      </div>

      {/* Provider */}
      <div style={{ marginBottom: 16 }}>
        <label className={styles.label}>接口格式</label>
        <div className={styles.providerGroup}>
          {['openai', 'anthropic', 'ollama'].map((p) => (
            <button key={p} onClick={() => {
              setProvider(p);
              if (p === 'ollama') {
                setBaseUrl('http://127.0.0.1:11434/v1');
              }
            }} className={provider === p ? styles.optionBtnActive : styles.optionBtnInactive}>
              {p === 'openai' ? 'OpenAI 兼容' : p === 'anthropic' ? 'Anthropic' : 'Ollama 本地'}
            </button>
          ))}
        </div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <label className={styles.label}>API 地址</label>
        <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="https://api.example.com/v1" className={styles.inputSecondary} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <label className={styles.label}>模型名称</label>
        {provider === 'ollama' ? (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {ollamaModels.length > 0 ? (
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className={styles.inputSecondary}
                style={{ flex: 1 }}
              >
                {ollamaModels.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            ) : (
              <input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="例如: deepseek-r1:7b"
                className={styles.inputSecondary}
                style={{ flex: 1 }}
              />
            )}
            <button
              onClick={(e) => { e.preventDefault(); fetchOllamaModels(); }}
              disabled={ollamaLoading}
              className={styles.ollamaRefreshBtn}
              style={{
                background: isDark ? 'rgba(99,102,241,0.12)' : '#eef2ff',
                border: `1px solid ${isDark ? 'rgba(99,102,241,0.25)' : '#c7d2fe'}`,
              }}
            >
              {ollamaLoading ? '🔄' : '🔄 刷新'}
            </button>
          </div>
        ) : (
          <input value={model} onChange={(e) => setModel(e.target.value)}
            placeholder="model-name" className={styles.inputSecondary} />
        )}
        {provider === 'ollama' && ollamaError && (
          <div className={styles.warningInline} style={{ color: isDark ? '#fbbf24' : '#d97706' }}>
            ⚠️ {ollamaError}
          </div>
        )}
      </div>
      {provider !== 'ollama' && (
        <div style={{ marginBottom: 16 }}>
          <label className={styles.label}>API Key</label>
          <input value={apiKey} onChange={(e) => setApiKey(e.target.value)}
            type="password" placeholder="sk-..." className={styles.inputSecondary} />
        </div>
      )}

      {/* Temperature & Max Tokens */}
      <div className={styles.sliderRow}>
        <div className={styles.sliderCol}>
          <label className={styles.label}>Temperature: {temperature}</label>
          <input type="range" min="0" max="1" step="0.1" value={temperature}
            onChange={(e) => setTemperature(parseFloat(e.target.value))}
            style={{ width: '100%', accentColor: '#4f46e5' }} />
          <div className={styles.sliderLabels}>
            <span>精确</span><span>创意</span>
          </div>
        </div>
        <div className={styles.sliderCol}>
          <label className={styles.label}>Max Tokens</label>
          <input type="number" value={maxTokens}
            onChange={(e) => setMaxTokens(parseInt(e.target.value) || 4096)}
            className={styles.inputSecondary} />
        </div>
      </div>

      <button onClick={handleSave} disabled={saving} className={styles.saveBtn} style={{ opacity: saving ? 0.6 : 1 }}>
        {saving ? '保存中...' : '保存配置'}
      </button>
    </>
  )
}
