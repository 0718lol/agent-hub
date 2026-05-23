import React from 'react'
import { GitGraph, ChevronRight } from 'lucide-react'
import { useCanvasStore } from '../../stores/canvasStore'
import AgentDAG from '../Canvas/AgentDAG'

export default function InlineDAGCard() {
  const nodes = useCanvasStore((s) => s.dagNodes)
  const activeCount = nodes.filter((n) => n.status === 'working').length
  const doneCount = nodes.filter((n) => n.status === 'done').length

  if (nodes.length === 0) return null

  return (
    <details className="inline-card">
      <summary className="inline-card-header" style={{ cursor: 'pointer', listStyle: 'none' }}>
        <span className="icon"><GitGraph size={16} /></span>
        <span>协作图</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto', marginRight: 8 }}>
          {doneCount}/{nodes.length} 完成
          {activeCount > 0 && <span style={{ color: 'var(--accent)' }}> · 工作中</span>}
        </span>
        <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
      </summary>
      <div style={{ height: 240, marginTop: 8 }}>
        <AgentDAG compact />
      </div>
    </details>
  )
}
