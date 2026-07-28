import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AlertCircle, ExternalLink, Play, RefreshCw, Server, Smartphone, Square, Workflow } from 'lucide-react'
import { useCanvasStore } from '../../stores/canvasStore'
import { useChatStore } from '../../stores/chatStore'
import { PREVIEW_HTML } from './previewHtml'

const commandStyle = {
  width: 30, height: 30, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  border: '1px solid var(--border)', borderRadius: 6, background: 'transparent',
  color: 'var(--text-secondary)', cursor: 'pointer', flexShrink: 0,
}

function StatusPanel({ icon: Icon, title, status, action, actionLabel }) {
  return (
    <div style={{ height: '100%', display: 'grid', placeItems: 'center', padding: 24 }}>
      <div style={{ width: 'min(420px, 100%)', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)', padding: '28px 4px', textAlign: 'center' }}>
        <Icon size={28} style={{ color: 'var(--accent)', marginBottom: 10 }} aria-hidden="true" />
        <div style={{ fontSize: 14, fontWeight: 650, marginBottom: 6 }}>{title}</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: action ? 16 : 0 }}>{status}</div>
        {action && <button type="button" onClick={action} style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid var(--accent)', background: 'var(--accent-bg)', color: 'var(--accent)', cursor: 'pointer', fontWeight: 600 }}>{actionLabel}</button>}
      </div>
    </div>
  )
}

