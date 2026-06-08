/**
 * TraceTreeView — Interactive tree visualization for agent execution traces.
 * 
 * Based on: Langfuse trace tree design pattern.
 * Zero external dependencies — pure React recursive component.
 * Uses project CSS variables for theming.
 */
import { useState } from 'react'

function TraceNode({ span, depth = 0 }) {
  const [expanded, setExpanded] = useState(depth < 2)
  const hasChildren = span.spans?.length > 0 || span.children?.length > 0
  const children = span.spans || span.children || []

  const statusColor = {
    success: 'var(--success, #22c55e)',
    error: 'var(--danger, #ef4444)',
    timeout: 'var(--warning, #f59e0b)',
    skipped: 'var(--text-muted, #6b7280)',
    running: 'var(--accent, #6366f1)',
  }[span.status] || 'var(--text-muted)'

  const typeIcon = {
    llm: '🤖',
    tool: '🔧',
    rag: '📚',
    agent: '👤',
    custom: '⚙️',
  }[span.span_type] || '•'

  return (
    <div style={{ marginLeft: depth > 0 ? 20 : 0 }}>
      <div
        onClick={() => hasChildren && setExpanded(!expanded)}
        style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px',
          cursor: hasChildren ? 'pointer' : 'default',
          borderRadius: 6, marginBottom: 2,
          background: expanded ? 'var(--bg-hover, rgba(255,255,255,0.03))' : 'transparent',
        }}
      >
        <span style={{ width: 16, textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }}>
          {hasChildren ? (expanded ? '▼' : '▶') : '·'}
        </span>
        <span style={{ fontSize: 14 }}>{typeIcon}</span>
        <span style={{ flex: 1, fontWeight: 500 }}>{span.name}</span>
        {span.duration_ms > 0 && (
          <span style={{ fontSize: 12, color: 'var(--text-muted)', minWidth: 50, textAlign: 'right' }}>
            {span.duration_ms < 1000 ? `${span.duration_ms}ms` : `${(span.duration_ms / 1000).toFixed(1)}s`}
          </span>
        )}
        {span.tokens_used > 0 && (
          <span style={{ fontSize: 12, color: 'var(--text-muted)', minWidth: 60, textAlign: 'right' }}>
            {span.tokens_used} tok
          </span>
        )}
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: statusColor, flexShrink: 0 }} />
        {span.error && (
          <span style={{ fontSize: 11, color: 'var(--danger)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={span.error}>
            {span.error}
          </span>
        )}
      </div>
      {expanded && children.map((child, i) => (
        <TraceNode key={child.name + i} span={child} depth={depth + 1} />
      ))}
    </div>
  )
}

export default function TraceTreeView({ trace }) {
  if (!trace) return null

  const rootSpan = {
    name: trace.user_input || 'User Request',
    span_type: 'custom',
    duration_ms: trace.total_duration_ms,
    status: trace.status || 'success',
    spans: trace.steps?.map(step => ({
      name: `${step.agent_name} (${step.agent_id})`,
      span_type: 'agent',
      duration_ms: step.duration_ms,
      tokens_used: step.tokens_used,
      status: step.status,
      spans: step.spans || [],
    })) || [],
  }

  return (
    <div style={{ padding: 16, fontFamily: 'var(--font-mono, monospace)' }}>
      <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontWeight: 600 }}>Execution Trace</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {trace.total_duration_ms < 1000 ? `${trace.total_duration_ms}ms` : `${(trace.total_duration_ms / 1000).toFixed(1)}s`}
        </span>
        {trace.task_id && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>#{trace.task_id}</span>}
      </div>
      <TraceNode span={rootSpan} depth={0} />
    </div>
  )
}
