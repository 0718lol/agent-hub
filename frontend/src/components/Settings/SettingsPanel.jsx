import React, { useState, useEffect, useRef } from 'react'
import { Sun, Moon, Trash2 } from 'lucide-react'
import { useThemeStore } from '../../stores/themeStore'
import { useChatStore } from '../../stores/chatStore'
import styles from './SettingsPanel.module.css'
import ToggleSwitch from './ToggleSwitch'
import LLMTab from './LLMTab'
import QualityGateTab from './QualityGateTab'
import PromptLayersTab from './PromptLayersTab'
import CronTasksTab from './CronTasksTab'
import RuntimeToolsTab from './RuntimeToolsTab'
import KnowledgeBaseTab from './KnowledgeBaseTab'
import SecurityTab from './SecurityTab'

export default function SettingsPanel({ onClose }) {
  const theme = useThemeStore((s) => s.theme)
  const isDark = theme === 'dark'
  const toggleTheme = useThemeStore((s) => s.toggleTheme)
  const activeId = useChatStore((s) => s.activeConversationId)
  const clearMessages = useChatStore((s) => s.clearMessages)

  const [tab, setTab] = useState('llm')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  // LLM state
  const [provider, setProvider] = useState('openai')
  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [temperature, setTemperature] = useState(0.5)
  const [maxTokens, setMaxTokens] = useState(8192)
  const [configured, setConfigured] = useState(false)
  const [activeProvider, setActiveProvider] = useState('')
  const [activeModel, setActiveModel] = useState('')
  const [highlightPresets, setHighlightPresets] = useState(false)
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

  const providerLabels = {
    ollama: 'Ollama 本地',
    openai: 'OpenAI 兼容',
    anthropic: 'Anthropic',
  }

  const getProviderDisplayName = (prov, mdl) => {
    const match = presets.find((p) => p.base_url === baseUrl && p.provider === prov)
    if (match) return match.label + ' (' + (mdl || match.model) + ')'
    return (providerLabels[prov] || prov) + ' (' + (mdl || '...') + ')'
  }

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

  // Quality gate state
  const [qEnabled, setQEnabled] = useState(true)
  const [bestOfN, setBestOfN] = useState(1)
  const [maxRetries, setMaxRetries] = useState(1)
  const [useLlmJudge, setUseLlmJudge] = useState(false)

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

  // Prompt layers state
  const [layers, setLayers] = useState([])

  const toggleLayer = async (layerId, enabled) => {
    try {
      await fetch('/api/prompt/layers/' + layerId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
      setLayers((prev) => prev.map((l) => l.id === layerId ? { ...l, enabled } : l))
    } catch {}
  }

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
      if (!resp.ok) throw new Error('HTTP ' + resp.status)
      const d = await resp.json()
      if (d.status === 'ok') setCronTasks(d.tasks || [])
    } catch (e) {
      console.error('Failed to fetch cron tasks:', e)
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
      await fetch('/api/cron/' + taskId + '/toggle', {
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
      const resp = await fetch('/api/cron/' + taskId + '/run', { method: 'POST' })
      const d = await resp.json()
      if (d.status === 'ok') setMsg(d.message)
      fetchCronTasks()
    } catch {}
    setSaving(false)
  }

  const handleDeleteCronTask = async (taskId) => {
    setSaving(true)
    try {
      await fetch('/api/cron/' + taskId, { method: 'DELETE' })
      fetchCronTasks()
    } catch {}
    setSaving(false)
  }

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
      if (!resp.ok) throw new Error('HTTP ' + resp.status)
      const d = await resp.json()
      if (d.status === 'ok') {
        setKbDocs(d.docs || [])
        setKbStats(d.stats || {})
      }
    } catch (e) {
      console.error('Failed to fetch knowledge docs:', e)
    }
    setKbLoading(false)
  }

  const handleKbUpload = async (e) => {
    const file = e.target.files && e.target.files[0]
    if (!file) return
    setKbUploading(true)
    setMsg('')
    try {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await fetch('/api/knowledge/upload', { method: 'POST', body: formData })
      const d = await resp.json()
      if (d.status === 'ok') {
        setMsg('文档入库成功！生成 ' + d.chunk_count + ' 个知识块')
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
      await fetch('/api/knowledge/' + docId, { method: 'DELETE' })
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
      if (!resp.ok) throw new Error('HTTP ' + resp.status)
      const d = await resp.json()
      setRtTools(d || [])
    } catch (e) {
      console.error('Failed to fetch runtime tools:', e)
    }
    setRtLoading(false)
  }

  const handleToggleRtTool = async (toolName) => {
    try {
      await fetch('/api/runtime-tools/' + toolName + '/toggle', { method: 'POST' })
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
      const resp = await fetch('/api/runtime-tools/' + rtTestName + '/test', {
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

  // Security state
  const [securityToken, setSecurityToken] = useState(localStorage.getItem('agenthub_api_secret') || '')
  const [showToken, setShowToken] = useState(false)

  // History
  const handleClearHistory = async () => {
    if (!activeId) return
    if (!window.confirm('确定要清空当前会话的全部历史消息吗？此操作不可撤销。')) return
    try {
      await fetch('/api/conversations/' + activeId + '/messages', { method: 'DELETE' })
      clearMessages(activeId)
    } catch {}
  }

  // Initial data fetch
  useEffect(() => {
    fetch('/api/settings/llm')
      .then((r) => r.json())
      .then((d) => {
        setProvider(d.provider || 'openai')
        setBaseUrl(d.base_url || '')
        setModel(d.model || '')
        setTemperature(d.temperature != null ? d.temperature : 0.5)
        setMaxTokens(d.max_tokens != null ? d.max_tokens : 8192)
        setConfigured(d.configured)
        setActiveProvider(d.provider || '')
        setActiveModel(d.model || '')
      })
      .catch(() => {})
    fetch('/api/settings/quality')
      .then((r) => r.json())
      .then((d) => {
        setQEnabled(d.enabled != null ? d.enabled : true)
        setBestOfN(d.best_of_n != null ? d.best_of_n : 1)
        setMaxRetries(d.max_retries != null ? d.max_retries : 1)
        setUseLlmJudge(d.use_llm_judge != null ? d.use_llm_judge : false)
      })
      .catch(() => {})
    fetch('/api/prompt/layers')
      .then((r) => r.json())
      .then((d) => setLayers(d || []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (tab === 'cron') fetchCronTasks()
    if (tab === 'knowledge') fetchKnowledgeDocs()
    if (tab === 'tools') fetchRuntimeTools()
  }, [tab])

  const tabs = [
    { id: 'llm', label: 'LLM 模型' },
    { id: 'quality', label: '质量门' },
    { id: 'prompt', label: 'Prompt 分层' },
    { id: 'tools', label: '工具' },
    { id: 'cron', label: '自治' },
    { id: 'knowledge', label: '知识库' },
    { id: 'security', label: '安全' },
  ]

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal + ' settings-modal-scroll'} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <h2 style={{ margin: 0, fontSize: 18, color: 'var(--text-primary)', fontWeight: 600 }}>设置</h2>
          <button onClick={onClose} className={styles.closeBtn}>x</button>
        </div>

        <div className={styles.generalSection}>
          <div className={styles.row}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {theme === 'light' ? <Sun size={16} color="#f59e0b" /> : <Moon size={16} color="#6366f1" />}
              <div>
                <div style={{ fontSize: 14, color: 'var(--text-primary)', fontWeight: 500 }}>界面主题</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  {theme === 'light' ? '浅色模式' : '深色模式'}
                </div>
              </div>
            </div>
            <ToggleSwitch checked={theme === 'dark'} onChange={() => toggleTheme()} />
          </div>

          <div className={styles.row}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Trash2 size={16} color="var(--danger, #ef4444)" />
              <div>
                <div style={{ fontSize: 14, color: 'var(--text-primary)', fontWeight: 500 }}>清空当前会话历史</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>删除所有消息，不可恢复</div>
              </div>
            </div>
            <button
              onClick={handleClearHistory}
              style={{
                padding: '6px 14px', borderRadius: 8, fontSize: 12,
                background: isDark ? 'rgba(239,68,68,0.12)' : '#fef2f2', border: '1px solid ' + (isDark ? 'rgba(239,68,68,0.25)' : '#fecaca'),
                color: 'var(--danger, #ef4444)', cursor: 'pointer', fontWeight: 500,
              }}
            >
              清空
            </button>
          </div>
        </div>

        <div className={styles.tabBar}>
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => { setTab(t.id); setMsg('') }}
              className={tab === t.id ? styles.tabBtnActive : styles.tabBtnInactive}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === 'llm' && (
          <LLMTab
            isDark={isDark} saving={saving} configured={configured}
            provider={provider} setProvider={setProvider}
            apiKey={apiKey} setApiKey={setApiKey}
            baseUrl={baseUrl} setBaseUrl={setBaseUrl}
            model={model} setModel={setModel}
            temperature={temperature} setTemperature={setTemperature}
            maxTokens={maxTokens} setMaxTokens={setMaxTokens}
            activeProvider={activeProvider} activeModel={activeModel}
            ollamaModels={ollamaModels} ollamaLoading={ollamaLoading} ollamaError={ollamaError}
            fetchOllamaModels={fetchOllamaModels}
            presets={presets} applyPreset={applyPreset}
            presetsRef={presetsRef} highlightPresets={highlightPresets}
            setHighlightPresets={setHighlightPresets}
            handleSave={handleSave} handleDisconnect={handleDisconnect}
            getProviderDisplayName={getProviderDisplayName}
          />
        )}

        {tab === 'quality' && (
          <QualityGateTab
            isDark={isDark} saving={saving}
            qEnabled={qEnabled} setQEnabled={setQEnabled}
            bestOfN={bestOfN} setBestOfN={setBestOfN}
            maxRetries={maxRetries} setMaxRetries={setMaxRetries}
            useLlmJudge={useLlmJudge} setUseLlmJudge={setUseLlmJudge}
            handleSaveQuality={handleSaveQuality}
          />
        )}

        {tab === 'prompt' && (
          <PromptLayersTab
            isDark={isDark} layers={layers} toggleLayer={toggleLayer}
          />
        )}

        {tab === 'tools' && (
          <RuntimeToolsTab
            isDark={isDark} saving={saving}
            rtTools={rtTools} rtLoading={rtLoading}
            handleToggleRtTool={handleToggleRtTool}
            rtTestName={rtTestName} setRtTestName={setRtTestName}
            rtTestParams={rtTestParams} setRtTestParams={setRtTestParams}
            handleTestRtTool={handleTestRtTool} rtTestResult={rtTestResult}
          />
        )}

        {tab === 'cron' && (
          <CronTasksTab
            isDark={isDark} saving={saving}
            cronLoading={cronLoading} cronTasks={cronTasks}
            fetchCronTasks={fetchCronTasks}
            handleToggleCronTask={handleToggleCronTask}
            handleRunCronTaskNow={handleRunCronTaskNow}
            handleDeleteCronTask={handleDeleteCronTask}
            selectedAgentForCron={selectedAgentForCron} setSelectedAgentForCron={setSelectedAgentForCron}
            cronInterval={cronInterval} setCronInterval={setCronInterval}
            cronPrompt={cronPrompt} setCronPrompt={setCronPrompt}
            handleAddCronTask={handleAddCronTask}
          />
        )}

        {tab === 'knowledge' && (
          <KnowledgeBaseTab
            isDark={isDark} saving={saving}
            kbStats={kbStats} kbLoading={kbLoading}
            fetchKnowledgeDocs={fetchKnowledgeDocs}
            kbUploading={kbUploading} handleKbUpload={handleKbUpload}
            kbDocs={kbDocs} handleKbDelete={handleKbDelete}
            kbQuery={kbQuery} setKbQuery={setKbQuery}
            handleKbQuery={handleKbQuery} kbResults={kbResults}
          />
        )}

        {tab === 'security' && (
          <SecurityTab
            isDark={isDark}
            securityToken={securityToken} setSecurityToken={setSecurityToken}
            showToken={showToken} setShowToken={setShowToken}
            setMsg={setMsg}
          />
        )}

        {msg && (
          <div style={{
            marginTop: 16, padding: '10px 14px', borderRadius: 8,
            background: msg.includes('成功') || msg.includes('已保存') ? (isDark ? 'rgba(34,197,94,0.12)' : '#ecfdf5') : (isDark ? 'rgba(239,68,68,0.12)' : '#fef2f2'),
            border: '1px solid ' + (msg.includes('成功') || msg.includes('已保存') ? (isDark ? 'rgba(34,197,94,0.25)' : '#a7f3d0') : (isDark ? 'rgba(239,68,68,0.25)' : '#fecaca')),
            fontSize: 13, color: msg.includes('成功') || msg.includes('已保存') ? '#059669' : (isDark ? '#f87171' : '#dc2626'),
          }}>{msg}</div>
        )}
      </div>
    </div>
  )
}