function ApiPreview({ api, openDeploy }) {
  const [method, setMethod] = useState('GET')
  const [path, setPath] = useState('')
  const [body, setBody] = useState('{}')
  const [result, setResult] = useState(null)
  const [sending, setSending] = useState(false)

  const sendRequest = async () => {
    if (!api?.base_url || sending) return
    setSending(true)
    setResult(null)
    const target = `${api.base_url}${path.replace(/^\/+/, '')}`
    try {
      const options = { method, headers: {} }
      if (!['GET', 'HEAD'].includes(method)) {
        options.headers['Content-Type'] = 'application/json'
        options.body = body
      }
      const response = await fetch(target, options)
      const text = await response.text()
      setResult({ status: response.status, ok: response.ok, text })
    } catch (error) {
      setResult({ status: 0, ok: false, text: error.message || '请求失败' })
    } finally {
      setSending(false)
    }
  }

  if (!api) {
    return <StatusPanel icon={Server} title="API 运行实例未启动" status="需要隔离构建 Worker" action={openDeploy} actionLabel="前往部署" />
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: 8, borderBottom: '1px solid var(--border)', background: 'var(--bg-secondary)' }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--green)' }} />
        <code style={{ minWidth: 0, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', fontSize: 11 }}>{api.base_url}</code>
        <button title="打开 Swagger" onClick={() => window.open(api.docs_url, '_blank', 'noopener,noreferrer')} style={commandStyle}><ExternalLink size={14} /></button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '88px minmax(0, 1fr) 72px', gap: 6, padding: 10, borderBottom: '1px solid var(--border)' }}>
        <select aria-label="HTTP 方法" value={method} onChange={(event) => setMethod(event.target.value)} style={{ border: '1px solid var(--border)', borderRadius: 6, background: 'var(--bg-primary)', color: 'var(--text-primary)', padding: '7px 8px' }}>
          {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((value) => <option key={value}>{value}</option>)}
        </select>
        <input aria-label="API 路径" value={path} onChange={(event) => setPath(event.target.value)} placeholder="health" style={{ minWidth: 0, border: '1px solid var(--border)', borderRadius: 6, background: 'var(--bg-primary)', color: 'var(--text-primary)', padding: '7px 9px' }} />
        <button type="button" onClick={sendRequest} disabled={sending} style={{ border: 'none', borderRadius: 6, background: 'var(--accent)', color: '#fff', cursor: sending ? 'wait' : 'pointer', fontWeight: 650 }}>{sending ? '发送中' : '发送'}</button>
      </div>
      {!['GET', 'HEAD'].includes(method) && <textarea aria-label="请求 JSON" value={body} onChange={(event) => setBody(event.target.value)} spellCheck={false} style={{ minHeight: 90, resize: 'vertical', border: 0, borderBottom: '1px solid var(--border)', padding: 10, background: 'var(--code-bg)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: 12 }} />}
      <pre style={{ flex: 1, minHeight: 0, overflow: 'auto', margin: 0, padding: 14, background: 'var(--code-bg)', color: result?.ok ? 'var(--text-primary)' : 'var(--red)', fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
        {result ? `HTTP ${result.status || 'ERR'}\n\n${result.text}` : '等待请求'}
      </pre>
    </div>
  )
}

export default function WebPreview() {
  const previewHtml = useCanvasStore((state) => state.previewHtml)
  const setActiveTab = useCanvasStore((state) => state.setActiveTab)
  const activeConversationId = useChatStore((state) => state.activeConversationId)
  const iframeRef = useRef(null)
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [runtimeBusy, setRuntimeBusy] = useState(false)
  const [revision, setRevision] = useState(0)

  const loadSummary = useCallback(async () => {
    if (!activeConversationId) {
      setSummary(null)
      setLoading(false)
      return
    }
    try {
      const response = await fetch(`/api/previews/${encodeURIComponent(activeConversationId)}`)
      if (!response.ok) throw new Error(`预览信息请求失败 (${response.status})`)
      setSummary(await response.json())
      setError('')
    } catch (loadError) {
      if (!useCanvasStore.getState().previewHtml) {
        setError(loadError.message || '预览信息请求失败')
      }
    } finally {
      setLoading(false)
    }
  }, [activeConversationId])

  useEffect(() => {
    setLoading(true)
    const timer = window.setTimeout(loadSummary, previewHtml ? 350 : 0)
    return () => window.clearTimeout(timer)
  }, [loadSummary, previewHtml])

  useEffect(() => {
    setSummary(null)
    setError('')
    setRevision(0)
  }, [activeConversationId])

  const toggleRuntime = async () => {
    if (!activeConversationId || runtimeBusy) return
    setRuntimeBusy(true)
    try {
      const response = await fetch(
        `/api/previews/${encodeURIComponent(activeConversationId)}/runtime`,
        { method: summary?.web?.runtime_active ? 'DELETE' : 'POST' },
      )
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || '预览服务操作失败')
      await loadSummary()
      setRevision((value) => value + 1)
    } catch (runtimeError) {
      setError(runtimeError.message || '预览服务操作失败')
    } finally {
      setRuntimeBusy(false)
    }
  }

  const refreshPreview = () => {
    setRevision((value) => value + 1)
    loadSummary()
  }

  const previewUrl = useMemo(() => {
    const url = summary?.web?.runtime_url || summary?.web?.static_url || ''
    if (!url) return ''
    return `${url}${url.includes('?') ? '&' : '?'}revision=${revision}`
  }, [revision, summary?.web?.runtime_url, summary?.web?.static_url])

  const projectType = summary?.project_type || (previewHtml ? 'web' : 'unknown')
  const fallbackHtml = previewHtml || PREVIEW_HTML.todo
  const openDeploy = () => setActiveTab('deploy')

  if (loading && !summary && !previewHtml) {
    return <StatusPanel icon={RefreshCw} title="正在读取项目" status="" />
  }

  if (projectType === 'api') return <ApiPreview api={summary?.api} openDeploy={openDeploy} />
  if (projectType === 'miniprogram') return <StatusPanel icon={Workflow} title="微信小程序真机预览" status="等待 AppID 与代码上传私钥" action={openDeploy} actionLabel="生成体验二维码" />
  if (projectType === 'apk') return <StatusPanel icon={Smartphone} title="Android APK" status="浏览器不提供模拟器，APK 可通过流水线签名并下载" action={openDeploy} actionLabel="前往构建" />
  if (projectType !== 'web' && !previewHtml) return <StatusPanel icon={AlertCircle} title="暂无可预览项目" status={error || '等待 Agent 生成项目文件'} />

  return (
    <div className="web-preview">
      <div className="preview-url-bar" style={{ gap: 6 }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: error ? 'var(--red)' : 'var(--green)', flexShrink: 0 }} />
        <input value={previewUrl || '流式 HTML 预览'} readOnly />
        {(summary?.web?.can_start_runtime || summary?.web?.runtime_active) && (
          <button title={summary.web.runtime_active ? '停止开发服务器' : '启动隔离开发服务器'} onClick={toggleRuntime} disabled={runtimeBusy} style={commandStyle}>
            {summary.web.runtime_active ? <Square size={13} /> : <Play size={14} />}
          </button>
        )}
        <button title="刷新预览" onClick={refreshPreview} style={commandStyle}><RefreshCw size={14} /></button>
        {previewUrl && <button title="新窗口打开" onClick={() => window.open(previewUrl, '_blank', 'noopener,noreferrer')} style={commandStyle}><ExternalLink size={14} /></button>}
      </div>
      {error && <div role="alert" style={{ padding: '6px 10px', color: 'var(--red)', background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)', fontSize: 11 }}>{error}</div>}
      <iframe
        key={previewUrl}
        ref={iframeRef}
        className="preview-iframe"
        {...(previewUrl ? { src: previewUrl } : { srcDoc: fallbackHtml })}
        sandbox="allow-scripts allow-popups allow-forms allow-modals allow-downloads"
        title="项目预览"
        tabIndex={0}
        style={{ outline: 'none' }}
      />
    </div>
  )
}
