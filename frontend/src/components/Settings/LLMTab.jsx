import React from 'react'
import ToggleSwitch from './ToggleSwitch'

export default function LLMTab({
  isDark, saving, configured, provider, setProvider, apiKey, setApiKey,
  baseUrl, setBaseUrl, model, setModel, temperature, setTemperature,
  maxTokens, setMaxTokens, activeProvider, activeModel,
  ollamaModels, ollamaLoading, ollamaError, fetchOllamaModels,
  presets, applyPreset, presetsRef, highlightPresets,
  setHighlightPresets, handleSave, handleDisconnect,
  getProviderDisplayName,
}) {
  const labelStyle = {
    fontSize: 13,
    color: 'var(--text-muted)',
    marginBottom: 6,
    display: 'block',
    fontWeight: 500,
  }

  const inputStyle = {
    width: '100%',
    padding: '10px 14px',
    background: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--text-primary)',
    fontSize: 13,
    outline: 'none',
    fontFamily: 'inherit',
  }

  const btnStyle = {
    width: '100%',
    padding: '12px',
    borderRadius: 10,
    background: '#4f46e5',
    border: 'none',
    color: 'white',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    opacity: saving ? 0.6 : 1,
    transition: 'all 0.2s',
  }

  return (
    <>
      {/* Status banner */}
      <div style={{
        padding: '10px 14px', borderRadius: 8, marginBottom: 20,
        background: configured ? (isDark ? 'rgba(34,197,94,0.12)' : '#ecfdf5') : (isDark ? 'rgba(245,158,11,0.12)' : '#fffbeb'),
        border: `1px solid ${configured ? (isDark ? 'rgba(34,197,94,0.25)' : '#a7f3d0') : (isDark ? 'rgba(245,158,11,0.25)' : '#fde68a')}`,
        fontSize: 13, color: configured ? 'var(--text-primary)' : (isDark ? '#fbbf24' : '#d97706'),
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
      }}>
        <span style={{ flex: 1, minWidth: 0 }}>
          {configured
            ? `✅ 已连接 ${getProviderDisplayName(activeProvider, activeModel)}`
            : '⚠️ 未配置 — Agent 使用 Mock 回复'}
        </span>
        {configured && (
          <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
            <button onClick={handleDisconnect} disabled={saving} style={{
              padding: '4px 10px', borderRadius: 6, fontSize: 11,
              background: 'var(--bg-secondary)', border: `1px solid ${isDark ? 'rgba(34,197,94,0.25)' : '#a7f3d0'}`,
              color: '#059669', cursor: 'pointer', fontWeight: 500,
              whiteSpace: 'nowrap',
            }}>断开接入</button>
            <button onClick={() => {
              setHighlightPresets(true)
              presetsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
              setTimeout(() => setHighlightPresets(false), 1500)
            }} style={{
              padding: '4px 10px', borderRadius: 6, fontSize: 11,
              background: '#059669', border: '1px solid #059669',
              color: 'white', cursor: 'pointer', fontWeight: 500,
              whiteSpace: 'nowrap',
            }}>切换 LLM</button>
          </div>
        )}
      </div>

      {/* Presets */}
      <div ref={presetsRef} style={{
        marginBottom: 20, padding: highlightPresets ? '8px' : 0,
        borderRadius: 8,
        background: highlightPresets ? (isDark ? 'rgba(34,197,94,0.12)' : '#ecfdf5') : 'transparent',
        border: highlightPresets ? `1px solid ${isDark ? 'rgba(34,197,94,0.25)' : '#a7f3d0'}` : '1px solid transparent',
        transition: 'all 0.3s',
      }}>
        <label style={labelStyle}>快速选择</label>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {presets.map((p) => (
            <button key={p.label} onClick={() => applyPreset(p)} style={{
              padding: '6px 12px', borderRadius: 6, fontSize: 12,
              background: isDark ? 'rgba(99,102,241,0.12)' : '#eef2ff', border: `1px solid ${isDark ? 'rgba(99,102,241,0.25)' : '#c7d2fe'}`,
              color: '#4f46e5', cursor: 'pointer',
            }}>{p.label}</button>
          ))}
        </div>
      </div>

      {/* Provider */}
      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>接口格式</label>
        <div style={{ display: 'flex', gap: 8 }}>
          {['openai', 'anthropic', 'ollama'].map((p) => (
            <button key={p} onClick={() => {
              setProvider(p);
              if (p === 'ollama') {
                setBaseUrl('http://127.0.0.1:11434/v1');
              }
            }} style={{
              flex: 1, padding: '10px', borderRadius: 8, fontSize: 13,
              background: provider === p ? '#4f46e5' : 'var(--bg-secondary)',
              border: `1px solid ${provider === p ? '#4f46e5' : 'var(--border)'}`,
              color: provider === p ? 'white' : 'var(--text-muted)',
              cursor: 'pointer', fontWeight: provider === p ? 600 : 400,
            }}>
              {p === 'openai' ? 'OpenAI 兼容' : p === 'anthropic' ? 'Anthropic' : 'Ollama 本地'}
            </button>
          ))}
        </div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>API 地址</label>
        <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="https://api.example.com/v1" style={inputStyle} />
      </div>
      <div style={{ marginBottom: 16 }}>
        <label style={labelStyle}>模型名称</label>
        {provider === 'ollama' ? (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {ollamaModels.length > 0 ? (
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                style={{ ...inputStyle, flex: 1 }}
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
                style={{ ...inputStyle, flex: 1 }}
              />
            )}
            <button
              onClick={(e) => { e.preventDefault(); fetchOllamaModels(); }}
              disabled={ollamaLoading}
              style={{
                padding: '10px 14px',
                background: isDark ? 'rgba(99,102,241,0.12)' : '#eef2ff',
                border: `1px solid ${isDark ? 'rgba(99,102,241,0.25)' : '#c7d2fe'}`,
                color: '#4f46e5',
                borderRadius: 8,
                cursor: 'pointer',
                fontSize: 12,
                display: 'flex',
                alignItems: 'center',
                gap: 4
              }}
            >
              {ollamaLoading ? '🔄' : '🔄 刷新'}
            </button>
          </div>
        ) : (
          <input value={model} onChange={(e) => setModel(e.target.value)}
            placeholder="model-name" style={inputStyle} />
        )}
        {provider === 'ollama' && ollamaError && (
          <div style={{ marginTop: 6, fontSize: 11, color: isDark ? '#fbbf24' : '#d97706' }}>
            ⚠️ {ollamaError}
          </div>
        )}
      </div>
      {provider !== 'ollama' && (
        <div style={{ marginBottom: 16 }}>
          <label style={labelStyle}>API Key</label>
          <input value={apiKey} onChange={(e) => setApiKey(e.target.value)}
            type="password" placeholder="sk-..." style={inputStyle} />
        </div>
      )}

      {/* Temperature & Max Tokens */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Temperature: {temperature}</label>
          <input type="range" min="0" max="1" step="0.1" value={temperature}
            onChange={(e) => setTemperature(parseFloat(e.target.value))}
            style={{ width: '100%', accentColor: '#4f46e5' }} />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)' }}>
            <span>精确</span><span>创意</span>
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <label style={labelStyle}>Max Tokens</label>
          <input type="number" value={maxTokens}
            onChange={(e) => setMaxTokens(parseInt(e.target.value) || 4096)}
            style={inputStyle} />
        </div>
      </div>

      <button onClick={handleSave} disabled={saving} style={btnStyle}>
        {saving ? '保存中...' : '保存配置'}
      </button>
    </>
  )
}
