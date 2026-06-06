import React, { useState, useEffect, useRef } from 'react'
import { Sun, Moon, Trash2, Key, ExternalLink, Check, X, Loader, Upload } from 'lucide-react'
import { useThemeStore } from '../../stores/themeStore'
import { useChatStore } from '../../stores/chatStore'
import IconAvatar from '../IconAvatar'

function AvatarUploadField({ value, onChange }) {
  const [preview, setPreview] = useState(null)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef(null)
  const previewRef = useRef(null)

  useEffect(() => {
    return () => { if (previewRef.current) URL.revokeObjectURL(previewRef.current) }
  }, [])

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      if (previewRef.current) URL.revokeObjectURL(previewRef.current)
      const url = URL.createObjectURL(file)
      previewRef.current = url
      setPreview(url)
      const formData = new FormData()
      formData.append('file', file)
      const resp = await fetch('/api/upload', { method: 'POST', body: formData })
      const data = await resp.json()
      if (data.status === 'uploaded') onChange(data.url)
    } catch {}
    setUploading(false)
    if (fileRef.current) fileRef.current.value = ''
  }

  const avatarSrc = preview || (value && (value.startsWith('/') || value.startsWith('http')) ? value : null)

  return (
    <div>
      {avatarSrc && (
        <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 10 }}>
          <img src={avatarSrc} alt="" style={{ width: 48, height: 48, borderRadius: 8, objectFit: 'cover', border: '2px solid var(--accent)' }} />
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{uploading ? '上传中...' : '已设置头像'}</span>
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <button
          onClick={() => fileRef.current?.click()}
          style={{
            flex: 'none', display: 'flex', alignItems: 'center', gap: 4,
            padding: '9px 12px', borderRadius: 8, fontSize: 12,
            background: 'var(--bg-secondary)', border: '1px solid var(--border)',
            color: 'var(--text-primary)', cursor: 'pointer', fontFamily: 'inherit',
          }}
          type="button"
        >
          <Upload size={14} />
          本地上传
        </button>
        <input
          value={preview ? '' : value || ''}
          onChange={(e) => { onChange(e.target.value); setPreview(null) }}
          placeholder="或输入 emoji / 图片 URL"
          style={{
            flex: 1, padding: '9px 12px',
            background: 'var(--bg-secondary)', border: '1px solid var(--border)',
            borderRadius: 8, fontSize: 13, color: 'var(--text-primary)',
            outline: 'none', fontFamily: 'inherit',
          }}
        />
        <input ref={fileRef} type="file" accept="image/*" onChange={handleUpload} style={{ display: 'none' }} />
      </div>
    </div>
  )
}

