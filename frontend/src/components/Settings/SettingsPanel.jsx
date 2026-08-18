import React, { useState, useEffect, useRef } from 'react'
import { Sun, Moon, Trash2 } from 'lucide-react'
import { useThemeStore } from '../../stores/themeStore'
import { useChatStore } from '../../stores/chatStore'
import ToggleSwitch from './ToggleSwitch'
import LLMTab from './LLMTab'
import AdaptersTab from './AdaptersTab'
import QualityGateTab from './QualityGateTab'
import PromptLayersTab from './PromptLayersTab'
import CronTasksTab from './CronTasksTab'
import OtherTab from './OtherTab'
import SecurityTab from './SecurityTab'

export default function SettingsPanel({ onClose, defaultTab, editAgentId }) {
  const theme = useThemeStore((s) => s.theme)
  const toggleTheme = useThemeStore((s) => s.toggleTheme)
  const activeId = useChatStore((s) => s.activeConversationId)
  const clearMessages = useChatStore((s) => s.clearMessages)

  const [tab, setTab] = useState(defaultTab || 'llm')
  const [provider, setProvider] = useState('openai')
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [temperature, setTemperature] = useState(0.5)
  const [maxTokens, setMaxTokens] = useState(8192)
  const [configured, setConfigured] = useState(false)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const [authStatus, setAuthStatus] = useState({ auth_required: true, authenticated: false, user: null })
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [legacyTenants, setLegacyTenants] = useState([])
  const [legacyLoading, setLegacyLoading] = useState(false)
  const [notificationStatus, setNotificationStatus] = useState({ slack: false, telegram: false })
  const [testingNotification, setTestingNotification] = useState('')
  const [activeProvider, setActiveProvider] = useState('')
  const [activeModel, setActiveModel] = useState('')
  const [highlightPresets, setHighlightPresets] = useState(false)
  const [testingLlm, setTestingLlm] = useState(false)
  const [llmTestMsg, setLlmTestMsg] = useState(null)
  const presetsRef = useRef(null)

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
            if (!model || !d.models.includes(model)) { setModel(d.models[0]) }
          } else {
            setOllamaError('未在本地 Ollama 中发现已下载的模型，请先运行 "ollama run <model>"')
          }
        } else { setOllamaError(d.message || '无法获取本地模型列表') }
      })
      .catch(() => { setOllamaError('无法连接到后端或本地 Ollama 服务没有运行') })
      .finally(() => { setOllamaLoading(false) })
  }

  useEffect(() => { if (provider === 'ollama') { fetchOllamaModels() } }, [provider])

  const [qEnabled, setQEnabled] = useState(true)
  const [bestOfN, setBestOfN] = useState(1)
  const [maxRetries, setMaxRetries] = useState(1)
  const [useLlmJudge, setUseLlmJudge] = useState(false)
  const [layers, setLayers] = useState([])

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
    } catch (e) { console.error("Failed to fetch cron tasks:", e) }
    setCronLoading(false)
  }

  const handleAddCronTask = async () => {
    if (!cronPrompt.trim()) return
    setSaving(true); setMsg('')
    try {
      const resp = await fetch('/api/cron', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversation_id: 'conv_pm', agent_id: selectedAgentForCron, task_prompt: cronPrompt, interval_seconds: cronInterval })
      })
      const d = await resp.json()
      if (d.status === 'ok') {
        setMsg('离线自治任务成功创建！')
        setCronPrompt('检查工作区，寻找安全漏洞并重构代码，完毕后运行编译测试并生成 checkpoint 版本。')
        fetchCronTasks()
      } else { setMsg('创建失败：' + d.message) }
    } catch { setMsg('创建失败，请检查后端') }
    setSaving(false)
  }

  const handleToggleCronTask = async (taskId, currentStatus) => {
    setSaving(true)
    try {
      const newStatus = currentStatus === 'active' ? 'paused' : 'active'
      await fetch(`/api/cron/${taskId}/toggle`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: newStatus }) })
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
    try { await fetch(`/api/cron/${taskId}`, { method: 'DELETE' }); fetchCronTasks() } catch {}
    setSaving(false)
  }

  useEffect(() => {
    if (tab === 'cron') fetchCronTasks()
    if (tab === 'knowledge') fetchKnowledgeDocs()
    if (tab === 'other') { fetchRuntimeTools(); fetchKnowledgeDocs() }
    if (tab === 'adapters') { fetchAdapters(); fetchProxyStatus() }
    if (tab === 'security') fetchSecurityStatus()
  }, [tab])

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
      if (d.status === 'ok') { setKbDocs(d.docs || []); setKbStats(d.stats || {}) }
    } catch (e) { console.error("Failed to fetch knowledge docs:", e) }
    setKbLoading(false)
  }

  const handleKbUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setKbUploading(true); setMsg('')
    try {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await fetch('/api/knowledge/upload', { method: 'POST', body: formData })
      const d = await resp.json()
      if (d.status === 'ok') { setMsg(`文档入库成功！生成 ${d.chunk_count} 个知识块`); fetchKnowledgeDocs() }
      else { setMsg('上传失败：' + d.message) }
    } catch { setMsg('上传失败，请检查后端') }
    setKbUploading(false); e.target.value = ''
  }

  const handleKbDelete = async (docId) => {
    setSaving(true); setMsg('')
    try {
      const resp = await fetch(`/api/knowledge/__default__/files/${docId}`, { method: 'DELETE' })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) throw new Error(data.detail || '删除失败')
      await fetchKnowledgeDocs()
      setMsg('知识库文档已删除')
    } catch (error) {
      setMsg(`删除失败：${error.message}`)
    }
    setSaving(false)
  }

  const handleKbQuery = async () => {
    if (!kbQuery.trim()) return
    setSaving(true)
    try {
      const resp = await fetch('/api/knowledge/query', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: kbQuery, top_k: 5 }) })
      const d = await resp.json()
      if (d.status === 'ok') setKbResults(d.results || [])
    } catch {}
    setSaving(false)
  }

  const fetchSecurityStatus = async () => {
    try {
      const resp = await fetch('/api/auth/status')
      const status = await resp.json()
      setAuthStatus(status)
      if (status.authenticated) {
        const channelResp = await fetch('/api/webhook/channels')
        if (channelResp.ok) {
          const channels = await channelResp.json()
          setNotificationStatus(channels.channels || {})
        }
        if (status.user?.is_admin) {
          setLegacyLoading(true)
          const legacyResp = await fetch('/api/admin/legacy-tenants')
          const legacyData = await legacyResp.json().catch(() => ({}))
          if (legacyResp.ok) setLegacyTenants(legacyData.tenants || [])
          setLegacyLoading(false)
        }
      }
    } catch { setMsg('无法读取安全状态') }
  }

  const handleChangePassword = async (event) => {
    event.preventDefault()
    if (newPassword !== confirmPassword) {
      setMsg('两次输入的新密码不一致')
      return
    }
    setSaving(true); setMsg('')
    try {
      const resp = await fetch('/api/auth/change-password', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) throw new Error(data.detail || '修改密码失败')
      setCurrentPassword(''); setNewPassword(''); setConfirmPassword('')
      setMsg('密码已更新成功')
    } catch (e) { setMsg(`修改失败：${e.message}`) }
    setSaving(false)
  }

  const handleSecurityLogout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' }).catch(() => {})
    localStorage.removeItem('agenthub_api_secret')
    window.location.reload()
  }

  const handleTestNotification = async (channel) => {
    setTestingNotification(channel); setMsg('')
    try {
      const resp = await fetch(`/api/webhook/channels/${channel}/test`, { method: 'POST' })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) throw new Error(data.detail || '投递失败')
      setMsg(`${channel === 'slack' ? 'Slack' : 'Telegram'} 测试通知发送成功`)
    } catch (e) { setMsg(`通知测试失败：${e.message}`) }
    setTestingNotification('')
  }

  useEffect(() => {
    fetch('/api/settings/llm').then((r) => r.json()).then((d) => {
      setProvider(d.provider || 'openai'); setBaseUrl(d.base_url || ''); setModel(d.model || '')
      setTemperature(d.temperature ?? 0.5); setMaxTokens(d.max_tokens ?? 8192)
      setConfigured(d.configured); setActiveProvider(d.provider || ''); setActiveModel(d.model || '')
    }).catch(() => {})
    fetch('/api/settings/quality').then((r) => r.json()).then((d) => {
      setQEnabled(d.enabled ?? true); setBestOfN(d.best_of_n ?? 1)
      setMaxRetries(d.max_retries ?? 1); setUseLlmJudge(d.use_llm_judge ?? false)
    }).catch(() => {})
    fetch('/api/prompt/layers').then((r) => r.json()).then((d) => setLayers(d || [])).catch(() => {})
  }, [])

  const handleSave = async () => {
    setSaving(true); setMsg('')
    try {
      const resp = await fetch('/api/settings/llm', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, api_key: provider === 'ollama' ? 'ollama' : apiKey, base_url: baseUrl, model, temperature, max_tokens: maxTokens }),
      })
      const d = await resp.json()
      setConfigured(d.configured)
      setMsg(d.configured ? '配置成功！Agent 现在会使用真实 LLM 回复' : '请填写完整信息')
      if (d.configured) { setActiveProvider(provider); setActiveModel(model); if (provider !== 'ollama') setApiKey('') }
      window.dispatchEvent(new Event('agenthub:readiness-refresh'))
    } catch { setMsg('保存失败，请检查后端是否运行') }
    setSaving(false)
  }

  const handleTestLlm = async () => {
    setTestingLlm(true); setLlmTestMsg(null)
    try {
      const resp = await fetch('/api/settings/llm/test', { method: 'POST' })
      const data = await resp.json()
      setLlmTestMsg(data)
    } catch { setLlmTestMsg({ success: false, error: '网络错误，请检查后端是否运行' }) }
    setTestingLlm(false)
  }

  const handleSaveQuality = async () => {
    setSaving(true); setMsg('')
    try {
      await fetch('/api/settings/quality', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: qEnabled, best_of_n: bestOfN, max_retries: maxRetries, use_llm_judge: useLlmJudge }) })
      setMsg('质量门配置已保存')
    } catch { setMsg('保存失败') }
    setSaving(false)
  }

  const toggleLayer = async (layerId, enabled) => {
    try {
      await fetch(`/api/prompt/layers/${layerId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }) })
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

  const applyPreset = (p) => { setProvider(p.provider); setBaseUrl(p.base_url); setModel(p.model) }

  const [rtTools, setRtTools] = useState([])
  const [rtLoading, setRtLoading] = useState(false)
  const [rtTestName, setRtTestName] = useState('')
  const [rtTestParams, setRtTestParams] = useState('')
  const [rtTestResult, setRtTestResult] = useState(null)

  const fetchRuntimeTools = async () => {
    setRtLoading(true)
    try { const resp = await fetch('/api/runtime-tools'); const d = await resp.json(); setRtTools(d || []) }
    catch (e) { console.error("Failed to fetch runtime tools:", e) }
    setRtLoading(false)
  }

  const handleToggleRtTool = async (toolName) => {
    try { await fetch(`/api/runtime-tools/${toolName}/toggle`, { method: 'POST' }); fetchRuntimeTools() } catch {}
  }

  const handleTestRtTool = async () => {
    if (!rtTestName) return
    setSaving(true); setRtTestResult(null)
    try {
      let params = {}
      if (rtTestParams.trim()) { params = JSON.parse(rtTestParams) }
      const resp = await fetch(`/api/runtime-tools/${rtTestName}/test`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(params) })
      const d = await resp.json()
      setRtTestResult(d)
    } catch (e) { setRtTestResult({ error: '请求失败: ' + e.message }) }
    setSaving(false)
  }

  const providerLabels = { ollama: 'Ollama 本地', openai: 'OpenAI 兼容', anthropic: 'Anthropic' }

  const getProviderDisplayName = (prov, mdl) => {
    const match = presets.find((p) => p.base_url === baseUrl && p.provider === prov)
    if (match) return `${match.label} (${mdl || match.model})`
    return `${providerLabels[prov] || prov} (${mdl || '...'})`
  }

  const handleDisconnect = async () => {
    setSaving(true)
    try {
      const resp = await fetch('/api/settings/llm', { method: 'DELETE' })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) throw new Error(data.detail || '断开失败')
      setConfigured(Boolean(data.configured)); setActiveProvider(data.provider || ''); setActiveModel(data.model || '')
      setProvider('openai'); setBaseUrl(''); setModel(''); setApiKey('')
      setMsg(data.inherited ? '已移除个人配置，当前使用系统默认 LLM' : '已断开 LLM 连接，Agent 将使用 Mock 回复')
      window.dispatchEvent(new Event('agenthub:readiness-refresh'))
    } catch (error) { setMsg(`断开失败：${error.message}`) }
    setSaving(false)
  }

  const handleClearHistory = async () => {
    if (!activeId) return
    if (!window.confirm('确定要清空当前会话的全部历史消息吗？此操作不可撤销。')) return
    try { await fetch(`/api/conversations/${activeId}/messages`, { method: 'DELETE' }); clearMessages(activeId) } catch {}
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

  const [adapters, setAdapters] = useState([])
  const [adapterLoading, setAdapterLoading] = useState(false)
  const [adapterMsg, setAdapterMsg] = useState('')
  const [adapterEditing, setAdapterEditing] = useState(null)
  const [adapterForm, setAdapterForm] = useState({ api_key: '', api_url: '', model: '', tool_mode: 'agent', bot_id: '', user_id: '', platform: 'opencode', display_name: '', display_avatar: '', display_desc: '' })
  const [testingAdapter, setTestingAdapter] = useState(null)
  const [proxyRunning, setProxyRunning] = useState(false)
  const [proxyLoading, setProxyLoading] = useState(false)

  useEffect(() => {
    if (editAgentId && tab === 'adapters') {
      if (adapters.length === 0) { fetchAdapters(); return }
      const adapter = adapters.find((a) => a.agent_id === editAgentId)
      if (adapter) {
        setAdapterEditing(editAgentId)
        setAdapterForm({
          api_key: '', api_url: '', model: adapter.model || '', tool_mode: adapter.tool_mode || 'agent',
          bot_id: adapter.extra?.bot_id || '', user_id: adapter.extra?.user_id || '',
          platform: adapter.extra?.platform || 'opencode', display_name: adapter.display_name || '',
          display_avatar: adapter.display_avatar || '', display_desc: adapter.display_desc || '',
        })
      }
    }
  }, [editAgentId, tab, adapters])

  const ADAPTER_META = {
    claude_code: {
      name: 'Claude Code', icon: '/avatars/claude-code.svg',
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
      name: 'Codex', icon: '/avatars/codex.svg',
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
      name: 'Coze', icon: null,
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
      name: '本地 Agent', icon: null,
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
    try { const resp = await fetch('/api/adapters'); const data = await resp.json(); setAdapters(data.adapters || []) } catch {}
    setAdapterLoading(false)
  }

  const fetchProxyStatus = async () => {
    try { const resp = await fetch('/api/proxy/status'); const data = await resp.json(); setProxyRunning(data.running || false) } catch {}
  }

  const handleStartProxy = async () => {
    setProxyLoading(true)
    try {
      const resp = await fetch('/api/proxy/start', { method: 'POST' })
      const data = await resp.json()
      if (data.status === 'started' || data.status === 'already_running') {
        setProxyRunning(true); setAdapterMsg(`本地 Agent 代理已启动 (端口 ${data.port})`)
      } else { setAdapterMsg(`启动失败: ${data.error || '未知错误'}`) }
    } catch { setAdapterMsg('启动失败，请检查后端是否运行') }
    setProxyLoading(false); setTimeout(() => setAdapterMsg(''), 5000)
  }

  const handleStopProxy = async () => {
    setProxyLoading(true)
    try { await fetch('/api/proxy/stop', { method: 'POST' }); setProxyRunning(false); setAdapterMsg('本地 Agent 代理已停止') }
    catch { setAdapterMsg('停止失败') }
    setProxyLoading(false); setTimeout(() => setAdapterMsg(''), 3000)
  }

  const handleSaveAdapter = async (agentId) => {
    const meta = ADAPTER_META[agentId]
    if (!meta) return
    const adapterType = agentId === 'claude_code' ? 'claude' : agentId === 'codex' ? 'codex' : agentId === 'coze' ? 'coze' : 'self_deployed'
    const extra = {}
    if (agentId === 'coze') { if (adapterForm.bot_id) extra.bot_id = adapterForm.bot_id; if (adapterForm.user_id) extra.user_id = adapterForm.user_id }
    if (agentId === 'self_deployed') { if (adapterForm.platform) extra.platform = adapterForm.platform }
    try {
      const resp = await fetch('/api/adapters', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent_id: agentId, adapter_type: adapterType, name: meta.name,
          api_key: adapterForm.api_key, api_url: adapterForm.api_url, model: adapterForm.model,
          tool_mode: adapterForm.tool_mode || 'agent', extra,
          display_name: adapterForm.display_name || '', display_avatar: adapterForm.display_avatar || '', display_desc: adapterForm.display_desc || '',
        }),
      })
      const data = await resp.json()
      if (data.status === 'ok') {
        setAdapterMsg(`${meta.name} 配置已保存`); setAdapterEditing(null)
        setAdapterForm({ api_key: '', api_url: '', model: '', tool_mode: 'agent', bot_id: '', user_id: '', platform: 'opencode', display_name: '', display_avatar: '', display_desc: '' })
        fetchAdapters()
      } else { setAdapterMsg(`保存失败: ${data.error || '未知错误'}`) }
    } catch { setAdapterMsg('保存失败，请检查后端是否运行') }
    setTimeout(() => setAdapterMsg(''), 3000)
  }

  const handleTestAdapter = async (agentId) => {
    setTestingAdapter(agentId)
    try {
      const resp = await fetch(`/api/adapters/${agentId}/test`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: '你好，请简单介绍一下你自己。' }) })
      const data = await resp.json()
      const isError = data.status === 'error' || data.error || (data.response && data.response.includes('错误'))
      if (data.status === 'ok' && !isError) { setAdapterMsg(`✅ 测试成功: ${data.response?.slice(0, 100) || '正常响应'}`) }
      else { setAdapterMsg(`❌ 测试失败: ${data.error || data.response || '未知错误'}`) }
    } catch { setAdapterMsg('测试失败，请检查网络连接') }
    setTestingAdapter(null); setTimeout(() => setAdapterMsg(''), 5000)
  }

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.3)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }} onClick={onClose}>
      <div className="settings-modal-scroll" style={{
        width: 500, maxHeight: '88vh', overflow: 'auto',
        background: 'var(--bg-primary)', border: '1px solid var(--border)',
        borderRadius: 16, padding: 28, boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
        scrollbarWidth: 'none', msOverflowStyle: 'none',
      }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 18, color: 'var(--text-primary)', fontWeight: 600 }}>设置</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: 20, cursor: 'pointer', padding: '0 4px' }}>×</button>
        </div>

        <div style={{ marginBottom: 20, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 14px', borderRadius: 10, background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {theme === 'light' ? <Sun size={16} color="var(--orange)" /> : <Moon size={16} color="var(--accent)" />}
              <div>
                <div style={{ fontSize: 14, color: 'var(--text-primary)', fontWeight: 500 }}>界面主题</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{theme === 'light' ? '浅色模式' : '深色模式'}</div>
              </div>
            </div>
            <ToggleSwitch checked={theme === 'dark'} onChange={() => toggleTheme()} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 14px', borderRadius: 10, background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Trash2 size={16} color="var(--red)" />
              <div>
                <div style={{ fontSize: 14, color: 'var(--text-primary)', fontWeight: 500 }}>清空当前会话历史</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>删除所有消息，不可恢复</div>
              </div>
            </div>
            <button onClick={handleClearHistory} style={{ padding: '6px 14px', borderRadius: 8, fontSize: 12, background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.25)', color: 'var(--red)', cursor: 'pointer', fontWeight: 500 }}>清空</button>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 4, marginBottom: 24, background: 'var(--bg-tertiary)', borderRadius: 10, padding: 4 }}>
          {tabs.map((t) => (
            <button key={t.id} onClick={() => { setTab(t.id); setMsg('') }} style={{
              flex: 1, padding: '8px 12px', borderRadius: 8, fontSize: 12,
              background: tab === t.id ? 'var(--accent)' : 'transparent',
              border: 'none', color: tab === t.id ? 'white' : 'var(--text-secondary)',
              cursor: 'pointer', fontWeight: tab === t.id ? 600 : 400, transition: 'all 0.2s',
            }}>{t.label}</button>
          ))}
        </div>

        {tab === 'llm' && (
          <LLMTab configured={configured} activeProvider={activeProvider} activeModel={activeModel}
            getProviderDisplayName={getProviderDisplayName} handleDisconnect={handleDisconnect} saving={saving}
            setHighlightPresets={setHighlightPresets} presetsRef={presetsRef} highlightPresets={highlightPresets}
            presets={presets} applyPreset={applyPreset} provider={provider} setProvider={setProvider}
            setBaseUrl={setBaseUrl} baseUrl={baseUrl} model={model} setModel={setModel}
            ollamaModels={ollamaModels} ollamaLoading={ollamaLoading} fetchOllamaModels={fetchOllamaModels}
            ollamaError={ollamaError} apiKey={apiKey} setApiKey={setApiKey}
            temperature={temperature} setTemperature={setTemperature} maxTokens={maxTokens} setMaxTokens={setMaxTokens}
            handleSave={handleSave} handleTestLlm={handleTestLlm} testingLlm={testingLlm} llmTestMsg={llmTestMsg} />
        )}

        {tab === 'adapters' && (
          <AdaptersTab adapterMsg={adapterMsg} ADAPTER_META={ADAPTER_META} adapters={adapters}
            adapterEditing={adapterEditing} setAdapterEditing={setAdapterEditing}
            adapterForm={adapterForm} setAdapterForm={setAdapterForm}
            proxyRunning={proxyRunning} proxyLoading={proxyLoading}
            handleStartProxy={handleStartProxy} handleStopProxy={handleStopProxy}
            handleSaveAdapter={handleSaveAdapter} handleTestAdapter={handleTestAdapter} testingAdapter={testingAdapter} />
        )}

        {tab === 'quality' && (
          <QualityGateTab qEnabled={qEnabled} setQEnabled={setQEnabled} bestOfN={bestOfN} setBestOfN={setBestOfN}
            maxRetries={maxRetries} setMaxRetries={setMaxRetries} useLlmJudge={useLlmJudge} setUseLlmJudge={setUseLlmJudge}
            handleSaveQuality={handleSaveQuality} saving={saving} />
        )}

        {tab === 'prompt' && (
          <PromptLayersTab layers={layers} toggleLayer={toggleLayer} />
        )}

        {tab === 'cron' && (
          <CronTasksTab fetchCronTasks={fetchCronTasks} cronLoading={cronLoading} cronTasks={cronTasks} saving={saving}
            handleToggleCronTask={handleToggleCronTask} handleRunCronTaskNow={handleRunCronTaskNow}
            handleDeleteCronTask={handleDeleteCronTask} selectedAgentForCron={selectedAgentForCron}
            setSelectedAgentForCron={setSelectedAgentForCron} cronInterval={cronInterval} setCronInterval={setCronInterval}
            cronPrompt={cronPrompt} setCronPrompt={setCronPrompt} handleAddCronTask={handleAddCronTask} />
        )}

        {tab === 'other' && (
          <OtherTab rtTools={rtTools} rtLoading={rtLoading} handleToggleRtTool={handleToggleRtTool}
            rtTestName={rtTestName} setRtTestName={setRtTestName} rtTestParams={rtTestParams} setRtTestParams={setRtTestParams}
            handleTestRtTool={handleTestRtTool} saving={saving} rtTestResult={rtTestResult}
            kbStats={kbStats} kbLoading={kbLoading} fetchKnowledgeDocs={fetchKnowledgeDocs}
            kbUploading={kbUploading} handleKbUpload={handleKbUpload} kbDocs={kbDocs}
            handleKbDelete={handleKbDelete} kbQuery={kbQuery} setKbQuery={setKbQuery}
            handleKbQuery={handleKbQuery} kbResults={kbResults} />
        )}

        {tab === 'security' && (
          <SecurityTab authStatus={authStatus} saving={saving}
            currentPassword={currentPassword} setCurrentPassword={setCurrentPassword}
            newPassword={newPassword} setNewPassword={setNewPassword}
            confirmPassword={confirmPassword} setConfirmPassword={setConfirmPassword}
            handleChangePassword={handleChangePassword} handleLogout={handleSecurityLogout}
            legacyTenants={legacyTenants} legacyLoading={legacyLoading}
            notificationStatus={notificationStatus} testingNotification={testingNotification}
            handleTestNotification={handleTestNotification} />
        )}

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
