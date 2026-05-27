import React from 'react'
import { ListTodo, ChevronRight } from 'lucide-react'
import { useCanvasStore } from '../../stores/canvasStore'
import TaskBoard from '../Canvas/TaskBoard'

export default function InlineTaskCard() {
  const tasks = useCanvasStore((s) => s.tasks)
  const doneCount = tasks.filter((t) => t.status === 'done').length
  const doingCount = tasks.filter((t) => t.status === 'doing').length

  if (tasks.length === 0) return null

  return (
    <details className="inline-card">
      <summary className="inline-card-header" style={{ cursor: 'pointer', listStyle: 'none' }}>
        <span className="icon"><ListTodo size={16} /></span>
        <span>任务看板</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto', marginRight: 8 }}>
          {doneCount}/{tasks.length} 完成
          {doingCount > 0 && <span style={{ color: 'var(--accent)' }}> · {doingCount} 进行中</span>}
        </span>
        <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
      </summary>
      <div style={{ marginTop: 8 }}>
        <TaskBoard compact />
      </div>
    </details>
  )
}
