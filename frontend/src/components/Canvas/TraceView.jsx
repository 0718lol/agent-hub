import React, { useState, useEffect } from 'react'
import { AlertCircle, RefreshCw } from 'lucide-react'

/**
 * TraceView — Agent execution trace visualization (Gantt-chart style).
 * Shows each agent's execution as a colored bar on a timeline.
 */
export default function TraceView() {
  const [traces, setTraces] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    // Initial fetch for existing traces
    const fetchTraces = async () => {
      try {
        const resp = await fetch('/api/metrics/traces?limit=10')
        if (!resp.ok) throw new Error(`Trace 请求失败 (${resp.status})`)
        const data = await resp.json()
        if (!Array.isArray(data)) throw new Error('Trace 数据格式无效')
        setTraces(data)
        setLoadError('')
      } catch (error) {
        setLoadError(error.message || 'Trace 加载失败')
      } finally {
        setLoading(false)
      }
    }
    fetchTraces()

    // SSE real-time updates
    let es = null
    try {
      es = new EventSource('/api/metrics/traces/stream')
      es.onmessage = (e) => {
        try {
          const trace = JSON.parse(e.data)
          if (trace.type === 'connected') return
          setTraces(prev => {
            const next = [...prev, trace]
            return next.length > 50 ? next.slice(-50) : next
          })
          setLoadError('')
        } catch {}
      }
      es.onerror = () => {
        // EventSource auto-reconnects, no action needed
      }
    } catch {}

    return () => {
      if (es) es.close()
    }
  }, [reloadToken])

  if (loading) return <div style={{ padding: 24, color: 'var(--text-muted)' }}>加载 Trace...</div>

  if (!traces.length) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
        {loadError ? (
          <>
            <AlertCircle size={32} style={{ marginBottom: 12, color: '#f87171' }} />
            <div style={{ color: '#fca5a5' }}>{loadError}</div>
            <button
              type="button"
              onClick={() => {
                setLoading(true)
                setReloadToken(token => token + 1)
              }}
              style={{
                marginTop: 12, height: 30, padding: '0 10px', borderRadius: 4,
                border: '1px solid var(--border)', background: 'var(--bg-secondary)',
                color: 'var(--text-primary)', cursor: 'pointer', display: 'inline-flex',
                alignItems: 'center', gap: 6,
              }}
            >
              <RefreshCw size={13} />
              重新加载
            </button>
          </>
        ) : (
          <>
            <div>还没有执行记录</div>
            <div style={{ marginTop: 8, fontSize: 12 }}>与 Agent 对话后，执行链路将自动展示</div>
          </>
        )}
      </div>
    )
  }

  return (
    <div style={{ padding: 16, overflow: 'auto', height: '100%' }}>
      <h3 style={{ margin: '0 0 16px', fontSize: 15, color: 'var(--text-primary)' }}>🔍 执行 Trace</h3>
      {loadError && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 7, marginBottom: 12, padding: '8px 10px',
          borderRadius: 6, border: '1px solid rgba(239,68,68,0.28)',
          background: 'rgba(239,68,68,0.08)', color: '#fca5a5', fontSize: 12,
        }}>
          <AlertCircle size={14} />
          <span>{loadError}，当前展示最近一次成功加载的数据。</span>
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {traces.slice().reverse().map((trace) => (
          <TraceCard key={trace.task_id} trace={trace} />
        ))}
      </div>
    </div>
  )
}

const AGENT_COLORS = {
  agent_pm: '#6366f1',
  agent_frontend: '#f59e0b',
  agent_backend: '#10b981',
  agent_tester: '#8b5cf6',
  agent_devops: '#ef4444',
  agent_designer: '#ec4899',
  agent_builder: '#06b6d4',
}

function TraceCard({ trace }) {
  if (!trace.steps || trace.steps.length === 0) return null

  const totalMs = trace.total_duration_ms || 1
  const startBase = trace.steps[0]?.start_time || 0

  return (
    <div style={{
      padding: 12, borderRadius: 10,
      background: 'var(--bg-secondary)', border: '1px solid var(--border)',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 500 }}>
          {trace.user_input}
        </span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          总耗时 {trace.total_duration_ms}ms | {trace.total_tokens} tokens
        </span>
      </div>

      {/* Gantt bars */}
      <div style={{ position: 'relative', minHeight: trace.steps.length * 28 + 4 }}>
        {trace.steps.map((step, i) => {
          const offset = ((step.start_time - startBase) * 1000) / totalMs
          const width = step.duration_ms / totalMs
          const color = AGENT_COLORS[step.agent_id] || '#64748b'

          return (
            <div
              key={i}
              style={{
                position: 'absolute',
                top: i * 28,
                left: `${Math.max(0, offset * 100)}%`,
                width: `${Math.max(width * 100, 8)}%`,
                height: 22,
                borderRadius: 4,
                background: color,
                opacity: 0.85,
                display: 'flex',
                alignItems: 'center',
                paddingLeft: 6,
                fontSize: 10,
                color: 'white',
                fontWeight: 500,
                overflow: 'hidden',
                whiteSpace: 'nowrap',
                transition: 'all 0.3s ease',
              }}
              title={`${step.agent_id}: ${step.duration_ms}ms, score: ${step.quality_score}`}
            >
              {step.agent_id.replace('agent_', '')} {step.duration_ms}ms
              {step.quality_score > 0 && ` (${step.quality_score}分)`}
            </div>
          )
        })}
      </div>

      {/* Timeline axis */}
      <div style={{
        marginTop: 8, display: 'flex', justifyContent: 'space-between',
        fontSize: 10, color: 'var(--text-muted)',
        borderTop: '1px solid var(--border)', paddingTop: 4,
      }}>
        <span>0ms</span>
        <span>{Math.round(totalMs / 2)}ms</span>
        <span>{totalMs}ms</span>
      </div>
    </div>
  )
}
