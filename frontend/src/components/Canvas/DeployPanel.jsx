import React, { useRef, useEffect, useState, useCallback } from 'react'
import { Boxes, Check, Download, ExternalLink, FileDown, Globe2, History, KeyRound, Power, Rocket, RotateCcw, RotateCw, Server, Smartphone, Square, Trash2, Upload } from 'lucide-react'
import { useCanvasStore } from '../../stores/canvasStore'
import { useChatStore } from '../../stores/chatStore'

const PIPELINE_STEPS = [
  { key: 'queued', label: '排队' },
  { key: 'generate', label: '生成' },
  { key: 'dependencies', label: '依赖安装' },
  { key: 'build', label: '构建' },
  { key: 'sign', label: '签名' },
  { key: 'upload', label: '上传' },
  { key: 'complete', label: '完成' },
]

export default function DeployPanel() {
  const isDeploying = useCanvasStore((s) => s.isDeploying)
  const deployLogs = useCanvasStore((s) => s.deployLogs)
  const deployedUrl = useCanvasStore((s) => s.deployedUrl)
  const deployResultType = useCanvasStore((s) => s.deployResultType)
  const deployedTarget = useCanvasStore((s) => s.deployTarget)
  const deployJobId = useCanvasStore((s) => s.deployJobId)
  const deployStatus = useCanvasStore((s) => s.deployStatus)
  const startDeploy = useCanvasStore((s) => s.startDeploy)
  const failDeploy = useCanvasStore((s) => s.failDeploy)
  const cancelDeploy = useCanvasStore((s) => s.cancelDeploy)
  const appendDeployLog = useCanvasStore((s) => s.appendDeployLog)
  const finishDeploy = useCanvasStore((s) => s.finishDeploy)
  const markDeployRunning = useCanvasStore((s) => s.markDeployRunning)
  const setDeployJobId = useCanvasStore((s) => s.setDeployJobId)

  const activeId = useChatStore((s) => s.activeConversationId)
  const terminalEndRef = useRef(null)
  const [target, setTarget] = useState('auto')
  const [signingMode, setSigningMode] = useState('demo')
  const [keystore, setKeystore] = useState({ id: '', name: '' })
  const [keyAlias, setKeyAlias] = useState('')
  const [storePassword, setStorePassword] = useState('')
  const [keyPassword, setKeyPassword] = useState('')
  const [miniAppid, setMiniAppid] = useState('')
  const [miniKey, setMiniKey] = useState({ id: '', name: '' })
  const [version, setVersion] = useState('1.0.0')
  const [history, setHistory] = useState([])
  const [historyMessage, setHistoryMessage] = useState('')
  const [activeJob, setActiveJob] = useState(null)
  const [cancelling, setCancelling] = useState(false)

  const targets = [
    { value: 'auto', label: '自动识别', icon: Boxes },
    { value: 'web', label: 'Web', icon: Globe2 },
    { value: 'api', label: 'API', icon: Server },
    { value: 'apk', label: 'APK', icon: Smartphone },
    { value: 'miniprogram', label: '小程序', icon: Boxes },
  ]

  const loadHistory = useCallback(async () => {
    try {
      const response = await fetch('/api/deployments?limit=20')
      if (response.ok) {
        const data = await response.json()
        setHistory(data.deployments || [])
      }
    } catch (_error) {
      // History is supplementary; deployment remains usable while disconnected.
    }
  }, [])

  useEffect(() => { loadHistory() }, [loadHistory, activeId, deployStatus])

  useEffect(() => {
    if (terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [deployLogs])

  useEffect(() => {
    if (!deployJobId || (activeJob?.id === deployJobId && ['success', 'failed', 'cancelled'].includes(activeJob.status))) return undefined
    let cancelled = false
    const poll = async () => {
      try {
        const response = await fetch(`/api/deployments/${deployJobId}`)
        if (!response.ok || cancelled) return
        const job = await response.json()
        setActiveJob(job)
        if (job.status === 'queued' || job.status === 'running') {
          markDeployRunning()
        } else if (job.status === 'success' && job.url) {
          finishDeploy(job.url, job.result_type, job.target)
        } else if (job.status === 'failed') {
          if (job.log) appendDeployLog(job.log)
          failDeploy()
        } else if (job.status === 'cancelled') {
          if (job.log) appendDeployLog(job.log)
          setCancelling(false)
          cancelDeploy()
        }
      } catch (_error) {
        // WebSocket remains the primary channel; the next poll retries recovery.
      }
    }
    poll()
    const timer = window.setInterval(poll, 3000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [activeJob?.id, activeJob?.status, appendDeployLog, cancelDeploy, deployJobId, failDeploy, finishDeploy, markDeployRunning])

  const handleDeploy = async () => {
    if (isDeploying || !activeId) return
    startDeploy()
    setCancelling(false)
    setActiveJob(null)
    try {
      const resp = await fetch(`/api/deploy/${activeId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target,
          signing_mode: signingMode,
          keystore_file_id: keystore.id,
          key_alias: keyAlias,
          store_password: storePassword,
          key_password: keyPassword,
          mini_appid: miniAppid,
          mini_private_key_file_id: miniKey.id,
          version,
          description: 'AgentHub 演示发布',
        }),
      })
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}))
        appendDeployLog(data.detail || '发布失败：未配置发布服务。')
        failDeploy()
      } else {
        const data = await resp.json()
        setDeployJobId(data.job_id)
        setActiveJob({
          id: data.job_id,
          status: 'queued',
          stage: 'queued',
          progress: 5,
          log_entries: [{ stage: 'queued', level: 'info', message: '任务已进入持久化队列，等待构建 Worker。' }],
        })
        appendDeployLog(`任务已进入持久化队列：${data.job_id}`)
      }
    } catch (e) {
      appendDeployLog('发布请求失败，请检查网络和部署服务配置。')
      failDeploy()
    }
  }

  const handleCancel = async () => {
    if (!deployJobId || cancelling) return
    if (!window.confirm('确定取消当前构建吗？正在运行的构建进程会被终止。')) return
    setCancelling(true)
    appendDeployLog('正在向构建 Worker 发送取消请求...')
    try {
      const response = await fetch(`/api/deployments/${deployJobId}/cancel`, { method: 'POST' })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        setCancelling(false)
        appendDeployLog(data.detail || '取消失败，请稍后重试。')
        return
      }
      setActiveJob((job) => job ? { ...job, cancel_requested: true } : job)
      appendDeployLog('取消请求已提交，正在安全停止构建进程...')
    } catch (_error) {
      setCancelling(false)
      appendDeployLog('取消请求发送失败，请检查网络连接。')
    }
  }

  const uploadCredential = async (file, setter) => {
    if (!file) return
    const form = new FormData()
    form.append('file', file)
    const response = await fetch('/api/upload', { method: 'POST', body: form })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      setHistoryMessage(data.detail || '凭证上传失败')
      return
    }
    setter({ id: data.stored_name, name: file.name })
  }

  const runHistoryAction = async (job, action) => {
    if (action === 'offline' && !window.confirm('确定下线这个 API 版本吗？')) return
    setHistoryMessage('正在提交操作...')
    const response = await fetch(`/api/deployments/${job.id}/${action}`, { method: 'POST' })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      setHistoryMessage(data.detail || '操作失败')
      return
    }
    setHistoryMessage('操作已进入队列')
    window.setTimeout(loadHistory, 2500)
  }

  const retryHistory = async (job) => {
    startDeploy()
    setCancelling(false)
    setActiveJob(null)
    const response = await fetch(`/api/deployments/${job.id}/retry`, { method: 'POST' })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      appendDeployLog(data.detail || '重试失败')
      failDeploy()
      return
    }
    setDeployJobId(data.job_id)
    setActiveJob({
      id: data.job_id,
      status: 'queued',
      stage: 'queued',
      progress: 5,
      log_entries: [{ stage: 'queued', level: 'info', message: '历史版本已重新进入队列。' }],
    })
    appendDeployLog(`历史版本已重新进入队列：${data.job_id}`)
  }

  const cleanupHistory = async () => {
    const response = await fetch('/api/deployments/cleanup', { method: 'POST' })
    const data = await response.json().catch(() => ({}))
    setHistoryMessage(response.ok ? '清理任务已进入队列' : (data.detail || '清理失败'))
    if (response.ok) window.setTimeout(loadHistory, 3000)
  }

  const handleVisitSite = () => {
    if (deployedUrl) window.open(deployedUrl, '_blank', 'noopener,noreferrer')
  }

  const isDownload = deployResultType !== 'site'
  const isMiniUploaded = deployResultType === 'miniprogram'
  const targetName = targets.find((item) => item.value === deployedTarget)?.label || deployedTarget
  const currentStage = activeJob?.stage || (deployStatus === 'success' ? 'complete' : isDeploying ? 'queued' : '')
  const currentStepIndex = PIPELINE_STEPS.findIndex((step) => step.key === currentStage)
  const visitedStages = new Set((activeJob?.log_entries || []).map((entry) => entry.stage))
  const progressPercent = activeJob?.progress ?? (deployStatus === 'success' ? 100 : isDeploying ? 5 : 0)
  const cancellationPending = cancelling || activeJob?.cancel_requested
  const visibleLogs = activeJob?.log_entries?.length
    ? activeJob.log_entries
    : deployLogs.map((message) => ({ message, level: 'info' }))


  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 12, overflowY: 'auto' }}>
      {/* Panel Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '12px 16px', background: 'var(--bg-secondary)', borderRadius: 10,
        border: '1px solid var(--border)', flexShrink: 0
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Rocket size={20} aria-hidden="true" />
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>构建与发布流水线</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Web、API、Android APK、微信小程序</div>
          </div>
        </div>
        <button
          onClick={isDeploying ? handleCancel : handleDeploy}
          disabled={cancelling}
          style={{
            padding: '8px 16px',
            background: isDeploying
              ? 'var(--red)'
              : deployStatus === 'success'
              ? 'var(--accent-bg)'
              : 'var(--accent)',
            color: deployStatus === 'success' ? 'var(--green)' : '#fff',
            border: deployStatus === 'success' ? '1px solid var(--green)' : 'none',
            borderRadius: 8,
            fontSize: 13,
            fontWeight: 600,
            cursor: cancelling ? 'wait' : 'pointer',
            transition: 'all 0.3s ease',
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}
        >
          {isDeploying ? (
            <>
              {cancellationPending ? <span className="deploy-loader" /> : <Square size={14} />}
              {cancellationPending ? '正在停止...' : '取消构建'}
            </>
          ) : deployStatus === 'success' ? (
            <>
              <Check size={15} />
              再次构建
            </>
          ) : (
            <><Rocket size={15} />启动流水线</>
          )}
        </button>
      </div>

      {target === 'apk' && (
        <div style={{ padding: 12, borderBottom: '1px solid var(--border)', background: 'var(--bg-secondary)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, fontSize: 12, fontWeight: 600 }}><KeyRound size={15} />APK 签名</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {[['demo', '系统演示密钥'], ['uploaded', '用户 keystore']].map(([value, label]) => (
              <button key={value} type="button" onClick={() => setSigningMode(value)} style={{ padding: '7px 10px', borderRadius: 6, border: signingMode === value ? '1px solid var(--accent)' : '1px solid var(--border)', background: signingMode === value ? 'var(--accent-bg)' : 'transparent', color: 'var(--text-primary)', cursor: 'pointer' }}>{label}</button>
            ))}
            {signingMode === 'uploaded' && <>
              <label style={{ padding: '7px 10px', border: '1px solid var(--border)', borderRadius: 6, cursor: 'pointer', fontSize: 12 }}><Upload size={14} style={{ verticalAlign: 'middle', marginRight: 5 }} />{keystore.name || '上传 keystore'}<input type="file" accept=".jks,.keystore,.p12" hidden onChange={(e) => uploadCredential(e.target.files?.[0], setKeystore)} /></label>
              <input value={keyAlias} onChange={(e) => setKeyAlias(e.target.value)} placeholder="密钥别名" style={inputStyle} />
              <input type="password" value={storePassword} onChange={(e) => setStorePassword(e.target.value)} placeholder="keystore 密码" style={inputStyle} />
              <input type="password" value={keyPassword} onChange={(e) => setKeyPassword(e.target.value)} placeholder="密钥密码（可留空）" style={inputStyle} />
            </>}
          </div>
        </div>
      )}

      {target === 'miniprogram' && (
        <div style={{ padding: 12, borderBottom: '1px solid var(--border)', background: 'var(--bg-secondary)', display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <input value={miniAppid} onChange={(e) => setMiniAppid(e.target.value)} placeholder="微信 AppID（可暂不填）" style={inputStyle} />
          <label style={{ padding: '7px 10px', border: '1px solid var(--border)', borderRadius: 6, cursor: 'pointer', fontSize: 12 }}><Upload size={14} style={{ verticalAlign: 'middle', marginRight: 5 }} />{miniKey.name || '上传代码上传私钥'}<input type="file" accept=".key,.pem" hidden onChange={(e) => uploadCredential(e.target.files?.[0], setMiniKey)} /></label>
          <input value={version} onChange={(e) => setVersion(e.target.value)} placeholder="版本号" style={{ ...inputStyle, width: 110 }} />
        </div>
      )}

      <div role="group" aria-label="发布目标" style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(76px, 1fr))', gap: 6,
        padding: 6, background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8,
      }}>
        {targets.map((item) => {
          const Icon = item.icon
          const selected = target === item.value
          return (
            <button key={item.value} type="button" onClick={() => setTarget(item.value)} disabled={isDeploying}
              aria-pressed={selected}
              style={{
                minWidth: 0, minHeight: 38, borderRadius: 6, border: selected ? '1px solid var(--accent)' : '1px solid transparent',
                color: selected ? 'var(--accent)' : 'var(--text-secondary)', background: selected ? 'var(--accent-bg)' : 'transparent',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, cursor: isDeploying ? 'not-allowed' : 'pointer',
                fontSize: 12, fontWeight: selected ? 600 : 500,
              }}>
              <Icon size={15} aria-hidden="true" />
              <span>{item.label}</span>
            </button>
          )
        })}
      </div>

      <section aria-label="流水线进度" style={{ padding: 12, border: '1px solid var(--border)', background: 'var(--bg-secondary)', borderRadius: 8, flexShrink: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 8, fontSize: 12 }}>
          <strong>{currentStage ? `当前阶段：${PIPELINE_STEPS.find((step) => step.key === currentStage)?.label || currentStage}` : '流水线尚未启动'}</strong>
          <span style={{ color: deployStatus === 'failed' ? 'var(--red)' : 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>{progressPercent}%</span>
        </div>
        <div role="progressbar" aria-label="部署进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow={progressPercent} style={{ height: 6, borderRadius: 3, background: 'var(--bg-tertiary)', overflow: 'hidden', marginBottom: 12 }}>
          <div style={{ width: `${progressPercent}%`, height: '100%', background: deployStatus === 'failed' ? 'var(--red)' : deployStatus === 'success' ? 'var(--green)' : 'var(--accent)', transition: 'width 0.3s ease' }} />
        </div>
        <div style={{ overflowX: 'auto' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(56px, 1fr))', minWidth: 440, gap: 4 }}>
            {PIPELINE_STEPS.map((step, index) => {
              const isCurrent = step.key === currentStage
              const completed = visitedStages.has(step.key) && !isCurrent
              const skipped = currentStepIndex > index && !visitedStages.has(step.key)
              const failed = isCurrent && deployStatus === 'failed'
              const cancelled = isCurrent && deployStatus === 'cancelled'
              const color = failed ? 'var(--red)' : cancelled ? 'var(--orange)' : completed || (isCurrent && deployStatus === 'success') ? 'var(--green)' : isCurrent ? 'var(--accent)' : 'var(--text-muted)'
              return (
                <div key={step.key} style={{ minWidth: 0, textAlign: 'center', color }}>
                  <div style={{ width: 20, height: 20, margin: '0 auto 4px', borderRadius: '50%', border: `1px solid ${color}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, background: isCurrent ? 'var(--accent-bg)' : 'transparent' }}>
                    {completed ? <Check size={12} /> : failed ? '!' : cancelled ? '×' : index + 1}
                  </div>
                  <div style={{ fontSize: 10, whiteSpace: 'nowrap' }}>{step.label}</div>
                  {skipped && <div style={{ fontSize: 9, marginTop: 2 }}>跳过</div>}
                </div>
              )
            })}
          </div>
        </div>
      </section>

      {/* Terminal View Container */}
      <div style={{
        flex: 1,
        background: 'var(--code-bg)',
        borderRadius: 12,
        border: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        position: 'relative',
        height: 'calc(100vh - 250px)'
      }}>
        {/* Window controls bar */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '10px 16px',
          background: 'var(--bg-tertiary)',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0
        }}>
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--red)', display: 'inline-block' }} />
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--orange)', display: 'inline-block' }} />
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--green)', display: 'inline-block' }} />
          <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginLeft: 12, letterSpacing: 0.5 }}>
            CLOUD_TERMINAL@AGENTS_SERVER
          </span>
          {['failed', 'cancelled'].includes(deployStatus) && deployJobId && (
            <a href={`/api/deployments/${deployJobId}/logs`} download title="下载任务日志" style={{ marginLeft: 'auto', color: deployStatus === 'failed' ? 'var(--red)' : 'var(--orange)', display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11, textDecoration: 'none' }}>
              <FileDown size={14} />任务日志
            </a>
          )}
        </div>

        {/* Terminal logs area */}
        <div style={{
          flex: 1,
          padding: 20,
          overflowY: 'auto',
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
          lineHeight: 1.8,
          color: 'var(--accent)'
        }}>
          {visibleLogs.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 8 }}>
              <Boxes size={32} opacity={0.3} aria-hidden="true" />
              <span>等待启动部署流程...</span>
            </div>
          ) : (
            visibleLogs.map((entry, index) => {
              const log = entry.message || ''
              const isSuccess = entry.level === 'success' || log.includes('成功') || log.includes('SUCCESS')
              const isError = entry.level === 'error'
              const isInfo = log.includes('编译') || log.includes('运行') || log.includes('Docker')
              return (
                <div key={index} style={{
                  color: isError ? 'var(--red)' : isSuccess ? 'var(--green)' : isInfo ? 'var(--accent)' : 'var(--text-secondary)',
                  marginBottom: 6,
                  wordBreak: 'break-word',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 8
                }}>
                  <span style={{ color: 'var(--text-muted)', userSelect: 'none', opacity: 0.5 }}>
                    [{entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString()}]
                  </span>
                  {entry.stage && <span style={{ color: 'var(--text-muted)' }}>[{PIPELINE_STEPS.find((step) => step.key === entry.stage)?.label || entry.stage}]</span>}
                  <span>{log}</span>
                </div>
              )
            })
          )}
          {isDeploying && (
            <div style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6, marginTop: 12 }}>
              <span className="deploy-pulse-dot" />
              <span>部署守护进程正在打包中，请稍候...</span>
            </div>
          )}
          <div ref={terminalEndRef} />
        </div>

        {/* Success Modal / Card Overlay */}
        {deployStatus === 'success' && deployedUrl && (
          <div style={{
            position: 'absolute',
            top: 0, left: 0, right: 0, bottom: 0,
            background: 'var(--bg-primary)',
            opacity: 0.92,
            backdropFilter: 'blur(12px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 24,
            animation: 'fadeIn 0.4s ease-out'
          }}>
            <div style={{
              width: '100%',
              maxWidth: 420,
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              boxShadow: 'var(--shadow-lg)',
              borderRadius: 16,
              padding: 28,
              textAlign: 'center',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 16
            }}>
              <div style={{
                width: 64, height: 64, borderRadius: '50%',
                background: 'var(--accent-bg)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                animation: 'pulseGlow 2s infinite'
              }}>
                <Check size={32} color="var(--green)" aria-hidden="true" />
              </div>
              <div>
                <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
                  {isMiniUploaded ? '小程序代码上传成功' : isDownload ? `${targetName} 构建完成` : `${targetName} 发布成功`}
                </h3>
                <p style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  {isMiniUploaded ? '代码已上传到微信平台，并保留了一份工程备份包。' : isDownload ? '构建产物已保存，可通过下方链接获取。' : '项目已发布到公网，可直接访问。'}
                </p>
              </div>

              {/* URL Display Box */}
              <div style={{
                width: '100%',
                padding: '12px 14px',
                background: 'var(--bg-tertiary)',
                border: '1px solid var(--border)',
                borderRadius: 10,
                fontSize: 12,
                fontFamily: 'var(--font-mono)',
                color: 'var(--cyan)',
                wordBreak: 'break-all',
                textAlign: 'left',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 8
              }}>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                  {deployedUrl}
                </span>
                <span style={{ fontSize: 10, background: 'var(--accent-bg)', padding: '2px 6px', borderRadius: 4, flexShrink: 0, color: 'var(--green)' }}>
                  {isDownload ? 'Artifact' : 'Online'}
                </span>
              </div>

              <div style={{ display: 'flex', gap: 10, width: '100%', marginTop: 8 }}>
                <button
                  onClick={handleVisitSite}
                  style={{
                    flex: 1,
                    padding: '10px 16px',
                    background: 'var(--green)',
                    color: '#fff',
                    border: 'none',
                    fontWeight: 600,
                    fontSize: 13,
                    borderRadius: 8,
                    transition: 'all 0.2s',
                    cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                  }}
                >
                  {isMiniUploaded ? <><Download size={15} />下载工程备份</> : isDownload ? <><Download size={15} />下载构建产物</> : <><ExternalLink size={15} />访问线上地址</>}
                </button>
                <button
                  onClick={handleDeploy}
                  style={{
                    flex: 1,
                    padding: '10px 16px',
                    background: 'var(--bg-tertiary)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-primary)',
                    fontWeight: 600,
                    fontSize: 13,
                    borderRadius: 8,
                    transition: 'all 0.2s',
                    cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                  }}
                >
                  <RotateCw size={15} />重新构建
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      <section style={{ borderTop: '1px solid var(--border)', paddingTop: 12, flexShrink: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 13, fontWeight: 600 }}><History size={16} />发布历史</div>
          <button type="button" onClick={cleanupHistory} title="清理过期产物" style={iconCommandStyle}><Trash2 size={14} />清理过期</button>
        </div>
        {historyMessage && <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>{historyMessage}</div>}
        <div style={{ display: 'grid', gap: 1, background: 'var(--border)', overflowX: 'auto' }}>
          {history.length === 0 ? <div style={{ padding: 12, background: 'var(--bg-primary)', color: 'var(--text-muted)', fontSize: 12 }}>暂无发布记录</div> : history.map((job) => (
            <div key={job.id} style={{ display: 'grid', gridTemplateColumns: '70px minmax(80px, 1fr) 80px minmax(120px, auto)', minWidth: 380, gap: 8, alignItems: 'center', padding: '9px 10px', background: 'var(--bg-primary)', fontSize: 11 }}>
              <strong style={{ textTransform: 'uppercase' }}>{job.target}</strong>
              <span style={{ color: job.status === 'success' ? 'var(--green)' : job.status === 'failed' ? 'var(--red)' : job.status === 'cancelled' ? 'var(--orange)' : 'var(--accent)' }}>{job.lifecycle === 'offline' ? '已下线' : job.status === 'cancelled' ? '已取消' : job.status}</span>
              <span style={{ color: 'var(--text-muted)' }}>{new Date(job.created_at).toLocaleString([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</span>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 5, flexWrap: 'wrap' }}>
                <button title="重试" onClick={() => retryHistory(job)} style={historyIconStyle}><RotateCw size={13} /></button>
                {job.provider === 'docker-runtime' && <button title="回滚到此版本" onClick={() => runHistoryAction(job, 'rollback')} style={historyIconStyle}><RotateCcw size={13} /></button>}
                {job.provider === 'docker-runtime' && job.lifecycle !== 'offline' && <button title="下线" onClick={() => runHistoryAction(job, 'offline')} style={historyIconStyle}><Power size={13} /></button>}
                {['failed', 'cancelled'].includes(job.status) && <a title="下载任务日志" href={`/api/deployments/${job.id}/logs`} download style={historyIconStyle}><FileDown size={13} /></a>}
                {job.url && <button title="打开产物或地址" onClick={() => window.open(job.url, '_blank', 'noopener,noreferrer')} style={historyIconStyle}><ExternalLink size={13} /></button>}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

const inputStyle = { minWidth: 150, padding: '7px 9px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: 12 }
const iconCommandStyle = { display: 'flex', alignItems: 'center', gap: 5, padding: '6px 9px', borderRadius: 6, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 11 }
const historyIconStyle = { width: 28, height: 28, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', borderRadius: 6, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer' }