export default function SettingsPanel({ onClose, defaultTab, editAgentId }) {
  const theme = useThemeStore((s) => s.theme)
  const toggleTheme = useThemeStore((s) => s.toggleTheme)
  const activeId = useChatStore((s) => s.activeConversationId)
  const clearMessages = useChatStore((s) => s.clearMessages)

  const [tab, setTab] = useState(defaultTab || 'llm') // 'llm' | 'quality' | 'prompt'
  const [provider, setProvider] = useState('openai')
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [temperature, setTemperature] = useState(0.5)
  const [maxTokens, setMaxTokens] = useState(8192)
  const [configured, setConfigured] = useState(false)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [securityToken, setSecurityToken] = useState(localStorage.getItem('agenthub_api_secret') || '')
  const [showToken, setShowToken] = useState(false)
  const [activeProvider, setActiveProvider] = useState('')
  const [activeModel, setActiveModel] = useState('')
  const [highlightPresets, setHighlightPresets] = useState(false)
  const [testingLlm, setTestingLlm] = useState(false)
  const [llmTestMsg, setLlmTestMsg] = useState(null) // { success, response/error }
  const presetsRef = useRef(null)

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
    if (tab === 'knowledge') fetchKnowledgeDocs()
    if (tab === 'other') { fetchRuntimeTools(); fetchKnowledgeDocs() }
    if (tab === 'adapters') { fetchAdapters(); fetchProxyStatus() }
  }, [tab])

  // Knowledge base state
  const [kbDocs, setKbDocs] = useState([])
  const [kbLoading, setKbLoading] = useState(false)
  const [kbStats, setKbStats] = useState({})
  const [kbUploading, setKbUploading] = useState(false)
  const [kbQuery, setKbQuery] = useState('')
  const [kbResults, setKbResults] = useState(null)

  const fetchKnowledgeDocs = async () => {
    setKbLoading(true)
    try {
      const resp = await fetch('/api/knowledge')
      const d = await resp.json()
      if (d.status === 'ok') {
        setKbDocs(d.docs || [])
        setKbStats(d.stats || {})
      }
    } catch (e) {
      console.error("Failed to fetch knowledge docs:", e)
    }
    setKbLoading(false)
  }

  const handleKbUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setKbUploading(true)
    setMsg('')
    try {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await fetch('/api/knowledge/upload', { method: 'POST', body: formData })
      const d = await resp.json()
      if (d.status === 'ok') {
        setMsg(`文档入库成功！生成 ${d.chunk_count} 个知识块`)
        fetchKnowledgeDocs()
      } else {
        setMsg('上传失败：' + d.message)
      }
    } catch {
      setMsg('上传失败，请检查后端')
    }
    setKbUploading(false)
    e.target.value = ''
  }

  const handleKbDelete = async (docId) => {
    setSaving(true)
    try {
      await fetch(`/api/knowledge/${docId}`, { method: 'DELETE' })
      fetchKnowledgeDocs()
    } catch {}
    setSaving(false)
  }

  const handleKbQuery = async () => {
    if (!kbQuery.trim()) return
    setSaving(true)
    try {
      const resp = await fetch('/api/knowledge/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: kbQuery, top_k: 5 })
      })
      const d = await resp.json()
      if (d.status === 'ok') setKbResults(d.results || [])
    } catch {}
    setSaving(false)
  }

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
        setActiveProvider(d.provider || '')
        setActiveModel(d.model || '')
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
      if (d.configured) {
        setActiveProvider(provider)
        setActiveModel(model)
        if (provider !== 'ollama') setApiKey('')
      }
    } catch {
      setMsg('保存失败，请检查后端是否运行')
    }
    setSaving(false)
  }

  const handleTestLlm = async () => {
    setTestingLlm(true)
    setLlmTestMsg(null)
    try {
      const resp = await fetch('/api/settings/llm/test', { method: 'POST' })
      const data = await resp.json()
      setLlmTestMsg(data)
    } catch {
      setLlmTestMsg({ success: false, error: '网络错误，请检查后端是否运行' })
    }
    setTestingLlm(false)
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

  // Runtime tools state
  const [rtTools, setRtTools] = useState([])
  const [rtLoading, setRtLoading] = useState(false)
  const [rtTestName, setRtTestName] = useState('')
  const [rtTestParams, setRtTestParams] = useState('')
  const [rtTestResult, setRtTestResult] = useState(null)

  const fetchRuntimeTools = async () => {
    setRtLoading(true)
    try {
      const resp = await fetch('/api/runtime-tools')
      const d = await resp.json()
      setRtTools(d || [])
    } catch (e) {
      console.error("Failed to fetch runtime tools:", e)
    }
    setRtLoading(false)
  }

  const handleToggleRtTool = async (toolName) => {
    try {
      await fetch(`/api/runtime-tools/${toolName}/toggle`, { method: 'POST' })
      fetchRuntimeTools()
    } catch {}
  }

  const handleTestRtTool = async () => {
    if (!rtTestName) return
    setSaving(true)
    setRtTestResult(null)
    try {
      let params = {}
      if (rtTestParams.trim()) {
        params = JSON.parse(rtTestParams)
      }
      const resp = await fetch(`/api/runtime-tools/${rtTestName}/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params)
      })
      const d = await resp.json()
      setRtTestResult(d)
    } catch (e) {
      setRtTestResult({ error: '请求失败: ' + e.message })
    }
    setSaving(false)
  }

  const providerLabels = {
    ollama: 'Ollama 本地',
    openai: 'OpenAI 兼容',
    anthropic: 'Anthropic',
  }

  const getProviderDisplayName = (prov, mdl) => {
    const match = presets.find((p) => p.base_url === baseUrl && p.provider === prov)
    if (match) return `${match.label} (${mdl || match.model})`
    return `${providerLabels[prov] || prov} (${mdl || '...'})`
  }

  const handleDisconnect = async () => {
    setSaving(true)
    try {
      await fetch('/api/settings/llm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: 'openai', api_key: '', base_url: '', model: '' }),
      })
      setConfigured(false)
      setActiveProvider('')
      setActiveModel('')
      setProvider('openai')
      setBaseUrl('')
      setModel('')
      setApiKey('')
      setMsg('已断开 LLM 连接，Agent 将使用 Mock 回复')
    } catch {
      setMsg('断开失败')
    }
    setSaving(false)
  }

  const handleClearHistory = async () => {
    if (!activeId) return
    if (!window.confirm('确定要清空当前会话的全部历史消息吗？此操作不可撤销。')) return
    try {
      await fetch(`/api/conversations/${activeId}/messages`, { method: 'DELETE' })
      clearMessages(activeId)
    } catch {}
  }

  const tabs = [
    { id: 'llm', label: 'LLM 模型' },
    { id: 'adapters', label: '外部 Agent' },
    { id: 'quality', label: '质量门' },
    { id: 'prompt', label: 'Prompt 分层' },
    { id: 'cron', label: '📅 自治' },
    { id: 'security', label: '🔒 安全' },
    { id: 'other', label: '其他' },
  ]

  // ---- Adapters state ----
  const [adapters, setAdapters] = useState([])
  const [adapterLoading, setAdapterLoading] = useState(false)
  const [adapterMsg, setAdapterMsg] = useState('')
  const [adapterEditing, setAdapterEditing] = useState(null) // agent_id being edited
  const [adapterForm, setAdapterForm] = useState({ api_key: '', api_url: '', model: '', tool_mode: 'agent', bot_id: '', user_id: '', platform: 'opencode', display_name: '', display_avatar: '', display_desc: '' })
  const [testingAdapter, setTestingAdapter] = useState(null)
  const [proxyRunning, setProxyRunning] = useState(false)
  const [proxyLoading, setProxyLoading] = useState(false)

  // 自动打开指定 Agent 的编辑表单
  useEffect(() => {
    if (editAgentId && tab === 'adapters') {
      if (adapters.length === 0) {
        fetchAdapters()
        return
      }
      const adapter = adapters.find((a) => a.agent_id === editAgentId)
      if (adapter) {
        setAdapterEditing(editAgentId)
        setAdapterForm({
          api_key: '',
          api_url: '',
          model: adapter.model || '',
          tool_mode: adapter.tool_mode || 'agent',
          bot_id: adapter.extra?.bot_id || '',
          user_id: adapter.extra?.user_id || '',
          platform: adapter.extra?.platform || 'opencode',
          display_name: adapter.display_name || '',
          display_avatar: adapter.display_avatar || '',
          display_desc: adapter.display_desc || '',
        })
      }
    }
  }, [editAgentId, tab, adapters])

  const ADAPTER_META = {
    claude_code: {
      name: 'Claude Code',
      icon: '/avatars/claude-code.svg',
      description: 'Anthropic 最强代码 Agent，支持原生工具调用',
      fields: [
        { key: 'api_key', label: 'API Key', placeholder: 'sk-...', type: 'password' },
        { key: 'api_url', label: 'API 地址（可选，中转站填这里）', placeholder: '请输入 API 地址', type: 'text' },
        { key: 'model', label: '模型', placeholder: '请输入模型名称', type: 'text' },
        { key: 'tool_mode', label: '工具模式', type: 'select', options: [
          { value: 'agent', label: 'Agent 回复（调用 Agent API，需 Agent 平台 Key）' },
          { value: 'text', label: 'LLM 回复（调用通用模型 API，需模型 Key）' },
          { value: 'auto', label: '自动探测（根据模型判断）' },
        ]},
      ],
      helpUrl: 'https://console.anthropic.com/settings/keys',
    },
    codex: {
      name: 'Codex',
      icon: '/avatars/codex.svg',
      description: 'OpenAI 兼容 Chat Completions API（支持 DeepSeek/Qwen 等国产模型）',
      fields: [
        { key: 'api_key', label: 'API Key', placeholder: 'sk-...', type: 'password' },
        { key: 'api_url', label: 'API 地址', placeholder: '请输入 API 地址', type: 'text' },
        { key: 'model', label: '模型', placeholder: '请输入模型名称', type: 'text' },
        { key: 'tool_mode', label: '工具模式', type: 'select', options: [
          { value: 'agent', label: 'Agent 回复（调用 Agent API，需 Agent 平台 Key）' },
          { value: 'text', label: 'LLM 回复（调用通用模型 API，需模型 Key）' },
          { value: 'auto', label: '自动探测（根据模型判断）' },
        ]},
      ],
      helpUrl: 'https://platform.openai.com/api-keys',
    },
    coze: {
      name: 'Coze',
      icon: null,
      description: '字节跳动 Agent 平台，支持插件和工作流',
      fields: [
        { key: 'api_key', label: 'Coze API Key', placeholder: 'pat_...', type: 'password' },
        { key: 'bot_id', label: 'Bot ID', placeholder: '输入 Coze Bot ID', type: 'text' },
        { key: 'user_id', label: 'User ID', placeholder: 'agenthub_user', type: 'text' },
        { key: 'api_url', label: 'API 地址（可选）', placeholder: 'https://api.coze.cn', type: 'text' },
      ],
      helpUrl: 'https://www.coze.cn/docs/guides/authentication',
      docUrl: 'https://acnhwabh9muv.feishu.cn/wiki/PDYlwz6Axi0FHQkTsz0coRydn6g?from=from_copylink',
    },
    self_deployed: {
      name: '本地 Agent',
      icon: null,
      description: '自部署 Agent — 支持 OpenCode、Dify、自定义 HTTP 服务等',
      fields: [
        { key: 'display_name', label: 'Agent 名称', placeholder: '我的本地 Agent', type: 'text' },
        { key: 'display_avatar', label: '头像', placeholder: '输入 emoji 或图片 URL', type: 'text' },
        { key: 'display_desc', label: '简介', placeholder: '简短描述 Agent 的功能', type: 'text' },
        { key: 'api_url', label: '服务地址', placeholder: 'http://localhost:4097/v1/chat/completions', type: 'text' },
        { key: 'api_key', label: 'API Key（可选）', placeholder: '如需认证填入', type: 'password' },
        { key: 'model', label: '模型名（可选）', placeholder: '如需指定模型填入', type: 'text' },
        { key: 'platform', label: '平台类型', type: 'select', options: [
          { value: 'opencode', label: 'OpenCode（OpenAI 兼容格式）' },
          { value: 'dify', label: 'Dify' },
          { value: 'generic', label: '通用 HTTP 服务' },
        ]},
      ],
      helpUrl: '',
    },
  }

  const fetchAdapters = async () => {
    setAdapterLoading(true)
    try {
      const resp = await fetch('/api/adapters')
      const data = await resp.json()
      setAdapters(data.adapters || [])
    } catch {}
    setAdapterLoading(false)
  }

  const fetchProxyStatus = async () => {
    try {
      const resp = await fetch('/api/proxy/status')
      const data = await resp.json()
      setProxyRunning(data.running || false)
    } catch {}
  }

  const handleStartProxy = async () => {
    setProxyLoading(true)
    try {
      const resp = await fetch('/api/proxy/start', { method: 'POST' })
      const data = await resp.json()
      if (data.status === 'started' || data.status === 'already_running') {
        setProxyRunning(true)
        setAdapterMsg(`本地 Agent 代理已启动 (端口 ${data.port})`)
      } else {
        setAdapterMsg(`启动失败: ${data.error || '未知错误'}`)
      }
    } catch {
      setAdapterMsg('启动失败，请检查后端是否运行')
    }
    setProxyLoading(false)
    setTimeout(() => setAdapterMsg(''), 5000)
  }

  const handleStopProxy = async () => {
    setProxyLoading(true)
    try {
      await fetch('/api/proxy/stop', { method: 'POST' })
      setProxyRunning(false)
      setAdapterMsg('本地 Agent 代理已停止')
    } catch {
      setAdapterMsg('停止失败')
    }
    setProxyLoading(false)
    setTimeout(() => setAdapterMsg(''), 3000)
  }

  const handleSaveAdapter = async (agentId) => {
    const meta = ADAPTER_META[agentId]
    if (!meta) return
    const adapterType = agentId === 'claude_code' ? 'claude' : agentId === 'codex' ? 'codex' : agentId === 'coze' ? 'coze' : 'self_deployed'
    const extra = {}
    if (agentId === 'coze') {
      if (adapterForm.bot_id) extra.bot_id = adapterForm.bot_id
      if (adapterForm.user_id) extra.user_id = adapterForm.user_id
    }
    if (agentId === 'self_deployed') {
      if (adapterForm.platform) extra.platform = adapterForm.platform
    }
    try {
      const resp = await fetch('/api/adapters', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent_id: agentId,
          adapter_type: adapterType,
          name: meta.name,
          api_key: adapterForm.api_key,
          api_url: adapterForm.api_url,
          model: adapterForm.model,
          tool_mode: adapterForm.tool_mode || 'agent',
          extra,
          display_name: adapterForm.display_name || '',
          display_avatar: adapterForm.display_avatar || '',
          display_desc: adapterForm.display_desc || '',
        }),
      })
      const data = await resp.json()
      if (data.status === 'ok') {
        setAdapterMsg(`${meta.name} 配置已保存`)
        setAdapterEditing(null)
        setAdapterForm({ api_key: '', api_url: '', model: '', tool_mode: 'agent', bot_id: '', user_id: '', platform: 'opencode', display_name: '', display_avatar: '', display_desc: '' })
        fetchAdapters()
      } else {
        setAdapterMsg(`保存失败: ${data.error || '未知错误'}`)
      }
    } catch {
      setAdapterMsg('保存失败，请检查后端是否运行')
    }
    setTimeout(() => setAdapterMsg(''), 3000)
  }

  const handleTestAdapter = async (agentId) => {
    setTestingAdapter(agentId)
    try {
      const resp = await fetch(`/api/adapters/${agentId}/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: '你好，请简单介绍一下你自己。' }),
      })
      const data = await resp.json()
      const isError = data.status === 'error' || data.error || (data.response && data.response.includes('错误'))
      if (data.status === 'ok' && !isError) {
        setAdapterMsg(`✅ 测试成功: ${data.response?.slice(0, 100) || '正常响应'}`)
      } else {
        setAdapterMsg(`❌ 测试失败: ${data.error || data.response || '未知错误'}`)
      }
    } catch {
      setAdapterMsg('测试失败，请检查网络连接')
    }
    setTestingAdapter(null)
    setTimeout(() => setAdapterMsg(''), 5000)
  }

  // Light theme styles
  const labelStyle = {
    fontSize: 13,
    color: 'var(--text-secondary)',
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
    background: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
  }

  const btnStyle = {
    width: '100%',
    padding: '12px',
    borderRadius: 10,
    background: 'var(--accent)',
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
    background: 'var(--bg-primary)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--text-primary)',
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
      <div className="settings-modal-scroll" style={{
        width: 500, maxHeight: '88vh', overflow: 'auto',
        background: 'var(--bg-primary)',
        border: '1px solid var(--border)',
        borderRadius: 16, padding: 28,
        boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
        scrollbarWidth: 'none', msOverflowStyle: 'none',
      }} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 18, color: 'var(--text-primary)', fontWeight: 600 }}>设置</h2>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: 'var(--text-muted)',
            fontSize: 20, cursor: 'pointer', padding: '0 4px',
          }}>×</button>
        </div>

        {/* 常规设置：主题切换 + 清空历史 */}
        <div style={{ marginBottom: 20, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {/* 主题切换 */}
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '12px 14px', borderRadius: 10,
            background: 'var(--bg-secondary)', border: '1px solid var(--border)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {theme === 'light' ? <Sun size={16} color="var(--orange)" /> : <Moon size={16} color="var(--accent)" />}
              <div>
                <div style={{ fontSize: 14, color: 'var(--text-primary)', fontWeight: 500 }}>界面主题</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  {theme === 'light' ? '浅色模式' : '深色模式'}
                </div>
              </div>
            </div>
            <ToggleSwitch checked={theme === 'dark'} onChange={() => toggleTheme()} />
          </div>

          {/* 清空历史 */}
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '12px 14px', borderRadius: 10,
            background: 'var(--bg-secondary)', border: '1px solid var(--border)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Trash2 size={16} color="var(--red)" />
              <div>
                <div style={{ fontSize: 14, color: 'var(--text-primary)', fontWeight: 500 }}>清空当前会话历史</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>删除所有消息，不可恢复</div>
              </div>
            </div>
            <button
              onClick={handleClearHistory}
              style={{
                padding: '6px 14px', borderRadius: 8, fontSize: 12,
                background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.25)',
                color: 'var(--red)', cursor: 'pointer', fontWeight: 500,
              }}
            >
              清空
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 24, background: 'var(--bg-tertiary)', borderRadius: 10, padding: 4 }}>
          {tabs.map((t) => (
            <button key={t.id} onClick={() => { setTab(t.id); setMsg('') }} style={{
              flex: 1, padding: '8px 12px', borderRadius: 8, fontSize: 12,
              background: tab === t.id ? 'var(--accent)' : 'transparent',
              border: 'none', color: tab === t.id ? 'white' : 'var(--text-secondary)',
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
        )}

        {/* ====== TAB: Adapters (外部 Agent) ====== */}
        {tab === 'adapters' && (
          <>
            <div style={{ padding: '12px 14px', borderRadius: 8, marginBottom: 20, background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)', fontSize: 12, color: 'var(--accent)', lineHeight: 1.8 }}>
              配置 API Key 即可启用外部 Agent。<br />
              「Agent 回复」— 调用 Agent 平台 API（如 Claude Code、Coze），具备工具调用、多轮推理等完整能力，需 Agent 平台 Key。<br />
              「LLM 回复」— 调用通用大模型 API（如 DeepSeek、Qwen），仅做纯文本对话，需模型 Key。<br />
              「自动探测」— 根据模型名和地址自动判断。
            </div>

            {adapterMsg && (
              <div style={{
                padding: '10px 14px', borderRadius: 8, marginBottom: 16, fontSize: 13,
                background: adapterMsg.startsWith('✅') ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)',
                border: `1px solid ${adapterMsg.startsWith('✅') ? 'rgba(16, 185, 129, 0.25)' : 'rgba(239, 68, 68, 0.25)'}`,
                color: adapterMsg.startsWith('✅') ? 'var(--green)' : 'var(--red)',
              }}>{adapterMsg}</div>
            )}

            {Object.entries(ADAPTER_META).map(([agentId, meta]) => {
              const adapter = adapters.find((a) => a.agent_id === agentId)
              const isConfigured = adapter?.configured ?? false
              const isEditing = adapterEditing === agentId

              return (
                <div key={agentId} style={{
                  border: '1px solid var(--border)', borderRadius: 12, marginBottom: 16,
                  overflow: 'hidden',
                }}>
                  {/* 头部 */}
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 12, padding: '14px 16px',
                    background: isConfigured ? 'rgba(16, 185, 129, 0.06)' : 'var(--bg-secondary)',
                    borderBottom: isEditing ? '1px solid var(--border)' : 'none',
                  }}>
                    <div style={{
                      width: 36, height: 36, borderRadius: 8,
                      background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      overflow: 'hidden', flexShrink: 0,
                    }}>
                      <IconAvatar agentId={agentId} size={20} />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{meta.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 1 }}>{meta.description}</div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                      {isConfigured ? (
                        <span style={{ fontSize: 11, color: 'var(--green)', display: 'flex', alignItems: 'center', gap: 4 }}>
                          <Check size={12} /> 已配置
                        </span>
                      ) : (
                        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>未配置</span>
                      )}
                      {agentId === 'self_deployed' && (
                        <button
                          onClick={() => proxyRunning ? handleStopProxy() : handleStartProxy()}
                          disabled={proxyLoading}
                          style={{
                            padding: '4px 10px', borderRadius: 6, fontSize: 11,
                            background: proxyRunning ? 'rgba(239, 68, 68, 0.1)' : 'rgba(16, 185, 129, 0.1)',
                            border: `1px solid ${proxyRunning ? 'rgba(239, 68, 68, 0.3)' : 'rgba(16, 185, 129, 0.3)'}`,
                            color: proxyRunning ? 'var(--red, #ef4444)' : 'var(--green)',
                            cursor: proxyLoading ? 'default' : 'pointer',
                            fontWeight: 500,
                          }}
                        >
                          {proxyLoading ? '处理中...' : proxyRunning ? '停止代理' : '启动代理'}
                        </button>
                      )}
                      <button
                        onClick={() => {
                          if (isEditing) {
                            setAdapterEditing(null)
                            setAdapterForm({ api_key: '', api_url: '', model: '', tool_mode: 'agent', bot_id: '', user_id: '', platform: 'opencode', display_name: '', display_avatar: '', display_desc: '' })
                          } else {
                            setAdapterEditing(agentId)
                            setAdapterForm({
                              api_key: '',
                              api_url: '',
                              model: adapter?.model || '',
                              tool_mode: adapter?.tool_mode || 'agent',
                              bot_id: adapter?.extra?.bot_id || '',
                              user_id: adapter?.extra?.user_id || '',
                              platform: adapter?.extra?.platform || 'opencode',
                              display_name: adapter?.display_name || '',
                              display_avatar: adapter?.display_avatar || '',
                              display_desc: adapter?.display_desc || '',
                            })
                          }
                        }}
                        style={{
                          padding: '5px 12px', borderRadius: 6, fontSize: 12,
                          background: isEditing ? 'var(--bg-tertiary)' : 'var(--accent)',
                          border: isEditing ? '1px solid var(--border)' : '1px solid var(--accent)',
                          color: isEditing ? 'var(--text-secondary)' : 'white',
                          cursor: 'pointer', fontWeight: 500,
                        }}
                      >
                        {isEditing ? '取消' : isConfigured ? '修改' : '配置'}
                      </button>
                    </div>
                  </div>

                  {/* 编辑表单 */}
                  {isEditing && (
                    <div style={{ padding: '16px', background: 'var(--bg-primary)' }}>
                      {meta.fields.map((field) => (
                        <div key={field.key} style={{ marginBottom: 12 }}>
                          <label style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4, display: 'block', fontWeight: 500 }}>
                            {field.label}
                          </label>
                          {field.key === 'display_avatar' && (agentId === 'self_deployed' || agentId.startsWith('local_agent_')) ? (
                            <AvatarUploadField
                              value={adapterForm.display_avatar}
                              onChange={(val) => setAdapterForm({ ...adapterForm, display_avatar: val })}
                            />
                          ) : field.type === 'select' ? (
                            <select
                              value={adapterForm[field.key] || field.options[0]?.value || ''}
                              onChange={(e) => setAdapterForm({ ...adapterForm, [field.key]: e.target.value })}
                              style={{
                                width: '100%', padding: '9px 12px',
                                background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                                borderRadius: 8, fontSize: 13, color: 'var(--text-primary)',
                                outline: 'none', fontFamily: 'inherit',
                              }}
                            >
                              {field.options.map((opt) => (
                                <option key={opt.value} value={opt.value}>{opt.label}</option>
                              ))}
                            </select>
                          ) : (
                            <input
                              type={field.type}
                              value={adapterForm[field.key]}
                              onChange={(e) => setAdapterForm({ ...adapterForm, [field.key]: e.target.value })}
                              placeholder={field.placeholder}
                              style={{
                                width: '100%', padding: '9px 12px',
                                background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                                borderRadius: 8, fontSize: 13, color: 'var(--text-primary)',
                                outline: 'none', fontFamily: 'inherit',
                              }}
                            />
                          )}
                        </div>
                      ))}
                      <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                        <button
                          onClick={() => handleSaveAdapter(agentId)}
                          style={{
                            padding: '8px 20px', borderRadius: 8, fontSize: 13,
                            background: 'var(--accent)', border: 'none', color: 'white',
                            cursor: 'pointer', fontWeight: 600,
                          }}
                        >
                          保存配置
                        </button>
                        {isConfigured && (
                          <button
                            onClick={() => handleTestAdapter(agentId)}
                            disabled={testingAdapter === agentId}
                            style={{
                              padding: '8px 16px', borderRadius: 8, fontSize: 13,
                              background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.25)',
                              color: 'var(--green)', cursor: 'pointer', fontWeight: 500,
                              display: 'flex', alignItems: 'center', gap: 4,
                            }}
                          >
                            {testingAdapter === agentId ? (
                              <><Loader size={12} style={{ animation: 'spin 1s linear infinite' }} /> 测试中...</>
                            ) : '测试连接'}
                          </button>
                        )}
                        <a
                          href={meta.helpUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            padding: '8px 16px', borderRadius: 8, fontSize: 13,
                            background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
                            color: 'var(--text-secondary)', cursor: 'pointer', fontWeight: 500,
                            textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4,
                          }}
                        >
                          <ExternalLink size={12} /> 获取 Key
                        </a>
                        {meta.docUrl && (
                          <a
                            href={meta.docUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              padding: '8px 16px', borderRadius: 8, fontSize: 13,
                              background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
                              color: 'var(--text-secondary)', cursor: 'pointer', fontWeight: 500,
                              textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4,
                            }}
                          >
                            <ExternalLink size={12} /> 配置文档
                          </a>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </>
        )}

        {/* ====== TAB: Quality Gate ====== */}
        {tab === 'quality' && (
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
        )}

        {/* ====== TAB: Prompt Layers ====== */}
        {tab === 'prompt' && (
          <>
            <div style={{ padding: '12px 14px', borderRadius: 8, marginBottom: 20, background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)', fontSize: 12, color: 'var(--accent)' }}>
              Prompt 按层级注入，每层可独立开关。高层级（约束）优先级最高。
            </div>

            {layers.map((layer) => (
              <div key={layer.id} style={{
                ...rowStyle,
                marginBottom: 10, padding: '12px 14px', borderRadius: 10,
                background: layer.enabled ? 'var(--bg-secondary)' : 'var(--bg-tertiary)',
                border: `1px solid ${layer.enabled ? 'var(--border)' : 'var(--border)'}`,
                opacity: layer.enabled ? 1 : 0.5,
              }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>
                    <span style={{ fontSize: 11, color: 'var(--accent)', marginRight: 6 }}>L{layer.level}</span>
                    {layer.id}
                    {layer.has_condition && <span style={{ fontSize: 10, color: 'var(--orange)', marginLeft: 6 }}>条件注入</span>}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 3 }}>
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
              background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)',
              fontSize: 13, color: 'var(--accent)', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
              <span>Always-on 离线常驻自治 — 网页关闭后 Agent 仍能后台自主开发</span>
              <button onClick={fetchCronTasks} disabled={cronLoading} style={{
                padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                background: 'var(--accent)', color: 'white', border: 'none', cursor: 'pointer',
                opacity: cronLoading ? 0.6 : 1,
              }}>{cronLoading ? '...' : '刷新'}</button>
            </div>

            {/* Task List */}
            <div style={{ marginBottom: 20 }}>
              <label style={labelStyle}>当前后台自治作业</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: '25vh', overflowY: 'auto' }}>
                {cronTasks.length === 0 ? (
                  <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '16px 0', fontSize: 12 }}>
                    暂无活动中的后台自治作业
                  </div>
                ) : (
                  cronTasks.map((t) => (
                    <div key={t.id} style={{
                      padding: '10px 14px', borderRadius: 10, background: 'var(--bg-secondary)',
                      border: `1px solid ${t.status === 'running' ? 'var(--accent)' : t.status === 'active' ? 'rgba(16, 185, 129, 0.25)' : 'rgba(245, 158, 11, 0.2)'}`,
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
                          {t.status === 'running' ? '🔵' : t.status === 'active' ? '🟢' : '🟡'} {t.agent_id}
                        </span>
                        <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>每 {t.interval_seconds}s</span>
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>{t.task_prompt.slice(0, 60)}...</div>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button onClick={() => handleToggleCronTask(t.id, t.status)} disabled={saving} style={{
                          padding: '3px 8px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
                          background: 'var(--bg-tertiary)', border: '1px solid var(--border)', color: 'var(--text-secondary)',
                        }}>{t.status === 'active' ? '暂停' : '恢复'}</button>
                        <button onClick={() => handleRunCronTaskNow(t.id)} disabled={saving || t.status === 'running'} style={{
                          padding: '3px 8px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
                          background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)', color: 'var(--accent)',
                        }}>立即执行</button>
                        <button onClick={() => handleDeleteCronTask(t.id)} disabled={saving} style={{
                          padding: '3px 8px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
                          background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.25)', color: 'var(--red)',
                        }}>删除</button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Create Form */}
            <div style={{ padding: '16px', borderRadius: 12, background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
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

        {/* ====== TAB: Other (Tools + Knowledge) ====== */}
        {tab === 'other' && (
          <>
            <div style={{
              padding: '10px 14px', borderRadius: 8, marginBottom: 20,
              background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)',
              fontSize: 13, color: 'var(--accent)',
            }}>
              Agent 可通过 <code>[tool_call:name]</code> 标签调用以下工具，系统自动执行并返回结果
            </div>

            {/* Tool List */}
            <div style={{ marginBottom: 20 }}>
              <label style={labelStyle}>已注册工具 ({rtTools.length})</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {rtLoading ? (
                  <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 16, fontSize: 12 }}>加载中...</div>
                ) : rtTools.length === 0 ? (
                  <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 16, fontSize: 12 }}>暂无工具</div>
                ) : (
                  rtTools.map((tool) => (
                    <div key={tool.name} style={{
                      padding: '12px 14px', borderRadius: 10, background: 'var(--bg-secondary)',
                      border: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                          {tool.icon} {tool.name}
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
                          {tool.description}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <span style={{
                          fontSize: 10, padding: '2px 8px', borderRadius: 4,
                          background: tool.enabled ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)',
                          color: tool.enabled ? 'var(--green)' : 'var(--red)',
                          border: `1px solid ${tool.enabled ? 'rgba(16, 185, 129, 0.25)' : 'rgba(239, 68, 68, 0.25)'}`,
                        }}>{tool.enabled ? '启用' : '禁用'}</span>
                        <button onClick={() => handleToggleRtTool(tool.name)} style={{
                          padding: '4px 10px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
                          background: tool.enabled ? 'rgba(239, 68, 68, 0.08)' : 'rgba(16, 185, 129, 0.08)',
                          border: `1px solid ${tool.enabled ? 'rgba(239, 68, 68, 0.25)' : 'rgba(16, 185, 129, 0.25)'}`,
                          color: tool.enabled ? 'var(--red)' : 'var(--green)',
                        }}>{tool.enabled ? '禁用' : '启用'}</button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Test Tool */}
            <div style={{ padding: '16px', borderRadius: 12, background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
              <label style={{ ...labelStyle, fontWeight: 600, marginBottom: 12 }}>工具测试</label>
              <div style={{ marginBottom: 10 }}>
                <select
                  value={rtTestName}
                  onChange={(e) => setRtTestName(e.target.value)}
                  style={{ ...inputStyle, marginBottom: 8 }}
                >
                  <option value="">选择工具...</option>
                  {rtTools.filter(t => t.enabled).map((t) => (
                    <option key={t.name} value={t.name}>{t.icon} {t.name}</option>
                  ))}
                </select>
                <textarea
                  value={rtTestParams}
                  onChange={(e) => setRtTestParams(e.target.value)}
                  style={{ ...inputStyle, minHeight: 60, resize: 'vertical', fontFamily: 'monospace', fontSize: 12 }}
                  placeholder='参数 JSON，如: {"query": "FastAPI 教程"}'
                />
              </div>
              <button onClick={handleTestRtTool} disabled={saving || !rtTestName} style={{
                ...btnStyle, background: 'var(--green)',
                opacity: (saving || !rtTestName) ? 0.6 : 1,
              }}>执行测试</button>
              {rtTestResult && (
                <div style={{
                  marginTop: 12, padding: '10px', borderRadius: 8,
                  background: rtTestResult.success ? 'rgba(16, 185, 129, 0.06)' : 'rgba(239, 68, 68, 0.08)',
                  border: `1px solid ${rtTestResult.success ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.25)'}`,
                  maxHeight: '25vh', overflowY: 'auto',
                }}>
                  <div style={{ fontSize: 11, color: rtTestResult.success ? 'var(--green)' : 'var(--red)', fontWeight: 600, marginBottom: 4 }}>
                    {rtTestResult.success ? '✅ 成功' : '❌ 失败'} {rtTestResult.usage?.time_ms ? `(${rtTestResult.usage.time_ms}ms)` : ''}
                  </div>
                  <pre style={{
                    fontSize: 11, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                    margin: 0, maxHeight: '20vh', overflow: 'auto',
                  }}>
                    {JSON.stringify(rtTestResult.data || rtTestResult.error, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            {/* ===== 知识库管理 ===== */}
            <div style={{
              padding: '10px 14px', borderRadius: 8, marginBottom: 20,
              background: 'rgba(16, 185, 129, 0.06)', border: '1px solid rgba(16, 185, 129, 0.3)',
              fontSize: 13, color: 'var(--green)', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
              <span>知识库已索引 <b>{kbStats.total_chunks || 0}</b> 个知识块，Agent 回复时自动检索注入</span>
              <button onClick={fetchKnowledgeDocs} disabled={kbLoading} style={{
                padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
                background: 'var(--green)', color: 'white', border: 'none', cursor: 'pointer',
                opacity: kbLoading ? 0.6 : 1,
              }}>{kbLoading ? '...' : '刷新'}</button>
            </div>

            {/* Upload */}
            <div style={{ marginBottom: 20 }}>
              <label style={labelStyle}>上传文档 (支持 txt/md/pdf/docx/json/csv)</label>
              <label style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px',
                borderRadius: 10, border: '2px dashed var(--border)', cursor: 'pointer',
                background: kbUploading ? 'var(--bg-tertiary)' : 'white', transition: 'all 0.2s',
              }}>
                <input type="file" accept=".txt,.md,.pdf,.docx,.json,.csv" onChange={handleKbUpload} style={{ display: 'none' }} />
                <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                  {kbUploading ? '正在处理...' : '点击选择文件上传到知识库'}
                </span>
              </label>
            </div>

            {/* Document List */}
            <div style={{ marginBottom: 20 }}>
              <label style={labelStyle}>已入库文档</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: '25vh', overflowY: 'auto' }}>
                {kbDocs.length === 0 ? (
                  <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '16px 0', fontSize: 12 }}>
                    暂无文档，请上传文件到知识库
                  </div>
                ) : (
                  kbDocs.map((doc) => (
                    <div key={doc.id} style={{
                      padding: '10px 14px', borderRadius: 10, background: 'var(--bg-secondary)',
                      border: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    }}>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>{doc.filename}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                          {doc.chunk_count} 块 | {doc.char_count} 字符
                        </div>
                      </div>
                      <button onClick={() => handleKbDelete(doc.id)} disabled={saving} style={{
                        padding: '4px 10px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
                        background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.25)', color: 'var(--red)',
                      }}>删除</button>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Test Query */}
            <div style={{ padding: '16px', borderRadius: 12, background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
              <label style={{ ...labelStyle, fontWeight: 600, marginBottom: 12 }}>检索测试</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  value={kbQuery}
                  onChange={(e) => setKbQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleKbQuery()}
                  style={{ ...inputStyle, flex: 1 }}
                  placeholder="输入查询语句测试知识库检索..."
                />
                <button onClick={handleKbQuery} disabled={saving || !kbQuery.trim()} style={{
                  padding: '8px 16px', borderRadius: 8, background: 'var(--accent)',
                  border: 'none', color: 'white', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                  opacity: saving ? 0.6 : 1,
                }}>检索</button>
              </div>
              {kbResults && (
                <div style={{ marginTop: 12, maxHeight: '20vh', overflowY: 'auto' }}>
                  {kbResults.length === 0 ? (
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: 8 }}>未找到相关内容</div>
                  ) : (
                    kbResults.map((r, i) => (
                      <div key={i} style={{
                        padding: '8px 10px', borderRadius: 6, background: 'var(--bg-primary)', border: '1px solid var(--border)',
                        marginBottom: 6, fontSize: 12, color: 'var(--text-secondary)',
                      }}>
                        <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginBottom: 4 }}>
                          相关度: {r.score} | 来源: {r.metadata?.filename || '未知'}
                        </div>
                        {r.text?.slice(0, 200)}{r.text?.length > 200 ? '...' : ''}
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          </>
        )}

        {/* ====== TAB: Security & Authentication ====== */}
        {tab === 'security' && (
          <>
            <div style={{
              padding: '10px 14px', borderRadius: 8, marginBottom: 20,
              background: 'rgba(245, 158, 11, 0.15)', border: '1px solid rgba(245, 158, 11, 0.2)',
              fontSize: 13, color: 'var(--orange)',
            }}>
              🔒 全局安全门禁与 API/WebSocket 会话密钥管理
            </div>

            <div style={{ padding: '16px', borderRadius: 12, background: 'var(--bg-secondary)', border: '1px solid var(--border)', marginBottom: 20 }}>
              <label style={{ ...labelStyle, fontWeight: 600, marginBottom: 12 }}>API Secret 密钥配置</label>
              
              <div style={{ marginBottom: 16 }}>
                <label style={labelStyle}>全局访问密钥 (AGENTHUB_API_SECRET)</label>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    value={securityToken}
                    onChange={(e) => setSecurityToken(e.target.value)}
                    type={showToken ? "text" : "password"}
                    placeholder="输入系统接口鉴权 Token..."
                    style={{ ...inputStyle, flex: 1 }}
                  />
                  <button
                    onClick={() => setShowToken(!showToken)}
                    style={{
                      padding: '10px 12px',
                      background: 'var(--bg-tertiary)',
                      border: '1px solid var(--border)',
                      borderRadius: 8,
                      cursor: 'pointer',
                      fontSize: 14,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center'
                    }}
                    type="button"
                    title={showToken ? "隐藏密码" : "显示密码"}
                  >
                    {showToken ? '👁️' : '👁️‍🗨️'}
                  </button>
                </div>
                <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6, lineHeight: 1.4 }}>
                  密钥将保存在您的浏览器本地 LocalStorage 中。在开启后端 <code>AGENTHUB_API_SECRET</code> 保护时，前端所有的 Fetch 和 WebSocket 请求将自动注入此凭证以完成双向身份鉴权。
                </p>
              </div>

              <div style={{ display: 'flex', gap: 10 }}>
                <button
                  onClick={() => {
                    localStorage.setItem('agenthub_api_secret', securityToken);
                    setMsg('安全凭证保存成功！所有 API 与实时会话已安全对齐。');
                  }}
                  style={{ ...btnStyle, flex: 1, background: 'var(--accent)' }}
                >
                  保存密钥
                </button>
                <button
                  onClick={() => {
                    localStorage.removeItem('agenthub_api_secret');
                    setSecurityToken('');
                    setMsg('安全凭证已成功清除，浏览器当前处于无凭证访问状态。');
                  }}
                  style={{ ...btnStyle, flex: 1, background: 'var(--bg-tertiary)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
                >
                  清除密钥
                </button>
              </div>
            </div>

            <div style={{ padding: '14px', borderRadius: 10, background: 'var(--bg-secondary)', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              <b>💡 物理安全说明：</b>
              <br />
              - 当密钥清除且后端未设置密钥时，系统默认激活 <b>Localhost 纯物理环回防火墙</b>，阻止任何外界物理设备访问此编排系统。
              <br />
              - 非 Docker 终端命令执行（RCE防护）已自动接入脚本安全包裹隔离保护。
            </div>
          </>
        )}

        {/* Message */}
        {msg && (
          <div style={{
            marginTop: 16, padding: '10px 14px', borderRadius: 8,
            background: msg.includes('成功') || msg.includes('已保存') ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)',
            border: `1px solid ${msg.includes('成功') || msg.includes('已保存') ? 'rgba(16, 185, 129, 0.25)' : 'rgba(239, 68, 68, 0.25)'}`,
            fontSize: 13, color: msg.includes('成功') || msg.includes('已保存') ? 'var(--green)' : 'var(--red)',
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
      background: checked ? 'var(--accent)' : 'var(--border)',
      border: `1px solid ${checked ? 'var(--accent)' : 'var(--border)'}`,
      position: 'relative', transition: 'all 0.2s', flexShrink: 0,
    }}>
      <div style={{
        width: 18, height: 18, borderRadius: 9,
        background: 'var(--bg-primary)', position: 'absolute', top: 2,
        left: checked ? 22 : 3, transition: 'left 0.2s',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
      }} />
    </div>
  )
}
