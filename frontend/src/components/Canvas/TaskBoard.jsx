import React, { useState, useCallback } from 'react'
import { Plus, X } from 'lucide-react'
import { useCanvasStore } from '../../stores/canvasStore'
import { useAgentStore } from '../../stores/agentStore'

const COLUMNS = [
  { key: 'todo', label: '待办', color: 'var(--text-muted)' },
  { key: 'doing', label: '进行中', color: 'var(--accent)' },
  { key: 'done', label: '已完成', color: 'var(--green)' },
]

export default function TaskBoard({ compact = false }) {
  const tasks = useCanvasStore((s) => s.tasks)
  const moveTask = useCanvasStore((s) => s.moveTask)
  const addTask = useCanvasStore((s) => s.addTask)
  const deleteTask = useCanvasStore((s) => s.deleteTask)
  const changeTaskStatus = useCanvasStore((s) => s.changeTaskStatus)
  const agents = useAgentStore((s) => s.agents)

  const [showCreate, setShowCreate] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newAssignee, setNewAssignee] = useState('agent_designer')
  const [draggedId, setDraggedId] = useState(null)
  const [dragOverCol, setDragOverCol] = useState(null)

  const total = tasks.length
  const doneCount = tasks.filter((t) => t.status === 'done').length
  const progress = total > 0 ? Math.round((doneCount / total) * 100) : 0

  const handleCreate = () => {
    if (!newTitle.trim()) return
    addTask({ title: newTitle.trim(), assignee: newAssignee, status: 'todo' })
    setNewTitle('')
    setNewAssignee('agent_designer')
    setShowCreate(false)
  }

  // Drag handlers
  const handleDragStart = useCallback((e, taskId) => {
    setDraggedId(taskId)
    e.dataTransfer.effectAllowed = 'move'
  }, [])

  const handleDragOver = useCallback((e, colKey) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOverCol(colKey)
  }, [])

  const handleDragLeave = useCallback(() => {
    setDragOverCol(null)
  }, [])

  const handleDrop = useCallback((e, colKey) => {
    e.preventDefault()
    if (draggedId) {
      changeTaskStatus(draggedId, colKey)
    }
    setDraggedId(null)
    setDragOverCol(null)
  }, [draggedId, changeTaskStatus])

  const handleDragEnd = useCallback(() => {
    setDraggedId(null)
    setDragOverCol(null)
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 12 }}>
      {/* Header */}
      {!compact && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0,
          padding: '0 4px',
        }}>
          <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>任务看板</span>

          {/* Progress bar */}
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              flex: 1, height: 4, borderRadius: 2,
              background: 'var(--border)', overflow: 'hidden',
            }}>
              <div style={{
                width: `${progress}%`, height: '100%', borderRadius: 2,
                background: progress === 100 ? 'var(--green)' : 'var(--accent)',
                transition: 'width 0.4s ease',
              }} />
            </div>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
              {doneCount}/{total}
            </span>
          </div>

          {/* New task button */}
          <button
            onClick={() => setShowCreate(!showCreate)}
            style={{
              width: 28, height: 28, borderRadius: 6,
              background: showCreate ? 'var(--accent-bg)' : 'var(--bg-secondary)',
              border: '1px solid var(--border)', color: showCreate ? 'var(--accent)' : 'var(--text-muted)',
              cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}
            title="新建任务"
          >
            <Plus size={14} />
          </button>
        </div>
      )}

      {/* Create form */}
      {showCreate && !compact && (
        <div style={{
          padding: '10px 12px', borderRadius: 8,
          background: 'var(--bg-secondary)', border: '1px solid var(--border)',
          display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0,
        }}>
          <input
            autoFocus
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            placeholder="任务标题"
            style={{
              flex: 1, padding: '6px 8px', borderRadius: 6,
              background: 'var(--bg-primary)', border: '1px solid var(--border)',
              color: 'var(--text-primary)', fontSize: 12, outline: 'none',
            }}
          />
          <select
            value={newAssignee}
            onChange={(e) => setNewAssignee(e.target.value)}
            style={{
              padding: '6px 8px', borderRadius: 6,
              background: 'var(--bg-primary)', border: '1px solid var(--border)',
              color: 'var(--text-primary)', fontSize: 12,
            }}
          >
            {agents.filter((a) => a.agent_id !== 'agent_builder').map((a) => (
              <option key={a.agent_id} value={a.agent_id}>{a.avatar} {a.name}</option>
            ))}
          </select>
          <button
            onClick={handleCreate}
            disabled={!newTitle.trim()}
            style={{
              padding: '6px 12px', borderRadius: 6, fontSize: 12,
              background: newTitle.trim() ? 'var(--accent)' : 'var(--bg-tertiary)',
              border: 'none', color: newTitle.trim() ? '#fff' : 'var(--text-muted)',
              cursor: newTitle.trim() ? 'pointer' : 'default',
            }}
          >
            添加
          </button>
        </div>
      )}

      {/* Columns */}
      <div style={{
        flex: 1, display: 'flex', gap: 10, minHeight: 0,
        overflowX: 'auto',
      }}>
        {COLUMNS.map((col) => {
          const colTasks = tasks.filter((t) => t.status === col.key)
          const isDragOver = dragOverCol === col.key

          return (
            <div
              key={col.key}
              onDragOver={(e) => handleDragOver(e, col.key)}
              onDragLeave={handleDragLeave}
              onDrop={(e) => handleDrop(e, col.key)}
              style={{
                flex: 1, minWidth: 140, display: 'flex', flexDirection: 'column',
                borderRadius: 10, overflow: 'hidden',
                background: isDragOver ? 'var(--accent-bg)' : 'var(--bg-secondary)',
                border: isDragOver ? '2px dashed var(--accent)' : '1px solid var(--border)',
                transition: 'all 0.15s',
              }}
            >
              {/* Column header */}
              <div style={{
                padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 6,
                borderBottom: '1px solid var(--border)', flexShrink: 0,
              }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: col.color }} />
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{col.label}</span>
                <span style={{
                  fontSize: 10, color: 'var(--text-muted)',
                  marginLeft: 'auto',
                  background: 'var(--bg-tertiary)', padding: '1px 6px', borderRadius: 4,
                }}>{colTasks.length}</span>
              </div>

              {/* Task cards */}
              <div style={{ flex: 1, padding: 8, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
                {colTasks.map((task) => {
                  const agent = agents.find((a) => a.agent_id === task.assignee)
                  const isDragging = draggedId === task.id

                  return (
                    <div
                      key={task.id}
                      draggable
                      onDragStart={(e) => handleDragStart(e, task.id)}
                      onDragEnd={handleDragEnd}
                      style={{
                        padding: '8px 10px', borderRadius: 8,
                        background: isDragging ? 'var(--accent-bg)' : 'var(--bg-primary)',
                        border: isDragging ? '1px solid var(--accent)' : '1px solid var(--border)',
                        cursor: 'grab', opacity: isDragging ? 0.5 : 1,
                        display: 'flex', alignItems: 'center', gap: 8,
                        transition: 'opacity 0.15s',
                        position: 'relative',
                      }}
                    >
                      {/* Status bar */}
                      <div style={{
                        width: 3, height: 24, borderRadius: 2, flexShrink: 0,
                        background: col.color,
                      }} />

                      {/* Title */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{
                          fontSize: 12, color: 'var(--text-primary)',
                          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                        }}>{task.title}</div>
                      </div>

                      {/* Agent avatar */}
                      {agent && (
                        <div style={{
                          fontSize: 14, flexShrink: 0,
                        }}>{agent.avatar}</div>
                      )}

                      {/* Delete button */}
                      <button
                        onClick={(e) => { e.stopPropagation(); deleteTask(task.id) }}
                        style={{
                          position: 'absolute', top: 4, right: 4,
                          width: 16, height: 16, borderRadius: 4,
                          background: 'none', border: 'none',
                          color: 'var(--text-muted)', cursor: 'pointer',
                          display: 'none', alignItems: 'center', justifyContent: 'center',
                          fontSize: 10,
                        }}
                        className="task-delete-btn"
                        title="删除任务"
                      >
                        <X size={10} />
                      </button>
                    </div>
                  )
                })}

                {colTasks.length === 0 && (
                  <div style={{
                    textAlign: 'center', padding: '16px 0',
                    fontSize: 11, color: 'var(--text-muted)',
                  }}>
                    拖拽任务到此处
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
