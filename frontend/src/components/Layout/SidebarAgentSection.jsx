import React from 'react'
import { Bot, Globe, Cpu, Plus, ChevronRight, Trash2, Lock } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { useTabStore } from '../../stores/tabStore'
import IconAvatar from '../IconAvatar'

export default function SidebarAgentSection({
  agentsExpanded,
  setAgentsExpanded,
  subExpanded,
  setSubExpanded,
  agentGroups,
  activeAgentId,
  openTabs,
  openTab,
  handleDeleteAgent,
  handleExportAgent,
  handleImportAgent,
  addBtnRef,
  setShowAgentMenu,
  setTooltip,
}) {
  return (
    <div className="sidebar-section">
      <div className="sidebar-section-header" onClick={() => setAgentsExpanded(!agentsExpanded)} style={{ padding: '10px var(--space-3)' }}>
        <div className="sidebar-section-title" style={{ fontSize: 15, fontWeight: 600, textTransform: 'none', letterSpacing: 0 }}>
          <ChevronRight size={15} className={`sidebar-section-chevron ${agentsExpanded ? 'open' : ''}`} />
          <Bot size={17} />
          <span>智能体</span>
        </div>
        <button
          ref={addBtnRef}
          className="sidebar-section-add"
          onClick={(e) => {
            e.stopPropagation()
            setShowAgentMenu(prev => !prev)
          }}
          title="新建Agent"
          onMouseEnter={(e) => {
            const rect = e.currentTarget.getBoundingClientRect()
            setTooltip({ text: '新建Agent', x: rect.left + rect.width / 2, y: rect.top - 8 })
          }}
          onMouseLeave={() => setTooltip(null)}
        >
          <Plus size={14} />
        </button>
      </div>

      {agentsExpanded && (
        <div style={{ paddingBottom: 'var(--space-1)' }}>
          {[
            { key: 'self', label: '自建 Agent', icon: Bot, items: agentGroups.self },
            { key: 'external', label: '外部 Agent', icon: Globe, items: agentGroups.external },
            { key: 'local', label: '本地 Agent', icon: Cpu, items: agentGroups.local },
          ].filter((g) => g.items.length > 0).map((group) => {
            const GroupIcon = group.icon
            const isOpen = subExpanded[group.key]
            return (
              <div key={group.key}>
                <div
                  className="sidebar-section-header"
                  onClick={() => setSubExpanded((prev) => ({ ...prev, [group.key]: !prev[group.key] }))}
                  style={{ padding: '8px var(--space-3) 8px var(--space-4)' }}
                >
                  <div className="sidebar-section-title" style={{ fontSize: 14, fontWeight: 500 }}>
                    <ChevronRight size={14} className={`sidebar-section-chevron ${isOpen ? 'open' : ''}`} />
                    <GroupIcon size={15} />
                    <span style={{ textTransform: 'none', letterSpacing: 0 }}>{group.label}</span>
                    <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 3 }}>({group.items.length})</span>
                  </div>
                </div>
                {isOpen && (
                  <div style={{ maxHeight: 185, overflowY: 'auto', scrollbarWidth: 'thin' }}>
                    {group.items.map((agent) => {
                      const isActive = activeAgentId === agent.agent_id
                      const isAgentRunning = openTabs.some((t) => t.agentId === agent.agent_id)
                      return (
                        <div
                          key={agent.agent_id}
                          className={`conversation-item ${isActive ? 'active' : ''}`}
                          style={{ paddingLeft: 'var(--space-6)' }}
                          onClick={() => {
                            const agentConvs = useChatStore.getState().conversations
                              .filter((c) => c.agentId === agent.agent_id && !c.archived)
                              .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
                            if (agentConvs.length > 0) {
                              const latest = agentConvs[0]
                              const existingTab = openTabs.find((t) => t.convId === latest.id)
                              if (existingTab) {
                                useTabStore.getState().setActiveTab(existingTab.id)
                              } else {
                                openTab(latest.id, latest.name, agent.agent_id)
                              }
                            } else {
                              const convId = `conv_${agent.agent_id}_${Date.now()}`
                              const convName = '新对话1'
                              useChatStore.getState().addConversation({
                                id: convId, type: 'single', agentId: agent.agent_id,
                                name: convName, avatar: null, messages: [],
                                pinned: false, unread: false, updatedAt: Date.now(),
                              })
                              fetch('/api/conversations', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ id: convId, type: 'single', name: convName, agent_id: agent.agent_id }),
                              }).catch(() => {})
                              openTab(convId, convName, agent.agent_id)
                            }
                          }}
                        >
                          <div className="conv-avatar" style={{ width: 32, height: 32 }}>
                            {agent.avatar ? (
                              agent.avatar.startsWith('/') || agent.avatar.startsWith('http') ? (
                                <img src={agent.avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: 'var(--radius-md)' }} />
                              ) : (
                                <span style={{ fontSize: 18 }}>{agent.avatar}</span>
                              )
                            ) : (
                              <IconAvatar agentId={agent.agent_id} size={18} />
                            )}
                          </div>
                          <div className="conv-info">
                            <div className="conv-name">{agent.name}</div>
                            <div className="conv-status conv-status-idle">{agent.role}</div>
                          </div>
                          <span className="online-dot" style={{ background: isAgentRunning ? 'var(--green)' : 'var(--red, #ef4444)' }} title={isAgentRunning ? '运行中' : '已停止'} />
                          {agent.agent_id.startsWith('agent_custom_') ? (
                            <>
                              <button
                                className="agent-row-delete"
                                onClick={(e) => handleExportAgent && handleExportAgent(e, agent)}
                                title="导出"
                                style={{ marginRight: 4 }}
                              >
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                              </button>
                              <button
                                className="agent-row-delete"
                                onClick={(e) => handleDeleteAgent(e, agent.agent_id)}
                                title="删除"
                              >
                                <Trash2 size={14} />
                              </button>
                            </>
                          ) : (
                            <span className="agent-row-lock" title="默认agent不允许删除">
                              <Lock size={14} />
                            </span>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
