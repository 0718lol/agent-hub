import React, { useEffect } from 'react'
import { X, Plus, Settings } from 'lucide-react'
import { useAgentStore } from '../../stores/agentStore'
import { useChatStore } from '../../stores/chatStore'
import { useTabStore } from '../../stores/tabStore'
import IconAvatar from '../IconAvatar'

export default function LocalAgentSelector({ onSelect, onOpenSettings, onClose }) {
  const adapterStatus = useAgentStore((s) => s.adapterStatus)
  const fetchAdapterStatus = useAgentStore((s) => s.fetchAdapterStatus)
  const openTab = useTabStore((s) => s.openTab)

  useEffect(() => { fetchAdapterStatus() }, [])

  // 筛选所有 self_deployed 类型的适配器
  const localAgents = Object.entries(adapterStatus)
    .filter(([, s]) => s.adapter_type === 'self_deployed')
    .map(([agentId, status]) => ({
      agentId,
      name: status.display_name || status.name || agentId,
      avatar: status.display_avatar || null,
      desc: status.display_desc || status.model || '本地 Agent',
      configured: status.configured,
    }))

  const handleSelect = (agentId) => {
    const agentConvs = useChatStore.getState().conversations
      .filter((c) => c.agentId === agentId && !c.archived)
      .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))

    if (agentConvs.length > 0) {
      const latest = agentConvs[0]
      const existingTab = useTabStore.getState().openTabs.find((t) => t.convId === latest.id)
      if (existingTab) {
        useTabStore.getState().setActiveTab(existingTab.id)
      } else {
        openTab(latest.id, latest.name, agentId)
      }
    } else {
      const convId = `conv_${agentId}_${Date.now()}`
      const convName = '新对话1'
      useChatStore.getState().addConversation({
        id: convId, type: 'single', agentId, name: convName,
        messages: [], pinned: false, unread: false, updatedAt: Date.now(),
      })
      fetch('/api/conversations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: convId, type: 'single', name: convName, agent_id: agentId }),
      }).catch(() => {})
      openTab(convId, convName, agentId)
    }
    onSelect?.(agentId)
  }

  const handleEdit = (e, agentId) => {
    e.stopPropagation()
    onClose()
    onOpenSettings?.(agentId)
  }

  return (
    <div className="agent-selector-overlay" onClick={onClose}>
      <div className="agent-selector" onClick={(e) => e.stopPropagation()}>
        <div className="agent-selector-header">
          <span className="agent-selector-title">本地 Agent</span>
          <button className="agent-selector-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="agent-selector-list">
          {localAgents.length === 0 ? (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 'var(--text-sm)', padding: 'var(--space-5) 0' }}>
              暂无已配置的本地 Agent
            </div>
          ) : (
            localAgents.map((agent) => (
              <button
                key={agent.agentId}
                className="agent-selector-item"
                onClick={() => handleSelect(agent.agentId)}
              >
                <div className="agent-selector-avatar">
                  {agent.avatar ? (
                    agent.avatar.startsWith('/') || agent.avatar.startsWith('http') ? (
                      <img src={agent.avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : (
                      <span style={{ fontSize: 20 }}>{agent.avatar}</span>
                    )
                  ) : (
                    <IconAvatar agentId={agent.agentId} size={22} />
                  )}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="agent-selector-name">{agent.name}</div>
                  <div className="agent-selector-role">{agent.desc}</div>
                </div>
                <button
                  className="agent-selector-delete"
                  onClick={(e) => handleEdit(e, agent.agentId)}
                  title="编辑配置"
                  style={{ color: 'var(--text-muted)' }}
                >
                  <Settings size={14} />
                </button>
              </button>
            ))
          )}
        </div>

        <button
          className="agent-create-entry"
          onClick={() => { onClose(); onOpenSettings?.() }}
        >
          <Plus size={16} />
          <span>接入新 Agent</span>
        </button>
      </div>
    </div>
  )
}
