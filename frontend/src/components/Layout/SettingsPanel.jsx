import React, { useState, useEffect } from 'react'
import { Bot, Target, Ruler, CheckCircle, AlertTriangle } from 'lucide-react'

export default function SettingsPanel({ onClose }) {
  const [tab, setTab] = useState('llm') // 'llm' | 'quality' | 'prompt'
  const [provider, setProvider] = useState('openai')
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [temperature, setTemperature] = useState(0.5)
  const [maxTokens, setMaxTokens] = useState(8192)
  const [configured, setConfigured] = useState(false)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  // Quality gate state
  const [qEnabled, setQEnabled] = useState(true)
  const [bestOfN, setBestOfN] = useState(1)
  const [maxRetries, setMaxRetries] = useState(1)
  const [useLlmJudge, setUseLlmJudge] = useState(false)

  // Prompt layers state
  const [layers, setLayers] = useState([])

  useEffect(() => {
    fetch('/api/settings/llm')
      .then((r) => r.json())
      .then((d) => {
        setProvider(d.provider || 'openai')
        setBaseUrl(d.base_url || '')
        setModel(d.model || '')
        setTemperature(d.temperature ?? 0.5)
        setMaxTokens(d.max_tokens ?? 8192)
        setConfigured(d.configured)
      })
      .catch(() => {})
    fetch('/api/settings/quality')
      .then((r) => r.json())
      .then((d) => {
        setQEnabled(d.enabled ?? true)
        setBestOfN(d.best_of_n ?? 1)
        setMaxRetries(d.max_retries ?? 1)
        setUseLlmJudge(d.use_llm_judge ?? false)
      })
      .catch(() => {})
    fetch('/api/prompt/layers')
      .then((r) => r.json())
      .then((d) => setLayers(d || []))
      .catch(() => {})
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setMsg('')
    try {
      const resp = await fetch('/api/settings/llm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, api_key: apiKey, base_url: baseUrl, model, temperature, max_tokens: maxTokens }),
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

  const handleSaveQuality = async () => {
    setSaving(true)
    setMsg('')
    try {
      await fetch('/api/settings/quality', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: qEnabled, best_of_n: bestOfN, max_retries: maxRetries, use_llm_judge: useLlmJudge }),
      })
      setMsg('质量门配置已保存')
    } catch {
      setMsg('保存失败')
    }
    setSaving(false)
  }

  const toggleLayer = async (layerId, enabled) => {
    try {
      await fetch(`/api/prompt/layers/${layerId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
      setLayers((prev) => prev.map((l) => l.id === layerId ? { ...l, enabled } : l))
    } catch {}
  }

  const presets = [
    { label: '小米 MiLM', provider: 'openai', base_url: 'https://token-plan-cn.xiaomimimo.com/v1', model: 'mimo-v2.5' },
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

  const tabIcons = {
    llm: <Bot size={16} />,
    quality: <Target size={16} />,
    prompt: <Ruler size={16} />,
  }

  const tabs = [
    { id: 'llm', label: 'LLM 模型' },
    { id: 'quality', label: '质量门' },
    { id: 'prompt', label: 'Prompt 分层' },
  ]

  const labelStyle = {
    fontSize: 13,
    color: '#94a3b8',
    marginBottom: 6,
    display: 'block',
  }

  const rowStyle = {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px 14px',
    borderRadius: 10,
    background: 'rgba(255,255,255,0.03)',
    border: '1px solid rgba(255,255,255,0.08)',
  }

  const btnStyle = {
    width: '100%',
    padding: '12px',
    borderRadius: 10,
    background: '#6366f1',
    border: 'none',
    color: 'white',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    opacity: saving ? 0.6 : 1,
    transition: 'all 0.2s',
  }

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000,
    }} onClick={onClose}>
      <div style={{
        width: 500, maxHeight: '88vh', overflow: 'auto',
        background: '#1e293b', border: '1px solid rgba(255,255,255,0.1)',
        borderRadius: 16, padding: 28,
      }} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 18, color: '#f8fafc' }}>设置</h2>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: '#64748b',
            fontSize: 20, cursor: 'pointer', padding: '0 4px',
          }}>×</button>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 24, background: 'rgba(0,0,0,0.2)', borderRadius: 10, padding: 4 }}>
          {tabs.map((t) => (
            <button key={t.id} onClick={() => { setTab(t.id); setMsg('') }} style={{
              flex: 1, padding: '8px 12px', borderRadius: 8, fontSize: 12,
              background: tab === t.id ? '#6366f1' : 'transparent',
              border: 'none', color: tab === t.id ? 'white' : '#94a3b8',
              cursor: 'pointer', fontWeight: tab === t.id ? 600 : 400,
              transition: 'all 0.2s',
            }}><span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>{tabIcons[t.id]}{t.label}</span></button>
          ))}
        </div>

        {/* ====== TAB: LLM ====== */}
        {tab === 'llm' && (
          <>
            <div style={{
              padding: '10px 14px', borderRadius: 8, marginBottom: 20,
              background: configured ? 'rgba(16,185,129,0.1)' : 'rgba(251,191,36,0.1)',
              border: `1px solid ${configured ? 'rgba(16,185,129,0.2)' : 'rgba(251,191,36,0.2)'}`,
              fontSize: 13, color: configured ? '#10b981' : '#fbbf24',
            }}>
              {configured ? <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><CheckCircle size={14} color="#10b981" style={{ flexShrink: 0 }} /> 已连接 LLM — Agent 使用真实模型回复</span> : <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><AlertTriangle size={14} color="#fbbf24" style={{ flexShrink: 0 }} /> 未配置 — Agent 使用 Mock 回复</span>}
            </div>

            {/* Presets */}
            <div style={{ marginBottom: 20 }}>
              <label style={labelStyle}>快速选择</label>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {presets.map((p) => (
                  <button key={p.label} onClick={() => applyPreset(p)} style={{
                    padding: '6px 12px', borderRadius: 6, fontSize: 12,
                    background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)',
                    color: '#a5b4fc', cursor: 'pointer',
                  }}>{p.label}</button>
                ))}
              </div>
            </div>

            {/* Provider */}
            <div style={{ marginBottom: 16 }}>
              <label style={labelStyle}>接口格式</label>
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

            <div style={{ marginBottom: 16 }}>
              <label style={labelStyle}>API 地址</label>
              <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.example.com/v1" style={inputStyle} />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={labelStyle}>模型名称</label>
              <input value={model} onChange={(e) => setModel(e.target.value)}
                placeholder="model-name" style={inputStyle} />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={labelStyle}>API Key</label>
              <input value={apiKey} onChange={(e) => setApiKey(e.target.value)}
                type="password" placeholder="sk-..." style={inputStyle} />
            </div>

            {/* Temperature & Max Tokens */}
            <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
              <div style={{ flex: 1 }}>
                <label style={labelStyle}>Temperature: {temperature}</label>
                <input type="range" min="0" max="1" step="0.1" value={temperature}
                  onChange={(e) => setTemperature(parseFloat(e.target.value))}
                  style={{ width: '100%', accentColor: '#6366f1' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#64748b' }}>
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
        )}

        {/* ====== TAB: Quality Gate ====== */}
        {tab === 'quality' && (
          <>
            <div style={{ padding: '12px 14px', borderRadius: 8, marginBottom: 20, background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)', fontSize: 12, color: '#a5b4fc' }}>
              质量门会自动评估 Agent 输出，不达标时触发重写或择优选择
            </div>

            {/* Enable toggle */}
            <div style={{ ...rowStyle, marginBottom: 16 }}>
              <div>
                <div style={{ fontSize: 14, color: '#f8fafc' }}>启用质量门</div>
                <div style={{ fontSize: 12, color: '#64748b' }}>关闭后 Agent 直接输出不评估</div>
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
                    background: bestOfN === n ? '#6366f1' : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${bestOfN === n ? '#6366f1' : 'rgba(255,255,255,0.1)'}`,
                    color: bestOfN === n ? 'white' : '#94a3b8',
                    cursor: 'pointer', fontWeight: bestOfN === n ? 600 : 400,
                  }}>
                    {n === 1 ? '关闭' : `${n} 候选`}
                  </button>
                ))}
              </div>
              {bestOfN > 1 && (
                <div style={{ marginTop: 6, fontSize: 11, color: '#fbbf24' }}>
                  <AlertTriangle size={12} color="#fbbf24" style={{ verticalAlign: 'middle', marginRight: 2, flexShrink: 0 }} /> 将消耗 {bestOfN}x Token，适合高质量关键输出
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
                    background: maxRetries === n ? '#6366f1' : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${maxRetries === n ? '#6366f1' : 'rgba(255,255,255,0.1)'}`,
                    color: maxRetries === n ? 'white' : '#94a3b8',
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
                <div style={{ fontSize: 14, color: '#f8fafc' }}>LLM 深度评审</div>
                <div style={{ fontSize: 12, color: '#64748b' }}>用 LLM 做语义级质量评分（额外消耗 Token）</div>
              </div>
              <ToggleSwitch checked={useLlmJudge} onChange={setUseLlmJudge} />
            </div>

            <button onClick={handleSaveQuality} disabled={saving} style={btnStyle}>
              {saving ? '保存中...' : '保存质量门配置'}
            </button>
          </>
        )}

        {/* ====== TAB: Prompt Layers ====== */}
        {tab === 'prompt' && (
          <>
            <div style={{ padding: '12px 14px', borderRadius: 8, marginBottom: 20, background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)', fontSize: 12, color: '#a5b4fc' }}>
              Prompt 按层级注入，每层可独立开关。高层级（约束）优先级最高。
            </div>

            {layers.map((layer) => (
              <div key={layer.id} style={{
                ...rowStyle,
                marginBottom: 10, padding: '12px 14px', borderRadius: 10,
                background: layer.enabled ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.2)',
                border: `1px solid ${layer.enabled ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.04)'}`,
                opacity: layer.enabled ? 1 : 0.5,
              }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, color: '#f8fafc', fontWeight: 500 }}>
                    <span style={{ fontSize: 11, color: '#6366f1', marginRight: 6 }}>L{layer.level}</span>
                    {layer.id}
                    {layer.has_condition && <span style={{ fontSize: 10, color: '#fbbf24', marginLeft: 6 }}>条件注入</span>}
                  </div>
                  <div style={{ fontSize: 11, color: '#64748b', marginTop: 3 }}>
                    {layer.content_preview}
                  </div>
                </div>
                <ToggleSwitch checked={layer.enabled} onChange={(v) => toggleLayer(layer.id, v)} />
              </div>
            ))}
          </>
        )}

        {/* Message */}
        {msg && (
          <div style={{
            marginTop: 16, padding: '10px 14px', borderRadius: 8,
            background: msg.includes('成功') || msg.includes('已保存') ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
            border: `1px solid ${msg.includes('成功') || msg.includes('已保存') ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}`,
            fontSize: 13, color: msg.includes('成功') || msg.includes('已保存') ? '#10b981' : '#ef4444',
          }}>{msg}</div>
        )}
      </div>
    </div>
  )
}

function ToggleSwitch({ checked, onChange }) {
  return (
    <div onClick={() => onChange(!checked)} style={{
      width: 44, height: 24, borderRadius: 12, cursor: 'pointer',
      background: checked ? '#6366f1' : 'rgba(255,255,255,0.1)',
      border: `1px solid ${checked ? '#6366f1' : 'rgba(255,255,255,0.15)'}`,
      position: 'relative', transition: 'all 0.2s', flexShrink: 0,
    }}>
      <div style={{
        width: 18, height: 18, borderRadius: 9,
        background: 'white', position: 'absolute', top: 2,
        left: checked ? 22 : 3, transition: 'left 0.2s',
      }} />
    </div>
  )
}

const inputStyle = {
  width: '100%', padding: '10px 14px',
  background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: 8, color: '#f8fafc', fontSize: 13, outline: 'none',
  fontFamily: 'inherit',
}
