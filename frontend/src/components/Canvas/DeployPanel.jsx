import React, { useRef, useEffect } from 'react'
import { useCanvasStore } from '../../stores/canvasStore'
import { useChatStore } from '../../stores/chatStore'
import { PREVIEW_HTML } from './previewHtml'

export default function DeployPanel() {
  const isDeploying = useCanvasStore((s) => s.isDeploying)
  const deployLogs = useCanvasStore((s) => s.deployLogs)
  const deployedUrl = useCanvasStore((s) => s.deployedUrl)
  const deployStatus = useCanvasStore((s) => s.deployStatus)
  const startDeploy = useCanvasStore((s) => s.startDeploy)
  const failDeploy = useCanvasStore((s) => s.failDeploy)
  const previewHtml = useCanvasStore((s) => s.previewHtml)

  const activeId = useChatStore((s) => s.activeConversationId)
  const terminalEndRef = useRef(null)

  useEffect(() => {
    if (terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [deployLogs])

  const handleDeploy = async () => {
    if (isDeploying || !activeId) return
    startDeploy()
    try {
      const resp = await fetch(`/api/deploy/${activeId}`, { method: 'POST' })
      if (!resp.ok) {
        failDeploy()
      }
    } catch (e) {
      failDeploy()
    }
  }

  const handleVisitSite = () => {
    const htmlToRender = previewHtml || PREVIEW_HTML.todo
    const newWindow = window.open()
    if (newWindow) {
      newWindow.document.write(htmlToRender)
      newWindow.document.close()
    }
  }


  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 16 }}>
      {/* Panel Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '12px 16px', background: 'var(--bg-secondary)', borderRadius: 10,
        border: '1px solid var(--border)', flexShrink: 0
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 20 }}>🚀</span>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>云端部署控制中心</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>提供一键上线及高可靠云原生环境交付</div>
          </div>
        </div>
        <button
          onClick={handleDeploy}
          disabled={isDeploying || deployStatus === 'success'}
          style={{
            padding: '8px 16px',
            background: deployStatus === 'success'
              ? 'var(--accent-bg)'
              : 'var(--accent)',
            color: deployStatus === 'success' ? 'var(--green)' : '#fff',
            border: deployStatus === 'success' ? '1px solid var(--green)' : 'none',
            borderRadius: 8,
            fontSize: 13,
            fontWeight: 600,
            cursor: (isDeploying || deployStatus === 'success') ? 'not-allowed' : 'pointer',
            transition: 'all 0.3s ease',
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}
        >
          {isDeploying ? (
            <>
              <span className="deploy-loader" />
              正在打包发布...
            </>
          ) : deployStatus === 'success' ? (
            <>
              <span>✓</span>
              已上线
            </>
          ) : (
            '一键部署上线'
          )}
        </button>
      </div>

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
          {deployLogs.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 8 }}>
              <span style={{ fontSize: 32, opacity: 0.3 }}>⚙️</span>
              <span>等待启动部署流程...</span>
            </div>
          ) : (
            deployLogs.map((log, index) => {
              const isSuccess = log.includes('成功') || log.includes('SUCCESS')
              const isInfo = log.includes('编译') || log.includes('运行') || log.includes('Docker')
              return (
                <div key={index} style={{
                  color: isSuccess ? 'var(--green)' : isInfo ? 'var(--accent)' : 'var(--text-secondary)',
                  marginBottom: 6,
                  wordBreak: 'break-word',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 8
                }}>
                  <span style={{ color: 'var(--text-muted)', userSelect: 'none', opacity: 0.5 }}>
                    [{new Date().toLocaleTimeString()}]
                  </span>
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
                <span style={{ fontSize: 32, color: 'var(--green)' }}>✓</span>
              </div>
              <div>
                <h3 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>部署发布成功！</h3>
                <p style={{ fontSize: 12, color: 'var(--text-secondary)' }}>项目已在全球分布式 CDN 边缘节点上线。</p>
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
                  Active
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
                    cursor: 'pointer'
                  }}
                >
                  访问线上地址
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
                    cursor: 'pointer'
                  }}
                >
                  重新上线
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
