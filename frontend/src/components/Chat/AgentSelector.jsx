import React from 'react'
import { Check, X } from 'lucide-react'
import { useAgentStore } from '../../stores/agentStore'
import IconAvatar from '../IconAvatar'

export default function AgentSelector({ onSelect, onClose, multiSelect = false, selected = [], onToggle }) {
  const agents = useAgentStore((s) => s.agents)
  // Exclude builder from quick select
  const selectable = agents.filter((a) => a.agent_id !== 'agent_builder')

  return (
    <div className="agent-selector-overlay" onClick={onClose}>
      <div className="agent-selector" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
          <span className="agent-selector-title">
            {multiSelect ? '选择 Agent' : '选择 Agent 开始对话'}
          </span>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 4, borderRadius: 4 }}
          >
            <X size={18} />
          </button>
        </div>
        <div className="agent-selector-list">
          {selectable.map((agent) => {
            const isSelected = selected.includes(agent.agent_id)
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
                <div style={{ flex: 1 }}>
                  <div className="agent-selector-name">{agent.name}</div>
                  <div className="agent-selector-role">{agent.role}</div>
                </div>
                {isSelected && (
                  <div className="agent-selector-check"><Check size={16} /></div>
                )}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
