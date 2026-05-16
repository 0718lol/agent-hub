import React, { useState, useEffect } from 'react'

export default function SettingsPanel({ onClose }) {
  const [provider, setProvider] = useState('openai')
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [configured, setConfigured] = useState(false)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    fetch('/api/settings/llm')
      .then((r) => r.json())
      .then((d) => {
        setProvider(d.provider || 'openai')
        setBaseUrl(d.base_url || '')
        setModel(d.model || '')
        setConfigured(d.configured)
      })
      .catch(() => {})
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setMsg('')
    try {
      const resp = await fetch('/api/settings/llm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, api_key: apiKey, base_url: baseUrl, model }),
      })
      const d = await resp.json()
      setConfigured(d.configured)
      setMsg(d.configured ? '配置成功！Agent 现在会使用真实 LLM 回复' : '请填写完整信息')
      if (d.configured) setApiKey('')
    } catch {
      setMsg('保存失败，请检查后端是否运行')
    }
    setSaving(false)
  }

  const presets = [
    { label: '小米 MiLM', provider: 'openai', base_url: 'https://api.milm.mi.com/v1', model: 'milm-large' },
    { label: 'DeepSeek', provider: 'openai', base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
    { label: '通义千问', provider: 'openai', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-turbo' },
    { label: 'OpenAI', provider: 'openai', base_url: 'https://api.openai.com/v1', model: 'gpt-4o' },
    { label: 'Claude', provider: 'anthropic', base_url: 'https://api.anthropic.com/v1', model: 'claude-sonnet-4-20250514' },
  ]

  const applyPreset = (p) => {
    setProvider(p.provider)
    setBaseUrl(p.base_url)
    setModel(p.model)
  }

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000,
    }} onClick={onClose}>
      <div style={{
        width: 440, maxHeight: '85vh', overflow: 'auto',
        background: '#1e293b', border: '1px solid rgba(255,255,255,0.1)',
        borderRadius: 16, padding: 28,
      }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <h2 style={{ margin: 0, fontSize: 18, color: '#f8fafc' }}>LLM 接口配置</h2>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: '#64748b',
            fontSize: 20, cursor: 'pointer', padding: '0 4px',
          }}>×</button>
        </div>

        {/* Status */}
        <div style={{
          padding: '10px 14px', borderRadius: 8, marginBottom: 20,
          background: configured ? 'rgba(16,185,129,0.1)' : 'rgba(251,191,36,0.1)',
          border: `1px solid ${configured ? 'rgba(16,185,129,0.2)' : 'rgba(251,191,36,0.2)'}`,
          fontSize: 13, color: configured ? '#10b981' : '#fbbf24',
        }}>
          {configured ? '✅ 已连接 LLM — Agent 使用真实模型回复' : '⚠️ 未配置 — Agent 使用 Mock 回复'}
        </div>

        {/* Presets */}
        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: 13, color: '#94a3b8', marginBottom: 8, display: 'block' }}>快速选择</label>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {presets.map((p) => (
              <button key={p.label} onClick={() => applyPreset(p)} style={{
                padding: '6px 12px', borderRadius: 6, fontSize: 12,
                background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)',
                color: '#a5b4fc', cursor: 'pointer', transition: 'all 0.2s',
              }}>{p.label}</button>
            ))}
          </div>
        </div>

        {/* Provider */}
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 13, color: '#94a3b8', marginBottom: 6, display: 'block' }}>接口格式</label>
          <div style={{ display: 'flex', gap: 8 }}>
            {['openai', 'anthropic'].map((p) => (
              <button key={p} onClick={() => setProvider(p)} style={{
                flex: 1, padding: '10px', borderRadius: 8, fontSize: 13,
                background: provider === p ? '#6366f1' : 'rgba(255,255,255,0.04)',
                border: `1px solid ${provider === p ? '#6366f1' : 'rgba(255,255,255,0.1)'}`,
                color: provider === p ? 'white' : '#94a3b8',
                cursor: 'pointer', fontWeight: provider === p ? 600 : 400,
              }}>
                {p === 'openai' ? 'OpenAI 兼容' : 'Anthropic'}
              </button>
            ))}
          </div>
        </div>

        {/* Base URL */}
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 13, color: '#94a3b8', marginBottom: 6, display: 'block' }}>API 地址</label>
          <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://api.example.com/v1"
            style={inputStyle} />
        </div>

        {/* Model */}
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 13, color: '#94a3b8', marginBottom: 6, display: 'block' }}>模型名称</label>
          <input value={model} onChange={(e) => setModel(e.target.value)}
            placeholder="model-name"
            style={inputStyle} />
        </div>

        {/* API Key */}
        <div style={{ marginBottom: 20 }}>
          <label style={{ fontSize: 13, color: '#94a3b8', marginBottom: 6, display: 'block' }}>API Key</label>
          <input value={apiKey} onChange={(e) => setApiKey(e.target.value)}
            type="password" placeholder="sk-..."
            style={inputStyle} />
        </div>

        {/* Save */}
        <button onClick={handleSave} disabled={saving} style={{
          width: '100%', padding: '12px', borderRadius: 10,
          background: '#6366f1', border: 'none', color: 'white',
          fontSize: 14, fontWeight: 600, cursor: saving ? 'not-allowed' : 'pointer',
          opacity: saving ? 0.6 : 1, transition: 'all 0.2s',
        }}>
          {saving ? '保存中...' : '保存配置'}
        </button>

        {msg && (
          <div style={{
            marginTop: 12, padding: '10px 14px', borderRadius: 8,
            background: msg.includes('成功') ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
            border: `1px solid ${msg.includes('成功') ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}`,
            fontSize: 13, color: msg.includes('成功') ? '#10b981' : '#ef4444',
          }}>{msg}</div>
        )}
      </div>
    </div>
  )
}

const inputStyle = {
  width: '100%', padding: '10px 14px',
  background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: 8, color: '#f8fafc', fontSize: 13, outline: 'none',
  fontFamily: 'inherit',
}
