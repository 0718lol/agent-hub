import React from 'react'
import { Loader } from 'lucide-react'
import { labelStyle, inputStyle, makeBtnStyle } from './sharedStyles'

export default function LLMTab({
  configured, activeProvider, activeModel, getProviderDisplayName,
  handleDisconnect, saving, setHighlightPresets, presetsRef, highlightPresets,
  presets, applyPreset, provider, setProvider, setBaseUrl,
  baseUrl, model, setModel, ollamaModels, ollamaLoading, fetchOllamaModels,
  ollamaError, apiKey, setApiKey, temperature, setTemperature,
  maxTokens, setMaxTokens, handleSave, handleTestLlm, testingLlm, llmTestMsg,
}) {
  const btnStyle = makeBtnStyle(saving)

  return (
    <>
      <div style={{
        padding: '10px 14px', borderRadius: 8, marginBottom: 20,
        background: configured ? 'rgba(16, 185, 129, 0.08)' : 'rgba(245, 158, 11, 0.08)',
        border: `1px solid ${configured ? 'rgba(16, 185, 129, 0.25)' : 'rgba(245, 158, 11, 0.2)'}`,
        fontSize: 13, color: configured ? 'var(--green)' : 'var(--orange)',
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
              background: 'var(--bg-primary)', border: '1px solid rgba(16, 185, 129, 0.25)',
              color: 'var(--green)', cursor: 'pointer', fontWeight: 500,
              whiteSpace: 'nowrap',
            }}>断开接入</button>
            <button onClick={() => {
              setHighlightPresets(true)
              presetsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
              setTimeout(() => setHighlightPresets(false), 1500)
            }} style={{
              padding: '4px 10px', borderRadius: 6, fontSize: 11,
              background: 'var(--green)', border: '1px solid var(--green)',
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
        background: highlightPresets ? 'rgba(16, 185, 129, 0.08)' : 'transparent',
        border: highlightPresets ? '1px solid rgba(16, 185, 129, 0.25)' : '1px solid transparent',
        transition: 'all 0.3s',
      }}>
        <label style={labelStyle}>快速选择</label>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {presets.map((p) => (
            <button key={p.label} onClick={() => applyPreset(p)} style={{
              padding: '6px 12px', borderRadius: 6, fontSize: 12,
              background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)',
              color: 'var(--accent)', cursor: 'pointer',
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
              background: provider === p ? 'var(--accent)' : 'var(--bg-secondary)',
              border: `1px solid ${provider === p ? 'var(--accent)' : 'var(--border)'}`,
              color: provider === p ? 'white' : 'var(--text-secondary)',
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
                background: 'rgba(99, 102, 241, 0.08)',
                border: '1px solid rgba(99, 102, 241, 0.25)',
                color: 'var(--accent)',
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
          <div style={{ marginTop: 6, fontSize: 11, color: 'var(--orange)' }}>
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
            style={{ width: '100%', accentColor: 'var(--accent)' }} />
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

      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={handleSave} disabled={saving} style={{ ...btnStyle, flex: 1 }}>
          {saving ? '保存中...' : '保存配置'}
        </button>
        <button
          onClick={handleTestLlm}
          disabled={testingLlm}
          style={{
            padding: '12px 16px', borderRadius: 10, fontSize: 14, fontWeight: 600,
            background: 'var(--bg-secondary)', border: '1px solid var(--border)',
            color: 'var(--text-primary)', cursor: testingLlm ? 'default' : 'pointer',
            opacity: testingLlm ? 0.6 : 1, display: 'flex', alignItems: 'center', gap: 6,
            transition: 'all 0.2s',
          }}
        >
          {testingLlm ? <><Loader size={14} style={{ animation: 'spin 1s linear infinite' }} /> 测试中...</> : '测试连通'}
        </button>
      </div>
      {llmTestMsg && (
        <div style={{
          marginTop: 10, padding: '10px 14px', borderRadius: 8, fontSize: 13,
          background: llmTestMsg.success ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
          border: `1px solid ${llmTestMsg.success ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}`,
          color: llmTestMsg.success ? 'var(--green)' : 'var(--red)',
        }}>
          {llmTestMsg.success ? `✅ 连通成功: ${llmTestMsg.response}` : `❌ ${llmTestMsg.error}`}
        </div>
      )}
    </>
  )
}
