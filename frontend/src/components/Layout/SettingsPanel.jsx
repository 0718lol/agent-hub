import React, { useState, useEffect } from 'react'
import { useChatStore } from '../../stores/chatStore'

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

  // AI Memory console states
  const activeConversationId = useChatStore((s) => s.activeConversationId)
  const [projectMemory, setProjectMemory] = useState({})
  const [editingKey, setEditingKey] = useState(null)
  const [editingValue, setEditingValue] = useState('')
  const [memoryLoading, setMemoryLoading] = useState(false)

  const fetchMemory = async () => {
    if (!activeConversationId) return
    setMemoryLoading(true)
    try {
      const r = await fetch(`/api/memory/${activeConversationId}`)
      const d = await r.json()
      if (d.status === 'ok') {
        setProjectMemory(d.memory || {})
      }
    } catch (e) {
      console.error("Failed to fetch project memory:", e)
    }
    setMemoryLoading(false)
  }

  const handleUpdateMemory = async (key, val) => {
    if (!activeConversationId) return
    setSaving(true)
    setMsg('')
    try {
      const resp = await fetch(`/api/memory/${activeConversationId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, value: val })
      })
      const d = await resp.json()
      if (d.status === 'ok') {
        setMsg('长期记忆库已人工覆盖成功！')
        setEditingKey(null)
        fetchMemory()
      } else {
        setMsg('更新失败：' + d.message)
      }
    } catch {
      setMsg('保存异常，连接已断开')
    }
    setSaving(false)
  }

  const handleDeleteMemory = async (key) => {
    if (!activeConversationId) return
    setSaving(true)
    setMsg('')
    try {
      const resp = await fetch(`/api/memory/${activeConversationId}/${key}`, {
        method: 'DELETE'
      })
      const d = await resp.json()
      if (d.status === 'ok') {
        setMsg('记忆项已删除')
        fetchMemory()
      } else {
        setMsg('删除失败：' + d.message)
      }
    } catch {
      setMsg('操作异常')
    }
    setSaving(false)
  }

  useEffect(() => {
    if (tab === 'memory' && activeConversationId) {
      fetchMemory()
    }
  }, [tab, activeConversationId])

  // Smart Router states
  const [autoRouting, setAutoRouting] = useState(true)
  const [manualRoutes, setManualRoutes] = useState({})
  const [routerAgents, setRouterAgents] = useState([])
  const [routerLoading, setRouterLoading] = useState(false)

  const fetchRouterSettings = async () => {
    setRouterLoading(true)
    try {
      const r = await fetch('/api/settings/router')
      const d = await r.json()
      setAutoRouting(d.auto_routing ?? true)
      setManualRoutes(d.manual_routes || {})
      setRouterAgents(d.agents || [])
    } catch (e) {
      console.error("Failed to fetch router settings:", e)
    }
    setRouterLoading(false)
  }

  const handleSaveRouterSettings = async () => {
    setSaving(true)
    setMsg('')
    try {
      const resp = await fetch('/api/settings/router', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auto_routing: autoRouting, manual_routes: manualRoutes })
      })
      const d = await resp.json()
      if (d.status === 'ok') {
        setMsg(d.message)
      } else {
        setMsg('保存失败：' + d.message)
      }
    } catch {
      setMsg('保存异常')
    }
    setSaving(false)
  }

  useEffect(() => {
    if (tab === 'router') {
      fetchRouterSettings()
    }
  }, [tab])

  const handleAgentRouteTypeChange = (agentId, type) => {
    const newRoutes = { ...manualRoutes }
    if (type === 'global') {
      newRoutes[agentId] = { provider: '', base_url: '', model: '', api_key: '' }
    } else if (type === 'ollama') {
      newRoutes[agentId] = { provider: 'ollama', base_url: 'http://127.0.0.1:11434/v1', model: 'deepseek-r1:7b', api_key: 'local' }
    } else if (type === 'lm_studio') {
      newRoutes[agentId] = { provider: 'openai', base_url: 'http://127.0.0.1:1234/v1', model: 'local-model', api_key: 'local' }
    } else {
      newRoutes[agentId] = { provider: 'openai', base_url: 'https://api.openai.com/v1', model: 'gpt-4o', api_key: '' }
    }
    setManualRoutes(newRoutes)
  }

  const updateAgentCustomRoute = (agentId, field, val) => {
    const newRoutes = { ...manualRoutes }
    newRoutes[agentId] = {
      ...(newRoutes[agentId] || {}),
      [field]: val
    }
    setManualRoutes(newRoutes)
  }

  const getAgentRouteType = (agentId) => {
    const r = manualRoutes[agentId]
    if (!r || !r.provider) return 'global'
    if (r.provider === 'ollama' && r.base_url === 'http://127.0.0.1:11434/v1') return 'ollama'
    if (r.provider === 'openai' && r.base_url === 'http://127.0.0.1:1234/v1') return 'lm_studio'
    return 'custom'
  }

  // MCP integration states
  const [mcpServers, setMcpServers] = useState([])
  const [mcpTools, setMcpTools] = useState([])
  const [mcpLoading, setMcpLoading] = useState(false)
  const [newMcpName, setNewMcpName] = useState('')
  const [newMcpCmd, setNewMcpCmd] = useState('')
  const [newMcpArgs, setNewMcpArgs] = useState('')

  const fetchMcpData = async () => {
    setMcpLoading(true)
    try {
      const r1 = await fetch('/api/mcp/servers')
      const d1 = await r1.json()
      if (d1.status === 'ok') setMcpServers(d1.servers || [])

      const r2 = await fetch('/api/mcp/tools')
      const d2 = await r2.json()
      if (d2.status === 'ok') setMcpTools(d2.tools || [])
    } catch (e) {
      console.error("Failed to fetch MCP configs:", e)
    }
    setMcpLoading(false)
  }

  const handleAddMcpServer = async () => {
    if (!newMcpName || !newMcpCmd) {
      setMsg('请填写完整的服务器名称与执行指令')
      return
    }
    setSaving(true)
    setMsg('')
    try {
      const parsedArgs = newMcpArgs.split(' ').filter(Boolean)
      const resp = await fetch('/api/mcp/servers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newMcpName,
          command: newMcpCmd,
          args: parsedArgs
        })
      })
      const d = await resp.json()
      if (d.status === 'ok') {
        setMsg(d.message)
        setNewMcpName('')
        setNewMcpCmd('')
        setNewMcpArgs('')
        fetchMcpData()
      } else {
        setMsg('启动失败：' + d.message)
      }
    } catch {
      setMsg('添加服务器异常')
    }
    setSaving(false)
  }

  const handleDeleteMcpServer = async (name) => {
    setSaving(true)
    setMsg('')
    try {
      const resp = await fetch(`/api/mcp/servers/${name}`, { method: 'DELETE' })
      const d = await resp.json()
      if (d.status === 'ok') {
        setMsg(d.message)
        fetchMcpData()
      } else {
        setMsg('卸载失败：' + d.message)
      }
    } catch {
      setMsg('卸载异常')
    }
    setSaving(false)
  }

  useEffect(() => {
    if (tab === 'mcp') {
      fetchMcpData()
    }
  }, [tab])

  // Sandbox version control states
  const [sandboxCommits, setSandboxCommits] = useState([])
  const [sandboxLoading, setSandboxLoading] = useState(false)

  const fetchSandboxCommits = async () => {
    if (!activeConversationId) return
    setSandboxLoading(true)
    try {
      const resp = await fetch(`/api/sandbox/${activeConversationId}/commits`)
      const d = await resp.json()
      if (d.status === 'ok') {
        setSandboxCommits(d.commits || [])
      }
    } catch (e) {
      console.error("Failed to fetch sandbox commits:", e)
    }
    setSandboxLoading(false)
  }

  const handleRollbackSandbox = async (commitHash) => {
    if (!activeConversationId) return
    setSaving(true)
    setMsg('')
    try {
      const resp = await fetch(`/api/sandbox/${activeConversationId}/rollback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ commit_hash: commitHash })
      })
      const d = await resp.json()
      if (d.status === 'ok') {
        setMsg(d.message)
        fetchSandboxCommits()
      } else {
        setMsg('回退失败：' + d.message)
      }
    } catch {
      setMsg('回退请求异常')
    }
    setSaving(false)
  }

  useEffect(() => {
    if (tab === 'sandbox' && activeConversationId) {
      fetchSandboxCommits()
    }
  }, [tab, activeConversationId])



  // AI Detector state
  const [detecting, setDetecting] = useState(false)
  const [detectedTools, setDetectedTools] = useState([])
  const [selectedModels, setSelectedModels] = useState({})

  const scanLocalTools = async () => {
    setDetecting(true)
    setMsg('')
    try {
      const resp = await fetch('/api/tools/detect')
      const data = await resp.json()
      if (data.status === 'ok') {
        setDetectedTools(data.tools || [])
        const newModels = {}
        data.tools.forEach((t) => {
          if (t.models && t.models.length > 0) {
            newModels[t.id] = t.models[0]
          }
        })
        setSelectedModels(newModels)
        setMsg('扫描完成！已更新本地运行的 AI 工具状态。')
      } else {
        setMsg('扫描失败：' + (data.message || '未知错误'))
      }
    } catch (e) {
      setMsg('连接后端超时或失败')
    }
    setDetecting(false)
  }

  const applyToolAction = async (toolId, action) => {
    setSaving(true)
    setMsg('')
    try {
      const model = selectedModels[toolId] || ''
      const resp = await fetch('/api/tools/apply-detected', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tool_id: toolId,
          action,
          options: { model }
        })
      })
      const d = await resp.json()
      if (d.status === 'ok') {
        setMsg(d.message)
        if (action === 'replace_settings') {
          const r = await fetch('/api/settings/llm')
          const settings = await r.json()
          setProvider(settings.provider || 'openai')
          setBaseUrl(settings.base_url || '')
          setModel(settings.model || '')
          setTemperature(settings.temperature ?? 0.5)
          setMaxTokens(settings.max_tokens ?? 8192)
          setConfigured(settings.configured)
        }
      } else {
        setMsg('应用失败：' + (d.message || '未知错误'))
      }
    } catch {
      setMsg('操作失败，连接断开')
    }
    setSaving(false)
  }

  useEffect(() => {
    if (tab === 'detector') {
      scanLocalTools()
    }
  }, [tab])


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
    { id: 'llm', label: '🤖 LLM 模型' },
    { id: 'router', label: '🔀 智能路由' },
    { id: 'mcp', label: '🔌 MCP 工具' },
    { id: 'sandbox', label: '📂 沙盒版本' },
    { id: 'quality', label: '🎯 质量门' },
    { id: 'prompt', label: '📐 Prompt 分层' },
    { id: 'memory', label: '💡 长期记忆' },
    { id: 'detector', label: '🔍 AI 探针' },
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
            }}>{t.label}</button>
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
              {configured ? '✅ 已连接 LLM — Agent 使用真实模型回复' : '⚠️ 未配置 — Agent 使用 Mock 回复'}
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
                {['openai', 'anthropic', 'ollama'].map((p) => (
                  <button key={p} onClick={() => {
                    setProvider(p);
                    if (p === 'ollama') {
                      setBaseUrl('http://127.0.0.1:11434/v1');
                    }
                  }} style={{
                    flex: 1, padding: '10px', borderRadius: 8, fontSize: 13,
                    background: provider === p ? '#6366f1' : 'rgba(255,255,255,0.04)',
                    border: `1px solid ${provider === p ? '#6366f1' : 'rgba(255,255,255,0.1)'}`,
                    color: provider === p ? 'white' : '#94a3b8',
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
                        <option key={m} value={m} style={{ background: '#1e293b', color: '#f8fafc' }}>
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
                      background: 'rgba(99,102,241,0.1)',
                      border: '1px solid rgba(99,102,241,0.2)',
                      color: '#a5b4fc',
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
                <div style={{ marginTop: 6, fontSize: 11, color: '#fbbf24' }}>
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

        {/* ====== TAB: AI Memory ====== */}
        {tab === 'memory' && (
          <>
            <div style={{
              padding: '12px 16px', borderRadius: 10, marginBottom: 20,
              background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)',
              fontSize: 12, color: '#a5b4fc', display: 'flex', justifyContent: 'space-between', alignItems: 'center'
            }}>
              <span>可追踪、人工可干预覆写的项目长期记忆库 (White-box Memory)</span>
              <button
                onClick={fetchMemory}
                disabled={memoryLoading}
                style={{
                  padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                  background: 'rgba(99,102,241,0.1)', color: '#a5b4fc', border: '1px solid rgba(99,102,241,0.2)', cursor: 'pointer',
                  opacity: memoryLoading ? 0.6 : 1, display: 'flex', alignItems: 'center', gap: 4
                }}
              >
                {memoryLoading ? '🔄 载入中...' : '🔄 刷新记忆'}
              </button>
            </div>

            {memoryLoading ? (
              <div style={{ padding: '40px 0', textAlign: 'center', color: '#64748b' }}>
                <span style={{ fontSize: 24, display: 'block', marginBottom: 12 }}>🔄</span>
                <span>正在提取底层 SQLite 记忆图谱...</span>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14, maxHeight: '50vh', overflowY: 'auto', paddingRight: 4 }}>
                {(() => {
                  const keyLabels = {
                    tech_stack: { label: '⚙️ 开发技术栈 & API 契约', desc: '捕获并沉淀本项目的框架、端口、API 路由规范。' },
                    user_preference: { label: '🎨 用户偏好 & 编码风格', desc: '归纳您专属的设计主题、微动效偏好及编码约定。' },
                    implemented_features: { label: '✅ 已实现特性 & 模块列表', desc: '记录项目中已开发成功的文件与完整业务模块。' },
                    pending_todos: { label: '📋 待开发任务 & 遗留 TODO', desc: '梳理后续迭代方向、待解决 Bug 和待写模块。' }
                  };

                  return Object.keys(keyLabels).map((key) => {
                    const item = projectMemory[key] || { value: '', source: 'system', updated_at: '-' };
                    const info = keyLabels[key];
                    const isEditing = editingKey === key;
                    const isUserSource = item.source === 'user';

                    return (
                      <div key={key} style={{
                        padding: 16, borderRadius: 12, background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.06)', display: 'flex', flexDirection: 'column', gap: 10
                      }}>
                        {/* Card Header */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div>
                            <div style={{ fontSize: 13, color: '#f8fafc', fontWeight: 600 }}>{info.label}</div>
                            <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{info.desc}</div>
                          </div>
                          <span style={{
                            fontSize: 10, fontWeight: 600, padding: '2px 6px', borderRadius: 4,
                            background: isUserSource ? 'rgba(34, 211, 238, 0.15)' : 'rgba(168, 85, 247, 0.15)',
                            color: isUserSource ? '#22d3ee' : '#c084fc',
                            border: `1px solid ${isUserSource ? 'rgba(34, 211, 238, 0.3)' : 'rgba(168, 85, 247, 0.3)'}`
                          }}>
                            {isUserSource ? '👤 人工覆写' : '🧠 AI 提炼'}
                          </span>
                        </div>

                        {/* Card Body */}
                        {isEditing ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4 }}>
                            <textarea
                              value={editingValue}
                              onChange={(e) => setEditingValue(e.target.value)}
                              rows={4}
                              style={{
                                width: '100%', padding: '10px 12px', background: '#0f172a',
                                border: '1px solid rgba(99, 102, 241, 0.4)', borderRadius: 8,
                                color: '#f8fafc', fontSize: 12, fontFamily: 'monospace', outline: 'none',
                                lineHeight: '1.6'
                              }}
                              placeholder={`在此编辑当前项目的 ${info.label}...`}
                            />
                            <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                              <button
                                onClick={() => setEditingKey(null)}
                                style={{
                                  padding: '6px 12px', borderRadius: 6, fontSize: 11,
                                  background: 'transparent', border: '1px solid rgba(255,255,255,0.1)',
                                  color: '#94a3b8', cursor: 'pointer'
                                }}
                              >
                                取消
                              </button>
                              <button
                                onClick={() => handleUpdateMemory(key, editingValue)}
                                disabled={saving}
                                style={{
                                  padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                                  background: '#6366f1', border: 'none', color: 'white', cursor: 'pointer'
                                }}
                              >
                                保存修改
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div style={{ marginTop: 4 }}>
                            {item.value ? (
                              <pre style={{
                                margin: 0, padding: '10px 12px', background: 'rgba(0,0,0,0.2)',
                                border: '1px solid rgba(255,255,255,0.04)', borderRadius: 8,
                                fontSize: 12, color: '#e2e8f0', fontFamily: 'monospace',
                                whiteSpace: 'pre-wrap', wordBreak: 'break-all', lineHeight: '1.6'
                              }}>
                                {item.value}
                              </pre>
                            ) : (
                              <div style={{
                                padding: '14px', border: '1px dashed rgba(255,255,255,0.1)',
                                borderRadius: 8, textAlign: 'center', color: '#64748b', fontSize: 11
                              }}>
                                本项暂无记忆沉淀。AI 将在下一轮交付时为您提取，您也可以直接点击右侧手动编写。
                              </div>
                            )}

                            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
                              {item.value && (
                                <button
                                  onClick={() => handleDeleteMemory(key)}
                                  style={{
                                    padding: '5px 10px', borderRadius: 6, fontSize: 11,
                                    background: 'rgba(239, 68, 68, 0.05)', border: '1px solid rgba(239, 68, 68, 0.15)',
                                    color: '#f87171', cursor: 'pointer', transition: 'all 0.2s'
                                  }}
                                >
                                  🗑️ 遗忘
                                </button>
                              )}
                              <button
                                onClick={() => {
                                  setEditingKey(key)
                                  setEditingValue(item.value || '')
                                }}
                                style={{
                                  padding: '5px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                                  background: 'rgba(99, 102, 241, 0.1)', border: '1px solid rgba(99, 102, 241, 0.2)',
                                  color: '#a5b4fc', cursor: 'pointer', transition: 'all 0.2s'
                                }}
                              >
                                📝 {item.value ? '修改记忆' : '手动配置'}
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  });
                })()}
              </div>
            )}
          </>
        )}

        {/* ====== TAB: Smart Router ====== */}
        {tab === 'router' && (
          <>
            <div style={{
              padding: '12px 16px', borderRadius: 10, marginBottom: 20,
              background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)',
              fontSize: 12, color: '#a5b4fc', lineHeight: '1.5'
            }}>
              💡 智能路由调度器借鉴了 <b>Pilotdeck OS</b> 架构，能自动将不同层级的智能体任务分配给最合适的模型引擎（如云端大模型做顶层设计、本地 Ollama 跑高负载编码），从而实现极端算力与开销的均衡。
            </div>

            {/* Auto Routing Toggle */}
            <div style={{ ...rowStyle, marginBottom: 20 }}>
              <div>
                <div style={{ fontSize: 14, color: '#f8fafc', fontWeight: 600 }}>启用自动探针路由 (Smart Auto-Route)</div>
                <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>自动探测本地 Ollama / LM Studio 端口，无缝 fallback 自愈</div>
              </div>
              <ToggleSwitch checked={autoRouting} onChange={setAutoRouting} />
            </div>

            {autoRouting ? (
              /* Auto Routing visualization flow */
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 20 }}>
                {/* L1 Tier */}
                <div style={{
                  padding: 14, borderRadius: 10, background: 'rgba(99, 102, 241, 0.05)',
                  border: '1px solid rgba(99, 102, 241, 0.15)'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: '#a5b4fc' }}>🥇 L1 规划决策层 (Planning & Audit)</span>
                    <span style={{ fontSize: 11, background: 'rgba(99, 102, 241, 0.15)', color: '#a5b4fc', padding: '2px 6px', borderRadius: 4 }}>云端旗舰模型</span>
                  </div>
                  <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>
                    涉及智能体：项目经理 (PM)、系统架构师 (Builder)、质量门校验 (Quality Gate)
                  </div>
                  <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 6, display: 'flex', gap: 6, alignItems: 'center' }}>
                    <span>🧠 默认路由指向:</span>
                    <span style={{ fontFamily: 'monospace', background: 'rgba(0,0,0,0.2)', padding: '2px 6px', borderRadius: 4, color: '#e2e8f0' }}>
                      {provider === 'ollama' ? 'Ollama' : (provider || 'OpenAI')} ({model || '默认'})
                    </span>
                  </div>
                </div>

                {/* L2 Tier */}
                <div style={{
                  padding: 14, borderRadius: 10, background: 'rgba(34, 211, 238, 0.03)',
                  border: '1px solid rgba(34, 211, 238, 0.15)'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: '#22d3ee' }}>🥈 L2 高载荷编码层 (Coding & Testing)</span>
                    <span style={{ fontSize: 11, background: 'rgba(34, 211, 238, 0.15)', color: '#22d3ee', padding: '2px 6px', borderRadius: 4 }}>本地自适应探针</span>
                  </div>
                  <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>
                    涉及智能体：前端工程师 (Frontend)、后端工程师 (Backend)、测试工程师 (Tester)
                  </div>
                  <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 6, display: 'flex', gap: 6, alignItems: 'center' }}>
                    <span>🔌 智能检测探测:</span>
                    <span style={{ color: '#22d3ee', fontSize: 11 }}>优先探测本地 Ollama (11434) / LM Studio (1234)，若均未启动则自愈降级回云端大模型</span>
                  </div>
                </div>

                {/* L3 Tier */}
                <div style={{
                  padding: 14, borderRadius: 10, background: 'rgba(168, 85, 247, 0.03)',
                  border: '1px solid rgba(168, 85, 247, 0.15)'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: '#c084fc' }}>🥉 L3 辅助与创意层 (Creative & DevOps)</span>
                    <span style={{ fontSize: 11, background: 'rgba(168, 85, 247, 0.15)', color: '#c084fc', padding: '2px 6px', borderRadius: 4 }}>本地轻量模型</span>
                  </div>
                  <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>
                    涉及智能体：UI设计师 (Designer)、运维工程师 (DevOps)
                  </div>
                  <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 6, display: 'flex', gap: 6, alignItems: 'center' }}>
                    <span>🎨 路由规则:</span>
                    <span style={{ color: '#c084fc', fontSize: 11 }}>首选本地 7B/8B 轻量级大模型（如 Ollama 中的 qwen2.5/llama3），降低开发成本</span>
                  </div>
                </div>
              </div>
            ) : (
              /* Manual overrides list */
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginBottom: 20, maxHeight: '42vh', overflowY: 'auto', paddingRight: 4 }}>
                {routerAgents.length === 0 ? (
                  <div style={{ textAlign: 'center', color: '#64748b', padding: '20px 0', fontSize: 12 }}>
                    未加载到智能体列表
                  </div>
                ) : (
                  routerAgents.map((agent) => {
                    const currentType = getAgentRouteType(agent.id);
                    const route = manualRoutes[agent.id] || {};

                    return (
                      <div key={agent.id} style={{
                        padding: 14, borderRadius: 12, background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.06)', display: 'flex', flexDirection: 'column', gap: 10
                      }}>
                        {/* Agent info */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{ fontSize: 18 }}>{agent.avatar || '🤖'}</span>
                            <div>
                              <span style={{ fontSize: 13, color: '#f8fafc', fontWeight: 600 }}>{agent.name}</span>
                              <span style={{ fontSize: 10, color: '#64748b', marginLeft: 8, background: 'rgba(0,0,0,0.2)', padding: '1px 5px', borderRadius: 4 }}>
                                {agent.role}
                              </span>
                            </div>
                          </div>

                          {/* Route selector */}
                          <select
                            value={currentType}
                            onChange={(e) => handleAgentRouteTypeChange(agent.id, e.target.value)}
                            style={{
                              padding: '5px 8px', borderRadius: 6, background: '#0f172a',
                              border: '1px solid rgba(255,255,255,0.1)', color: '#f8fafc', fontSize: 11,
                              outline: 'none', cursor: 'pointer'
                            }}
                          >
                            <option value="global" style={{ background: '#0f172a' }}>🌏 默认全局模型</option>
                            <option value="ollama" style={{ background: '#0f172a' }}>🦙 Ollama 本地</option>
                            <option value="lm_studio" style={{ background: '#0f172a' }}>💻 LM Studio 本地</option>
                            <option value="custom" style={{ background: '#0f172a' }}>⚙️ 自定义模型</option>
                          </select>
                        </div>

                        {/* Custom fields rendered if custom type is selected */}
                        {currentType === 'custom' && (
                          <div style={{
                            display: 'flex', flexDirection: 'column', gap: 8, marginTop: 4,
                            padding: 10, borderRadius: 8, background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.04)'
                          }}>
                            {/* Provider */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <span style={{ fontSize: 11, color: '#64748b', width: 60 }}>接口格式:</span>
                              <select
                                value={route.provider || 'openai'}
                                onChange={(e) => updateAgentCustomRoute(agent.id, 'provider', e.target.value)}
                                style={{
                                  flex: 1, padding: '4px 6px', borderRadius: 6, background: '#1e293b',
                                  border: '1px solid rgba(255,255,255,0.1)', color: '#f8fafc', fontSize: 11, outline: 'none'
                                }}
                              >
                                <option value="openai" style={{ background: '#1e293b' }}>OpenAI 兼容</option>
                                <option value="anthropic" style={{ background: '#1e293b' }}>Anthropic</option>
                                <option value="ollama" style={{ background: '#1e293b' }}>Ollama</option>
                              </select>
                            </div>

                            {/* Base URL */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <span style={{ fontSize: 11, color: '#64748b', width: 60 }}>API 地址:</span>
                              <input
                                value={route.base_url || ''}
                                onChange={(e) => updateAgentCustomRoute(agent.id, 'base_url', e.target.value)}
                                placeholder="http://..."
                                style={{
                                  flex: 1, padding: '4px 6px', borderRadius: 6, background: '#1e293b',
                                  border: '1px solid rgba(255,255,255,0.1)', color: '#f8fafc', fontSize: 11, outline: 'none'
                                }}
                              />
                            </div>

                            {/* Model */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <span style={{ fontSize: 11, color: '#64748b', width: 60 }}>模型名称:</span>
                              <input
                                value={route.model || ''}
                                onChange={(e) => updateAgentCustomRoute(agent.id, 'model', e.target.value)}
                                placeholder="gpt-4o"
                                style={{
                                  flex: 1, padding: '4px 6px', borderRadius: 6, background: '#1e293b',
                                  border: '1px solid rgba(255,255,255,0.1)', color: '#f8fafc', fontSize: 11, outline: 'none'
                                }}
                              />
                            </div>

                            {/* API Key */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <span style={{ fontSize: 11, color: '#64748b', width: 60 }}>API Key:</span>
                              <input
                                type="password"
                                value={route.api_key || ''}
                                onChange={(e) => updateAgentCustomRoute(agent.id, 'api_key', e.target.value)}
                                placeholder="sk-..."
                                style={{
                                  flex: 1, padding: '4px 6px', borderRadius: 6, background: '#1e293b',
                                  border: '1px solid rgba(255,255,255,0.1)', color: '#f8fafc', fontSize: 11, outline: 'none'
                                }}
                              />
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            )}

            <button onClick={handleSaveRouterSettings} disabled={saving} style={{ ...btnStyle, marginBottom: 12 }}>
              {saving ? '保存中...' : '💾 保存路由配置'}
            </button>
          </>
        )}

        {/* ====== TAB: MCP Tools ====== */}
        {tab === 'mcp' && (
          <>
            <div style={{
              padding: '12px 16px', borderRadius: 10, marginBottom: 20,
              background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)',
              fontSize: 12, color: '#a5b4fc', lineHeight: '1.5', display: 'flex', justifyContent: 'space-between', alignItems: 'center'
            }}>
              <span>🔌 <b>Model Context Protocol (MCP)</b> 原生工具链管理中心，实现物理级工具装载与执行</span>
              <button
                onClick={fetchMcpData}
                disabled={mcpLoading}
                style={{
                  padding: '5px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                  background: 'rgba(99,102,241,0.1)', color: '#a5b4fc', border: '1px solid rgba(99,102,241,0.2)', cursor: 'pointer',
                  opacity: mcpLoading ? 0.6 : 1, display: 'flex', alignItems: 'center', gap: 4
                }}
              >
                {mcpLoading ? '🔄' : '🔄 刷新'}
              </button>
            </div>

            {/* Configured MCP Servers */}
            <div style={{ marginBottom: 24 }}>
              <label style={{ ...labelStyle, fontSize: 14, fontWeight: 600, color: '#f8fafc', marginBottom: 12 }}>⚡ 运行中的 MCP 服务器 (Servers)</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: '25vh', overflowY: 'auto', paddingRight: 4 }}>
                {mcpServers.map((srv) => {
                  const isActive = srv.status === 'active';
                  return (
                    <div key={srv.name} style={{
                      padding: 12, borderRadius: 10, background: 'rgba(255,255,255,0.02)',
                      border: `1px solid ${isActive ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}`,
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      boxShadow: isActive ? '0 0 10px rgba(16,185,129,0.02)' : 'none'
                    }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span style={{ fontSize: 13, color: '#f8fafc', fontWeight: 600 }}>{srv.name}</span>
                          <span style={{
                            fontSize: 9, fontWeight: 600, padding: '2px 6px', borderRadius: 4,
                            background: isActive ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
                            color: isActive ? '#34d399' : '#f87171'
                          }}>
                            {isActive ? '🟢 活跃在线' : '🔴 离线异常'}
                          </span>
                          {srv.is_system && (
                            <span style={{ fontSize: 9, background: 'rgba(99,102,241,0.15)', color: '#a5b4fc', padding: '2px 6px', borderRadius: 4 }}>
                              🛡️ 系统核心
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: 11, color: '#64748b', marginTop: 4, fontFamily: 'monospace' }}>
                          Command: {srv.command} {srv.args.join(' ')}
                        </div>
                      </div>
                      {!srv.is_system && (
                        <button
                          onClick={() => handleDeleteMcpServer(srv.name)}
                          disabled={saving}
                          style={{
                            padding: '4px 8px', borderRadius: 6, fontSize: 11, background: 'rgba(239, 68, 68, 0.05)',
                            border: '1px solid rgba(239, 68, 68, 0.2)', color: '#f87171', cursor: 'pointer', transition: 'all 0.2s'
                          }}
                        >
                          🗑️ 卸载
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Register External Stdio Server */}
            <div style={{
              padding: 16, borderRadius: 12, background: 'rgba(0,0,0,0.15)',
              border: '1px solid rgba(255,255,255,0.04)', marginBottom: 24
            }}>
              <label style={{ ...labelStyle, fontSize: 12, fontWeight: 600, color: '#f8fafc', marginBottom: 10 }}>🔌 注册外部 Stdio 服务器 (JSON-RPC 协议)</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    value={newMcpName}
                    onChange={(e) => setNewMcpName(e.target.value)}
                    placeholder="服务器名称 (如 sqlite)"
                    style={{ ...inputStyle, flex: 1, padding: '8px 12px', fontSize: 12 }}
                  />
                  <input
                    value={newMcpCmd}
                    onChange={(e) => setNewMcpCmd(e.target.value)}
                    placeholder="执行命令 (如 npx 或 python)"
                    style={{ ...inputStyle, flex: 1, padding: '8px 12px', fontSize: 12 }}
                  />
                </div>
                <input
                  value={newMcpArgs}
                  onChange={(e) => setNewMcpArgs(e.target.value)}
                  placeholder="命令参数，以空格分隔 (如 -y @modelcontextprotocol/server-sqlite --db sqlite.db)"
                  style={{ ...inputStyle, padding: '8px 12px', fontSize: 12 }}
                />
                <button
                  onClick={handleAddMcpServer}
                  disabled={saving}
                  style={{
                    padding: '8px', borderRadius: 8, background: '#6366f1',
                    border: 'none', color: 'white', fontSize: 12, fontWeight: 600,
                    cursor: 'pointer', transition: 'all 0.2s'
                  }}
                >
                  {saving ? '正在启动并连接...' : '🔌 启动并注册此 MCP 服务'}
                </button>
              </div>
            </div>

            {/* Consolidated Tools List */}
            <div style={{ marginBottom: 12 }}>
              <label style={{ ...labelStyle, fontSize: 14, fontWeight: 600, color: '#f8fafc', marginBottom: 12 }}>🔍 聚合工具中心 (Active Tools: {mcpTools.length})</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: '35vh', overflowY: 'auto', paddingRight: 4 }}>
                {mcpTools.length === 0 ? (
                  <div style={{ textAlign: 'center', color: '#64748b', padding: '20px 0', fontSize: 12 }}>
                    暂无可用工具，请刷新或检查服务器是否活跃
                  </div>
                ) : (
                  mcpTools.map((t) => (
                    <div key={t.name} style={{
                      padding: 14, borderRadius: 10, background: 'rgba(255,255,255,0.01)',
                      border: '1px solid rgba(255,255,255,0.05)', display: 'flex', flexDirection: 'column', gap: 6
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: 13, color: '#38bdf8', fontWeight: 600, fontFamily: 'monospace' }}>
                          {t.name}
                        </span>
                        <span style={{ fontSize: 10, background: 'rgba(56, 189, 248, 0.1)', color: '#38bdf8', padding: '1px 5px', borderRadius: 4 }}>
                          {t.server_name}
                        </span>
                      </div>
                      <p style={{ margin: 0, fontSize: 12, color: '#94a3b8', lineHeight: '1.4' }}>
                        {t.description}
                      </p>
                      {t.inputSchema && Object.keys(t.inputSchema.properties || {}).length > 0 && (
                        <div style={{ marginTop: 4 }}>
                          <pre style={{
                            margin: 0, padding: '6px 10px', background: 'rgba(0,0,0,0.2)',
                            borderRadius: 6, fontSize: 10, color: '#64748b', fontFamily: 'monospace',
                            overflowX: 'auto', border: '1px solid rgba(255,255,255,0.02)'
                          }}>
                            Schema: {JSON.stringify(t.inputSchema.properties, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          </>
        )}

        {/* ====== TAB: Sandbox Version Control ====== */}
        {tab === 'sandbox' && (
          <>
            <div style={{
              padding: '12px 16px', borderRadius: 10, marginBottom: 20,
              background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)',
              fontSize: 12, color: '#a5b4fc', lineHeight: '1.5', display: 'flex', justifyContent: 'space-between', alignItems: 'center'
            }}>
              <span>📂 <b>事务级影子 Git 版本控制系统 (Versioning OS)</b> — 实时记录并拦截智能体的写入行为</span>
              <button
                onClick={fetchSandboxCommits}
                disabled={sandboxLoading}
                style={{
                  padding: '5px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                  background: 'rgba(99,102,241,0.1)', color: '#a5b4fc', border: '1px solid rgba(99,102,241,0.2)', cursor: 'pointer',
                  opacity: sandboxLoading ? 0.6 : 1, display: 'flex', alignItems: 'center', gap: 4
                }}
              >
                {sandboxLoading ? '🔄' : '🔄 刷新'}
              </button>
            </div>

            {sandboxLoading ? (
              <div style={{ padding: '40px 0', textAlign: 'center', color: '#64748b' }}>
                <span style={{ fontSize: 24, display: 'block', marginBottom: 12 }}>🔄</span>
                <span>正在扫描沙盒 Git 影子分支状态...</span>
              </div>
            ) : (
              <div style={{ position: 'relative', paddingLeft: 32, paddingRight: 4, maxHeight: '60vh', overflowY: 'auto' }}>
                {sandboxCommits.length === 0 ? (
                  <div style={{
                    padding: '30px', border: '1px dashed rgba(255,255,255,0.1)',
                    borderRadius: 12, textAlign: 'center', color: '#64748b', fontSize: 12, marginLeft: -32
                  }}>
                    🛡️ 当前沙盒尚未产生任何版本控制数据。
                    <br /><span style={{ fontSize: 11, color: '#475569', marginTop: 6, display: 'inline-block' }}>当智能体开始为您修改代码或运行终端指令时，系统会自动在此沉淀事务版本。</span>
                  </div>
                ) : (
                  <>
                    {/* Glowing timeline track line */}
                    <div style={{
                      position: 'absolute', left: 14, top: 12, bottom: 12, width: 2,
                      background: 'linear-gradient(180deg, #6366f1 0%, rgba(99,102,241,0.1) 100%)',
                      boxShadow: '0 0 8px rgba(99,102,241,0.3)'
                    }} />

                    {sandboxCommits.map((c) => {
                      const msg = c.message;
                      // Categorize commit nodes
                      let color = '#3b82f6'; // default blue
                      let category = '👤 手动操作';
                      let icon = '🔵';

                      if (msg.includes('Pre-write') || msg.includes('Pre-command')) {
                        color = '#eab308'; // yellow
                        category = '🟡 事务前备份 (Pre-Action Checkpoint)';
                        icon = '🟡';
                      } else if (msg.includes('Success-write') || msg.includes('Success-command')) {
                        color = '#10b981'; // green
                        category = '🟢 安全编译通过 (Success Checkpoint)';
                        icon = '🟢';
                      } else if (msg.includes('自愈') || msg.includes('rollback') || msg.includes('failed')) {
                        color = '#ef4444'; // red
                        category = '🔴 自动自愈回滚 (Self-healed Rollback)';
                        icon = '🔴';
                      } else if (msg.includes('Initial Commit')) {
                        color = '#a855f7'; // purple
                        category = '💜 沙盒初始化 (Workspace Initialized)';
                        icon = '💜';
                      }

                      return (
                        <div key={c.hash} style={{ position: 'relative', marginBottom: 20 }}>
                          {/* Glowing node dot */}
                          <div style={{
                            position: 'absolute', left: -24, top: 16, width: 12, height: 12,
                            borderRadius: '50%', background: color, border: '2px solid #1e293b',
                            boxShadow: `0 0 10px ${color}`, zIndex: 10
                          }} />

                          {/* Commit Details Card */}
                          <div style={{
                            padding: 14, borderRadius: 12, background: 'rgba(255,255,255,0.02)',
                            border: '1px solid rgba(255,255,255,0.06)', display: 'flex', flexDirection: 'column', gap: 6
                          }}>
                            {/* Card Header */}
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <span style={{ fontSize: 11, fontWeight: 600, color: color }}>
                                {category}
                              </span>
                              <span style={{ fontSize: 10, color: '#64748b', fontFamily: 'monospace' }}>
                                {new Date(c.timestamp * 1000).toLocaleTimeString()}
                              </span>
                            </div>

                            {/* Hash & Date details */}
                            <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 10, color: '#475569' }}>
                              <span style={{ fontFamily: 'monospace', background: 'rgba(0,0,0,0.2)', padding: '1px 5px', borderRadius: 4, color: '#94a3b8' }}>
                                Hash: {c.hash.substring(0, 7)}
                              </span>
                              <span>•</span>
                              <span>{new Date(c.timestamp * 1000).toLocaleDateString()}</span>
                            </div>

                            {/* Message Description */}
                            <p style={{ margin: '4px 0 0 0', fontSize: 12, color: '#e2e8f0', lineHeight: '1.4', fontFamily: 'monospace' }}>
                              {msg}
                            </p>

                            {/* Action Rollback Trigger */}
                            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 4 }}>
                              <button
                                onClick={() => handleRollbackSandbox(c.hash)}
                                disabled={saving}
                                style={{
                                  padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                                  background: 'rgba(99, 102, 241, 0.1)', border: '1px solid rgba(99, 102, 241, 0.2)',
                                  color: '#a5b4fc', cursor: 'pointer', transition: 'all 0.2s',
                                  display: 'flex', alignItems: 'center', gap: 4
                                }}
                              >
                                🔄 撤销并还原到此版本
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </>
                )}
              </div>
            )}
          </>
        )}

        {/* ====== TAB: AI Detector ====== */}
        {tab === 'detector' && (
          <>
            <div style={{
              padding: '12px 16px', borderRadius: 10, marginBottom: 20,
              background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)',
              fontSize: 12, color: '#a5b4fc', display: 'flex', justifyContent: 'space-between', alignItems: 'center'
            }}>
              <span>自动发现并集成用户本地运行的 Ollama、Claude Code 等 AI 工具</span>
              <button
                onClick={scanLocalTools}
                disabled={detecting}
                style={{
                  padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                  background: '#6366f1', color: 'white', border: 'none', cursor: 'pointer',
                  opacity: detecting ? 0.6 : 1, display: 'flex', alignItems: 'center', gap: 4,
                  boxShadow: '0 0 10px rgba(99,102,241,0.5)'
                }}
              >
                {detecting ? '🔍 扫描中...' : '🔄 重新扫描'}
              </button>
            </div>

            {detecting ? (
              <div style={{ padding: '40px 0', textAlign: 'center', color: '#64748b' }}>
                <span style={{ fontSize: 24, display: 'block', marginBottom: 12 }}>🔄</span>
                <span>正在深度探索本地环境与端口...</span>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14, maxHeight: '50vh', overflowY: 'auto', paddingRight: 4 }}>
                {detectedTools.length === 0 ? (
                  <div style={{ padding: '30px 0', textAlign: 'center', color: '#64748b', fontSize: 13 }}>
                    点击右上角【重新扫描】开始检测本地环境
                  </div>
                ) : (
                  detectedTools.map((t) => {
                    const isRunning = t.status === 'running';
                    const isInstalled = t.status === 'installed';

                    const statusBadgeStyle = {
                      fontSize: 11, fontWeight: 600, padding: '3px 8px', borderRadius: 6,
                      background: isRunning ? 'rgba(16,185,129,0.15)' : (isInstalled ? 'rgba(245,158,11,0.15)' : 'rgba(100,116,139,0.15)'),
                      color: isRunning ? '#10b981' : (isInstalled ? '#f59e0b' : '#94a3b8'),
                      border: `1px solid ${isRunning ? 'rgba(16,185,129,0.3)' : (isInstalled ? 'rgba(245,158,11,0.3)' : 'rgba(100,116,139,0.3)')}`
                    };

                    const actionBtnStyle = {
                      flex: 1, padding: '8px 10px', borderRadius: 8, fontSize: 11, fontWeight: 600,
                      cursor: 'pointer', border: 'none', transition: 'all 0.2s', display: 'flex',
                      alignItems: 'center', justifyContent: 'center', gap: 4
                    };

                    return (
                      <div key={t.id} style={{
                        padding: 16, borderRadius: 12, background: 'rgba(255,255,255,0.02)',
                        border: `1px solid ${isRunning ? 'rgba(99,102,241,0.2)' : 'rgba(255,255,255,0.06)'}`,
                        display: 'flex', flexDirection: 'column', gap: 10,
                        boxShadow: isRunning ? '0 4px 12px rgba(99,102,241,0.05)' : 'none'
                      }}>
                        {/* Header */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{ fontSize: 20 }}>{t.icon}</span>
                            <span style={{ fontSize: 14, color: '#f8fafc', fontWeight: 600 }}>{t.name}</span>
                          </div>
                          <span style={statusBadgeStyle}>
                            {isRunning ? '🟢 正在运行' : (isInstalled ? '🟡 已安装' : '⚪ 未检测到')}
                          </span>
                        </div>

                        {/* Description */}
                        <p style={{ margin: 0, fontSize: 12, color: '#94a3b8', lineHeight: '1.4' }}>
                          {t.description}
                        </p>

                        {/* Details */}
                        {t.details && (
                          <div style={{ fontSize: 11, color: '#fbbf24', background: 'rgba(251,191,36,0.05)', padding: '6px 10px', borderRadius: 6 }}>
                            💡 {t.details}
                          </div>
                        )}

                        {/* Model Dropdown for Ollama & LM Studio */}
                        {isRunning && t.models && t.models.length > 0 && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                            <label style={{ fontSize: 11, color: '#64748b', flexShrink: 0 }}>选择模型:</label>
                            <select
                              value={selectedModels[t.id] || ''}
                              onChange={(e) => setSelectedModels(prev => ({ ...prev, [t.id]: e.target.value }))}
                              style={{
                                flex: 1, padding: '4px 8px', borderRadius: 6, background: '#0f172a',
                                border: '1px solid rgba(255,255,255,0.1)', color: '#f8fafc', fontSize: 11
                              }}
                            >
                              {t.models.map((m) => (
                                <option key={m} value={m} style={{ background: '#0f172a' }}>{m}</option>
                              ))}
                            </select>
                          </div>
                        )}

                        {/* Actions */}
                        {(isRunning || isInstalled) && (
                          <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                            {t.suggested_tool && (
                              <button
                                onClick={() => applyToolAction(t.id, 'register_tool')}
                                disabled={saving}
                                style={{ ...actionBtnStyle, background: 'rgba(16,185,129,0.1)', color: '#34d399', border: '1px solid rgba(16,185,129,0.2)' }}
                                title="将该工具作为能力接入智能体项目，可在创建自定义助手时选用"
                              >
                                🔌 接入为工具
                              </button>
                            )}
                            {t.suggested_prompt_addon && (
                              <button
                                onClick={() => applyToolAction(t.id, 'add_to_prompt')}
                                disabled={saving}
                                style={{ ...actionBtnStyle, background: 'rgba(245,158,11,0.1)', color: '#fbbf24', border: '1px solid rgba(245,158,11,0.2)' }}
                                title="将本地环境背景写入 Prompt 全局上下文，使所有 Agent 自动感知"
                              >
                                📝 写入背景
                              </button>
                            )}
                            {t.suggested_llm_settings && isRunning && (
                              <button
                                onClick={() => applyToolAction(t.id, 'replace_settings')}
                                disabled={saving}
                                style={{ ...actionBtnStyle, background: '#6366f1', color: 'white' }}
                                title="直接将项目的底层大模型服务切换为本地的该服务"
                              >
                                ⚙️ 替换模型配置
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            )}
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
