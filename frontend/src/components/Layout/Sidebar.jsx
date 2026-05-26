import React, { useState } from 'react'
import { useChatStore } from '../../stores/chatStore'
import SettingsPanel from './SettingsPanel'
import AgentBuilderModal from './AgentBuilderModal'

export default function Sidebar() {
  const conversations = useChatStore((s) => s.conversations)
  const activeId = useChatStore((s) => s.activeConversationId)
  const setActive = useChatStore((s) => s.setActiveConversation)
  
  const [showSettings, setShowSettings] = useState(false)
  const [showBuilderModal, setShowBuilderModal] = useState(false)
  const [editingAgentId, setEditingAgentId] = useState(null)

  // Built-in agents (exclude builder)
  const builtinIds = ['agent_pm', 'agent_frontend', 'agent_backend', 'agent_tester', 'agent_devops', 'agent_designer']
  const builtins = conversations.filter((c) => c.type === 'single' && builtinIds.includes(c.agentId))
  // Custom agents (user-created)
  const customs = conversations.filter((c) => c.type === 'single' && c.agentId && c.agentId.startsWith('agent_custom_'))
  // Builder
  const builder = conversations.find((c) => c.agentId === 'agent_builder')
  const groups = conversations.filter((c) => c.type === 'group')

  // Deletion logic
  const deleteAgent = async (agentId, e) => {
    e.stopPropagation()
    if (!window.confirm('您确定要永久删除这个自定义智能体吗？')) return
    
    try {
      const resp = await fetch(`/api/agents/custom/${agentId}`, { method: 'DELETE' })
      if (resp.ok) {
        const removeConversation = useChatStore.getState().removeConversation
        removeConversation(`conv_${agentId}`)
      }
    } catch (err) {
      console.error('Failed to delete custom agent:', err)
    }
  }

  const ConvItem = ({ conv }) => (
    <div
      className={`conversation-item ${activeId === conv.id ? 'active' : ''}`}
      onClick={() => setActive(conv.id)}
    >
      <div className="avatar">{conv.avatar}</div>
      <div className="info">
        <div className="name">{conv.name}</div>
        <div className="preview">{conv.preview}</div>
      </div>
    </div>
  )

  const CustomConvItem = ({ conv }) => (
    <div
      className={`conversation-item custom-agent-item ${activeId === conv.id ? 'active' : ''}`}
      onClick={() => setActive(conv.id)}
    >
      <div className="avatar">{conv.avatar}</div>
      <div className="info">
        <div className="name">{conv.name}</div>
        <div className="preview">{conv.preview}</div>
      </div>
      <div className="custom-agent-actions">
        <button
          className="custom-agent-action-btn edit"
          title="配置/编辑人物设定"
          onClick={(e) => {
            e.stopPropagation()
            setEditingAgentId(conv.agentId)
            setShowBuilderModal(true)
          }}
        >
          ⚙️
        </button>
        <button
          className="custom-agent-action-btn delete"
          title="删除智能体"
          onClick={(e) => deleteAgent(conv.agentId, e)}
        >
          🗑️
        </button>
      </div>
    </div>
  )

  return (
    <>
      <div className="sidebar">
        <div className="sidebar-header">
          <div className="logo">AgentHub</div>
        </div>

        <div className="sidebar-section-title">内置 Agent</div>
        <div className="conversation-list">
          {builtins.map((conv) => <ConvItem key={conv.id} conv={conv} />)}
        </div>

        {/* Custom Agents Section */}
        <div className="sidebar-section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>我的 Agent</span>
          <button
            className="sidebar-add-btn"
            title="可视化创建新智能体 (Coze风格)"
            onClick={() => {
              setEditingAgentId(null)
              setShowBuilderModal(true)
            }}
          >
            ＋
          </button>
        </div>
        <div className="conversation-list">
          {customs.length === 0 && (
            <div style={{ padding: '8px 16px', fontSize: 12, color: '#475569' }}>
              还没有自建 Agent
            </div>
          )}
          {customs.map((conv) => <CustomConvItem key={conv.id} conv={conv} />)}

          {/* Create Agent Button → opens Agent Builder */}
          {builder && (
            <div
              className={`conversation-item ${activeId === builder.id ? 'active' : ''}`}
              onClick={() => setActive(builder.id)}
              style={{ borderTop: '1px solid rgba(255,255,255,0.04)', marginTop: 4 }}
            >
              <div className="avatar" style={{ background: 'rgba(99,102,241,0.15)', borderRadius: 8, width: 32, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16 }}>💬</div>
              <div className="info">
                <div className="name" style={{ color: '#a5b4fc' }}>Agent 工坊</div>
                <div className="preview">对话式创建自定义 Agent</div>
              </div>
            </div>
          )}
        </div>

        <div className="sidebar-section-title">群聊</div>
        <div className="conversation-list">
          {groups.map((conv) => <ConvItem key={conv.id} conv={conv} />)}
        </div>

        <div style={{ flex: 1 }} />
        <div
          className="conversation-item"
          onClick={() => setShowSettings(true)}
          style={{ marginTop: 'auto', borderTop: '1px solid rgba(255,255,255,0.06)' }}
        >
          <div className="avatar">⚙️</div>
          <div className="info">
            <div className="name">设置</div>
            <div className="preview">LLM · 质量门 · Prompt</div>
          </div>
        </div>
      </div>

      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} />}
      
      {showBuilderModal && (
        <AgentBuilderModal
          editingAgentId={editingAgentId}
          onClose={() => {
            setShowBuilderModal(false)
            setEditingAgentId(null)
          }}
        />
      )}
    </>
  )
}
