import React from 'react'
import { useCanvasStore } from '../../stores/canvasStore'
import { useAgentStore } from '../../stores/agentStore'

export default function TaskBoard({ compact = false }) {
  const tasks = useCanvasStore((s) => s.tasks)
  const moveTask = useCanvasStore((s) => s.moveTask)
  const agents = useAgentStore((s) => s.agents)

  const columns = [
    { key: 'todo', label: '待办', color: '#94a3b8' },
    { key: 'doing', label: '进行中', color: '#6366f1' },
    { key: 'done', label: '已完成', color: '#10b981' },
  ]

  const handleMove = (taskId, currentStatus) => {
    const order = ['todo', 'doing', 'done']
    const idx = order.indexOf(currentStatus)
    if (idx < order.length - 1) {
      moveTask(taskId, order[idx + 1])
    }
  }

  return (
    <div className="task-board">
      {columns.map((col) => {
        const colTasks = tasks.filter((t) => t.status === col.key)
        return (
          <div key={col.key} className="task-column">
            {!compact && (
              <div className="task-column-header">
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: col.color }} />
                {col.label}
                <span className="count">{colTasks.length}</span>
              </div>
            )}
            {colTasks.map((task) => {
              const agent = agents.find((a) => a.agent_id === task.assignee)
              return (
                <div
                  key={task.id}
                  className="task-card"
                  style={{ padding: compact ? '8px 10px' : undefined }}
                  onClick={() => handleMove(task.id, task.status)}
                >
                  <div className="task-title" style={compact ? {
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    fontSize: 12,
                  } : undefined}>{task.title}</div>
                  {!compact && (
                    <div className="task-meta">
                      <div className="task-assignee">
                        <span>{agent?.avatar}</span>
                        <span>{agent?.name}</span>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )
      })}
    </div>
  )
}
