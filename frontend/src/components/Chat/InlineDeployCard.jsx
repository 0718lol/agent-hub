import React, { useState } from 'react'
import { Terminal, ExternalLink, ChevronRight, X } from 'lucide-react'
import { useCanvasStore } from '../../stores/canvasStore'

export default function InlineDeployCard() {
  const logs = useCanvasStore((s) => s.deployLogs)
  const status = useCanvasStore((s) => s.deployStatus)
  const url = useCanvasStore((s) => s.deployedUrl)
  const resetDeploy = useCanvasStore((s) => s.resetDeploy)
  const [expanded, setExpanded] = useState(true)

  if (status === 'idle') return null

  const statusLabel = status === 'running' ? '部署中...' : status === 'success' ? '部署成功' : '部署失败'
  const statusColor = status === 'success' ? 'var(--green)' : status === 'failed' ? 'var(--red)' : 'var(--accent)'

  return (
    <div className="inline-card">
      <div
        className="inline-card-header"
        onClick={() => setExpanded(!expanded)}
        style={{ cursor: 'pointer' }}
      >
        <span className="icon"><Terminal size={16} /></span>
        <span>部署状态</span>
        <span style={{ fontSize: 12, marginLeft: 'auto', marginRight: 8, color: statusColor }}>
          {statusLabel}
        </span>
        <button
          onClick={(e) => { e.stopPropagation(); resetDeploy() }}
          title="关闭"
          style={{
            background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer',
            padding: 2, display: 'flex', alignItems: 'center', marginRight: 4,
          }}
        >
          <X size={14} />
        </button>
        <ChevronRight
          size={14}
          style={{
            color: 'var(--text-muted)',
            transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
            transition: 'transform 0.15s',
          }}
        />
      </div>

      {expanded && (
        <>
          <div style={{
            marginTop: 8, background: 'var(--code-bg)', borderRadius: 'var(--radius-md)',
            padding: 'var(--space-3)', fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)',
            maxHeight: 120, overflow: 'auto', color: 'var(--text-secondary)',
          }}>
            {logs.length === 0 && <span style={{ color: 'var(--text-muted)' }}>等待日志...</span>}
            {logs.slice(-10).map((line, i) => (
              <div key={i} style={{ lineHeight: 1.6 }}>{line}</div>
            ))}
          </div>
          {url && (
            <a href={url} target="_blank" rel="noopener noreferrer" style={{
              display: 'inline-flex', alignItems: 'center', gap: 4, marginTop: 8,
              fontSize: 'var(--text-xs)', color: 'var(--accent)', textDecoration: 'none',
            }}>
              <ExternalLink size={12} /> {url}
            </a>
          )}
        </>
      )}
    </div>
  )
}
