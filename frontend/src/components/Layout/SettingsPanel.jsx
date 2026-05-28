import React, { useState, useEffect } from 'react'

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

  // Ollama integration states
  const [ollamaModels, setOllamaModels] = useState([])
  const [ollamaLoading, setOllamaLoading] = useState(false)
  const [ollamaError, setOllamaError] = useState('')

  const fetchOllamaModels = () => {
    setOllamaLoading(true)
    setOllamaError('')
    fetch('/api/ollama/models')
      .then((r) => r.json())
      .then((d) => {
        if (d.status === 'ok') {
          setOllamaModels(d.models || [])
          if (d.models && d.models.length > 0) {
            if (!model || !d.models.includes(model)) {
              setModel(d.models[0])
            }
          } else {
            setOllamaError('未在本地 Ollama 中发现已下载的模型，请先运行 "ollama run <model>"')
          }
        } else {
          setOllamaError(d.message || '无法获取本地模型列表')
        }
      })
      .catch(() => {
        setOllamaError('无法连接到后端或本地 Ollama 服务没有运行')
      })
      .finally(() => {
        setOllamaLoading(false)
      })
  }

  useEffect(() => {
    if (provider === 'ollama') {
      fetchOllamaModels()
    }
  }, [provider])

  // Quality gate state
  const [qEnabled, setQEnabled] = useState(true)
  const [bestOfN, setBestOfN] = useState(1)
  const [maxRetries, setMaxRetries] = useState(1)
  const [useLlmJudge, setUseLlmJudge] = useState(false)

  // Prompt layers state
  const [layers, setLayers] = useState([])

  // Cron tasks state
  const [cronTasks, setCronTasks] = useState([])
  const [cronLoading, setCronLoading] = useState(false)
  const [selectedAgentForCron, setSelectedAgentForCron] = useState('agent_pm')
  const [cronPrompt, setCronPrompt] = useState('检查工作区，寻找安全漏洞并重构代码，完毕后运行编译测试并生成 checkpoint 版本。')
  const [cronInterval, setCronInterval] = useState(60)

  const fetchCronTasks = async () => {
    setCronLoading(true)
    try {
      const resp = await fetch('/api/cron')
      const d = await resp.json()
      if (d.status === 'ok') setCronTasks(d.tasks || [])
    } catch (e) {
      console.error("Failed to fetch cron tasks:", e)
    }
    setCronLoading(false)
  }

  const handleAddCronTask = async () => {
    if (!cronPrompt.trim()) return
    setSaving(true)
    setMsg('')
    try {
      const resp = await fetch('/api/cron', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: 'conv_pm',
          agent_id: selectedAgentForCron,
          task_prompt: cronPrompt,
          interval_seconds: cronInterval
        })
      })
      const d = await resp.json()
      if (d.status === 'ok') {
        setMsg('离线自治任务成功创建！')
        setCronPrompt('检查工作区，寻找安全漏洞并重构代码，完毕后运行编译测试并生成 checkpoint 版本。')
        fetchCronTasks()
      } else {
        setMsg('创建失败：' + d.message)
      }
    } catch {
      setMsg('创建失败，请检查后端')
    }
    setSaving(false)
  }

  const handleToggleCronTask = async (taskId, currentStatus) => {
    setSaving(true)
    try {
      const newStatus = currentStatus === 'active' ? 'paused' : 'active'
      await fetch(`/api/cron/${taskId}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
      })
      fetchCronTasks()
    } catch {}
    setSaving(false)
  }

  const handleRunCronTaskNow = async (taskId) => {
    setSaving(true)
    try {
      const resp = await fetch(`/api/cron/${taskId}/run`, { method: 'POST' })
      const d = await resp.json()
      if (d.status === 'ok') setMsg(d.message)
      fetchCronTasks()
    } catch {}
    setSaving(false)
  }

  const handleDeleteCronTask = async (taskId) => {
    setSaving(true)
    try {
      await fetch(`/api/cron/${taskId}`, { method: 'DELETE' })
      fetchCronTasks()
    } catch {}
    setSaving(false)
  }

  useEffect(() => {
    if (tab === 'cron') fetchCronTasks()
  }, [tab])

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
        body: JSON.stringify({ provider, api_key: provider === 'ollama' ? 'ollama' : apiKey, base_url: baseUrl, model, temperature, max_tokens: maxTokens }),
      })
      const d = await resp.json()
      setConfigured(d.configured)
      setMsg(d.configured ? '配置成功！Agent 现在会使用真实 LLM 回复' : '请填写完整信息')
      if (d.configured && provider !== 'ollama') setApiKey('')
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
    { label: 'Ollama 本地', provider: 'ollama', base_url: 'http://127.0.0.1:11434/v1', model: '' },
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

  const tabs = [
    { id: 'llm', label: 'LLM 模型' },
    { id: 'quality', label: '质量门' },
    { id: 'prompt', label: 'Prompt 分层' },
    { id: 'cron', label: '📅 自治' },
  ]

  // Light theme styles
  const labelStyle = {
    fontSize: 13,
    color: '#6b7280',
    marginBottom: 6,
    display: 'block',
    fontWeight: 500,
  }

  const rowStyle = {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '12px 14px',
    borderRadius: 10,
    background: '#f9fafb',
    border: '1px solid #e5e7eb',
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

  const inputStyle = {
    width: '100%',
    padding: '10px 14px',
    background: 'white',
    border: '1px solid #d1d5db',
    borderRadius: 8,
    color: '#1f2937',
    fontSize: 13,
    outline: 'none',
    fontFamily: 'inherit',
  }

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.3)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 1000,
    }} onClick={onClose}>
      <div style={{
        width: 500, maxHeight: '88vh', overflow: 'auto',
        background: 'white',
        border: '1px solid #e5e7eb',
        borderRadius: 16, padding: 28,
        boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
      }} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 18, color: '#1f2937', fontWeight: 600 }}>设置</h2>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: '#9ca3af',
            fontSize: 20, cursor: 'pointer', padding: '0 4px',
          }}>×</button>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 24, background: '#f3f4f6', borderRadius: 10, padding: 4 }}>
          {tabs.map((t) => (
            <button key={t.id} onClick={() => { setTab(t.id); setMsg('') }} style={{
              flex: 1, padding: '8px 12px', borderRadius: 8, fontSize: 12,
              background: tab === t.id ? '#4f46e5' : 'transparent',
              border: 'none', color: tab === t.id ? 'white' : '#6b7280',
              cursor: 'pointer', fontWeight: tab === t.id ? 600 : 400,
              transition: 'all 0.2s',
            }}>{t.label}</button>
          ))}
        </div>

        {/* ====== TAB: LLM ====== */}
        {tab === 'llm' && (
          <>
            <div style={{
              padding: '10px 14px', borderRadius: 8, marginBottom: 20,
              background: configured ? '#ecfdf5' : '#fffbeb',
              border: `1px solid ${configured ? '#a7f3d0' : '#fde68a'}`,
              fontSize: 13, color: configured ? '#059669' : '#d97706',
            }}>
              {configured ? '✅ 已连接 LLM — Agent 使用真实模型回复' : '⚠️ 未配置 — Agent 使用 Mock 回复'}
            </div>

            {/* Presets */}
            <div style={{ marginBottom: 20 }}>
              <label style={labelStyle}>快速选择</label>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {presets.map((p) => (
                  <button key={p.label} onClick={() => applyPreset(p)} style={{
                    padding: '6px 12px', borderRadius: 6, fontSize: 12,
                    background: '#eef2ff', border: '1px solid #c7d2fe',
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
                    background: provider === p ? '#4f46e5' : '#f9fafb',
                    border: `1px solid ${provider === p ? '#4f46e5' : '#e5e7eb'}`,
                    color: provider === p ? 'white' : '#6b7280',
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
                      background: '#eef2ff',
                      border: '1px solid #c7d2fe',
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
                <div style={{ marginTop: 6, fontSize: 11, color: '#d97706' }}>
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
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#9ca3af' }}>
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
            <div style={{ padding: '12px 14px', borderRadius: 8, marginBottom: 20, background: '#eef2ff', border: '1px solid #c7d2fe', fontSize: 12, color: '#4f46e5' }}>
              质量门会自动评估 Agent 输出，不达标时触发重写或择优选择
            </div>

            {/* Enable toggle */}
            <div style={{ ...rowStyle, marginBottom: 16 }}>
              <div>
                <div style={{ fontSize: 14, color: '#1f2937', fontWeight: 500 }}>启用质量门</div>
                <div style={{ fontSize: 12, color: '#9ca3af' }}>关闭后 Agent 直接输出不评估</div>
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
                    background: bestOfN === n ? '#4f46e5' : '#f9fafb',
                    border: `1px solid ${bestOfN === n ? '#4f46e5' : '#e5e7eb'}`,
                    color: bestOfN === n ? 'white' : '#6b7280',
                    cursor: 'pointer', fontWeight: bestOfN === n ? 600 : 400,
                  }}>
                    {n === 1 ? '关闭' : `${n} 候选`}
                  </button>
                ))}
              </div>
              {bestOfN > 1 && (
                <div style={{ marginTop: 6, fontSize: 11, color: '#d97706' }}>
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
                    background: maxRetries === n ? '#4f46e5' : '#f9fafb',
                    border: `1px solid ${maxRetries === n ? '#4f46e5' : '#e5e7eb'}`,
                    color: maxRetries === n ? 'white' : '#6b7280',
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
                <div style={{ fontSize: 14, color: '#1f2937', fontWeight: 500 }}>LLM 深度评审</div>
                <div style={{ fontSize: 12, color: '#9ca3af' }}>用 LLM 做语义级质量评分（额外消耗 Token）</div>
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
            <div style={{ padding: '12px 14px', borderRadius: 8, marginBottom: 20, background: '#eef2ff', border: '1px solid #c7d2fe', fontSize: 12, color: '#4f46e5' }}>
              Prompt 按层级注入，每层可独立开关。高层级（约束）优先级最高。
            </div>

            {layers.map((layer) => (
              <div key={layer.id} style={{
                ...rowStyle,
                marginBottom: 10, padding: '12px 14px', borderRadius: 10,
                background: layer.enabled ? '#f9fafb' : '#f3f4f6',
                border: `1px solid ${layer.enabled ? '#e5e7eb' : '#e5e7eb'}`,
                opacity: layer.enabled ? 1 : 0.5,
              }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, color: '#1f2937', fontWeight: 500 }}>
                    <span style={{ fontSize: 11, color: '#4f46e5', marginRight: 6 }}>L{layer.level}</span>
                    {layer.id}
                    {layer.has_condition && <span style={{ fontSize: 10, color: '#d97706', marginLeft: 6 }}>条件注入</span>}
                  </div>
                  <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 3 }}>
                    {layer.content_preview}
                  </div>
                </div>
                <ToggleSwitch checked={layer.enabled} onChange={(v) => toggleLayer(layer.id, v)} />
              </div>
            ))}
          </>
        )}

        {/* ====== TAB: Offline Cron Autonomous Tasks ====== */}
        {tab === 'cron' && (
          <>
            <div style={{
              padding: '10px 14px', borderRadius: 8, marginBottom: 20,
              background: '#eef2ff', border: '1px solid #c7d2fe',
              fontSize: 13, color: '#4338ca', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
              <span>Always-on 离线常驻自治 — 网页关闭后 Agent 仍能后台自主开发</span>
              <button onClick={fetchCronTasks} disabled={cronLoading} style={{
                padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                background: '#4f46e5', color: 'white', border: 'none', cursor: 'pointer',
                opacity: cronLoading ? 0.6 : 1,
              }}>{cronLoading ? '...' : '刷新'}</button>
            </div>

            {/* Task List */}
            <div style={{ marginBottom: 20 }}>
              <label style={labelStyle}>当前后台自治作业</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: '25vh', overflowY: 'auto' }}>
                {cronTasks.length === 0 ? (
                  <div style={{ textAlign: 'center', color: '#9ca3af', padding: '16px 0', fontSize: 12 }}>
                    暂无活动中的后台自治作业
                  </div>
                ) : (
                  cronTasks.map((t) => (
                    <div key={t.id} style={{
                      padding: '10px 14px', borderRadius: 10, background: '#f9fafb',
                      border: `1px solid ${t.status === 'running' ? '#a78bfa' : t.status === 'active' ? '#a7f3d0' : '#fde68a'}`,
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: '#1f2937' }}>
                          {t.status === 'running' ? '🔵' : t.status === 'active' ? '🟢' : '🟡'} {t.agent_id}
                        </span>
                        <span style={{ fontSize: 10, color: '#6b7280' }}>每 {t.interval_seconds}s</span>
                      </div>
                      <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 8 }}>{t.task_prompt.slice(0, 60)}...</div>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button onClick={() => handleToggleCronTask(t.id, t.status)} disabled={saving} style={{
                          padding: '3px 8px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
                          background: '#f3f4f6', border: '1px solid #d1d5db', color: '#374151',
                        }}>{t.status === 'active' ? '暂停' : '恢复'}</button>
                        <button onClick={() => handleRunCronTaskNow(t.id)} disabled={saving || t.status === 'running'} style={{
                          padding: '3px 8px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
                          background: '#eef2ff', border: '1px solid #c7d2fe', color: '#4338ca',
                        }}>立即执行</button>
                        <button onClick={() => handleDeleteCronTask(t.id)} disabled={saving} style={{
                          padding: '3px 8px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
                          background: '#fef2f2', border: '1px solid #fecaca', color: '#dc2626',
                        }}>删除</button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Create Form */}
            <div style={{ padding: '16px', borderRadius: 12, background: '#f9fafb', border: '1px solid #e5e7eb' }}>
              <label style={{ ...labelStyle, fontWeight: 600, marginBottom: 12 }}>创建新离线自治任务</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{ display: 'flex', gap: 10 }}>
                  <div style={{ flex: 1 }}>
                    <label style={{ ...labelStyle, fontSize: 11 }}>执行 Agent</label>
                    <select value={selectedAgentForCron} onChange={(e) => setSelectedAgentForCron(e.target.value)} style={inputStyle}>
                      <option value="agent_pm">PM 小助手</option>
                      <option value="agent_frontend">前端工程师</option>
                      <option value="agent_backend">后端工程师</option>
                      <option value="agent_tester">测试工程师</option>
                      <option value="agent_devops">运维工程师</option>
                      <option value="agent_designer">设计顾问</option>
                    </select>
                  </div>
                  <div style={{ flex: 1 }}>
                    <label style={{ ...labelStyle, fontSize: 11 }}>自治周期</label>
                    <select value={cronInterval} onChange={(e) => setCronInterval(parseInt(e.target.value))} style={inputStyle}>
                      <option value={60}>每分钟 (自测)</option>
                      <option value={300}>每 5 分钟</option>
                      <option value={1800}>每 30 分钟</option>
                      <option value={3600}>每小时</option>
                      <option value={86400}>每日</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label style={{ ...labelStyle, fontSize: 11 }}>自治 Prompt 指令</label>
                  <textarea
                    value={cronPrompt}
                    onChange={(e) => setCronPrompt(e.target.value)}
                    rows={3}
                    style={{ ...inputStyle, resize: 'vertical', lineHeight: '1.5' }}
                    placeholder="输入分配给 Agent 的后台离线自治开发/检测指令..."
                  />
                </div>
                <button onClick={handleAddCronTask} disabled={saving || !cronPrompt.trim()} style={btnStyle}>
                  {saving ? '正在处理...' : '创建常驻离线自治任务'}
                </button>
              </div>
            </div>
          </>
        )}

        {/* Message */}
        {msg && (
          <div style={{
            marginTop: 16, padding: '10px 14px', borderRadius: 8,
            background: msg.includes('成功') || msg.includes('已保存') ? '#ecfdf5' : '#fef2f2',
            border: `1px solid ${msg.includes('成功') || msg.includes('已保存') ? '#a7f3d0' : '#fecaca'}`,
            fontSize: 13, color: msg.includes('成功') || msg.includes('已保存') ? '#059669' : '#dc2626',
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
      background: checked ? '#4f46e5' : '#d1d5db',
      border: `1px solid ${checked ? '#4f46e5' : '#d1d5db'}`,
      position: 'relative', transition: 'all 0.2s', flexShrink: 0,
    }}>
      <div style={{
        width: 18, height: 18, borderRadius: 9,
        background: 'white', position: 'absolute', top: 2,
        left: checked ? 22 : 3, transition: 'left 0.2s',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
      }} />
    </div>
  )
}
