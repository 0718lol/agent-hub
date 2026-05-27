import React, { useState, useEffect } from 'react'
import { Check, X, Plus, Trash2 } from 'lucide-react'
import { useAgentStore } from '../../stores/agentStore'
import IconAvatar from '../IconAvatar'
import AgentCreator from './AgentCreator'

export default function AgentSelector({ onSelect, onClose, multiSelect = false, selected = [], onToggle }) {
  const agents = useAgentStore((s) => s.agents)
  const deletedPresetIds = useAgentStore((s) => s.deletedPresetIds)
  const loadCustomAgents = useAgentStore((s) => s.loadCustomAgents)
  const removeAgent = useAgentStore((s) => s.removeAgent)

  const [showCreator, setShowCreator] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)

  // Exclude builder and deleted presets
  const visibleAgents = agents.filter(
    (a) => a.agent_id !== 'agent_builder' && !deletedPresetIds.includes(a.agent_id)
  )

  useEffect(() => {
    loadCustomAgents()
  }, [])

  const handleDelete = async (agentId) => {
    await removeAgent(agentId)
    setConfirmDeleteId(null)
  }

  const handleCreateClick = () => {
    setShowCreator(true)
  }

  return (
    <>
      {/* 选择 Agent 弹窗 */}
      {!showCreator && (
        <div className="agent-selector-overlay" onClick={onClose}>
          <div className="agent-selector" onClick={(e) => e.stopPropagation()}>
            <div className="agent-selector-header">
              <span className="agent-selector-title">
                {multiSelect ? '选择 Agent' : '选择 Agent 开始对话'}
              </span>
              <button className="agent-selector-close" onClick={onClose}>
                <X size={18} />
              </button>
            </div>

            <div className="agent-selector-list">
              {visibleAgents.map((agent) => {
                const isSelected = selected.includes(agent.agent_id)
                const isConfirming = confirmDeleteId === agent.agent_id

                if (isConfirming) {
                  return (
                    <div key={agent.agent_id} className="agent-delete-confirm">
                      <span>确定删除「{agent.name}」？</span>
                      <div className="agent-delete-confirm-actions">
                        <button
                          className="agent-delete-btn danger"
                          onClick={() => handleDelete(agent.agent_id)}
                        >
                          删除
                        </button>
                        <button
                          className="agent-delete-btn"
                          onClick={() => setConfirmDeleteId(null)}
                        >
                          取消
                        </button>
                      </div>
                    </div>
                  )
                }

                return (
                  <button
                    key={agent.agent_id}
                    className={`agent-selector-item ${isSelected ? 'selected' : ''}`}
                    onClick={() => {
                      if (multiSelect && onToggle) {
                        onToggle(agent.agent_id)
                      } else {
                        onSelect(agent.agent_id)
                      }
                    }}
                  >
                    <div className="agent-selector-avatar">
                      <IconAvatar agentId={agent.agent_id} size={22} />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="agent-selector-name">{agent.name}</div>
                      <div className="agent-selector-role">{agent.role}</div>
                    </div>
                    {isSelected && (
                      <div className="agent-selector-check"><Check size={16} /></div>
                    )}
                    <button
                      className="agent-selector-delete"
                      onClick={(e) => {
                        e.stopPropagation()
                        setConfirmDeleteId(agent.agent_id)
                      }}
                      title="删除此 Agent"
                    >
                      <Trash2 size={14} />
                    </button>
                  </button>
                )
              })}

              {visibleAgents.length === 0 && (
                <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 'var(--text-sm)', padding: 'var(--space-5) 0' }}>
                  暂无可选 Agent
                </div>
              )}
            </div>

            <button className="agent-create-entry" onClick={handleCreateClick}>
              <Plus size={16} />
              <span>自定义 Agent</span>
            </button>
          </div>
        </div>
      )}

      {/* 创建 Agent 弹窗（独立层级，更高 z-index） */}
      {showCreator && (
        <AgentCreator
          onClose={() => { setShowCreator(false); onClose() }}
          onBack={() => setShowCreator(false)}
        />
      )}
    </>
  )
}
