import React, { useState } from 'react'
import { useChatStore } from '../../stores/chatStore'
import SettingsPanel from './SettingsPanel'

export default function Sidebar() {
  const conversations = useChatStore((s) => s.conversations)
  const activeId = useChatStore((s) => s.activeConversationId)
  const setActive = useChatStore((s) => s.setActiveConversation)
  const [showSettings, setShowSettings] = useState(false)

  const singles = conversations.filter((c) => c.type === 'single')
  const groups = conversations.filter((c) => c.type === 'group')

  return (
    <>
      <div className="sidebar">
        <div className="sidebar-header">
          <div className="logo">AgentHub</div>
        </div>

        <div className="sidebar-section-title">单聊</div>
        <div className="conversation-list">
          {singles.map((conv) => (
            <div
              key={conv.id}
              className={`conversation-item ${activeId === conv.id ? 'active' : ''}`}
              onClick={() => setActive(conv.id)}
            >
              <div className="avatar">{conv.avatar}</div>
              <div className="info">
                <div className="name">{conv.name}</div>
                <div className="preview">{conv.preview}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="sidebar-section-title">群聊</div>
        <div className="conversation-list">
          {groups.map((conv) => (
            <div
              key={conv.id}
              className={`conversation-item ${activeId === conv.id ? 'active' : ''}`}
              onClick={() => setActive(conv.id)}
            >
              <div className="avatar">{conv.avatar}</div>
              <div className="info">
                <div className="name">{conv.name}</div>
                <div className="preview">{conv.preview}</div>
              </div>
            </div>
          ))}
        </div>

        <div style={{ flex: 1 }} />
        <div
          className="conversation-item"
          onClick={() => setShowSettings(true)}
          style={{ marginTop: 'auto', borderTop: '1px solid rgba(255,255,255,0.06)' }}
        >
          <div className="avatar">⚙️</div>
          <div className="info">
            <div className="name">LLM 设置</div>
            <div className="preview">配置 API 接口</div>
          </div>
        </div>
      </div>

      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} />}
    </>
  )
}
