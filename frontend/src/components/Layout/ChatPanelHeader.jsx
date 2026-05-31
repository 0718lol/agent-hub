import React, { useState, memo } from 'react'
import { Code2, GitBranch, LayoutList, Menu, Search, PanelRightClose, MoreHorizontal, Share2 } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { useCanvasStore } from '../../stores/canvasStore'
import IconAvatar from '../IconAvatar'

const ChatPanelHeader = memo(function ChatPanelHeader({ convId, onToggleSidebar, onToggleTask, onToggleDag, taskOpen, dagOpen }) {
  const conv = useChatStore((s) => s.conversations.find((c) => c.id === convId))
  const agents = useAgentStore((s) => s.agents)
  const typingAgents = useChatStore((s) => s.typingAgents)

  const slidePanelOpen = useCanvasStore((s) => s.slidePanelOpen)
  const slidePanelContent = useCanvasStore((s) => s.slidePanelContent)
  const toggleSlidePanel = useCanvasStore((s) => s.toggleSlidePanel)

  const [moreHover, setMoreHover] = useState(false)

  if (!conv) return null

  const typingSet = typingAgents[convId] || new Set()
  const typingAgentIds = [...typingSet]
  const isGroup = conv.type === 'group'
  const activeTypingAgent = typingAgentIds.length > 0
    ? agents.find((a) => a.agent_id === typingAgentIds[0])
    : null

  return (
    <div className="chat-header">
      <div className="chat-header-left">
        <button className="hamburger-btn" onClick={onToggleSidebar} title="菜单">
          <Menu size={18} />
        </button>
        {isGroup ? (
          <>
            <div className="group-avatar-stack">
              {(conv.agents || []).slice(0, 4).map((agentId) => (
                <div key={agentId} className="mini-avatar">
                  <IconAvatar agentId={agentId} size={10} />
                </div>
              ))}
            </div>
            <div className="chat-header-info">
              <div className="chat-header-name">{conv.name}</div>
              <div className="chat-header-desc">
                {conv.agents?.length || 0} 人
                {activeTypingAgent && (
                  <span style={{ color: 'var(--accent)', marginLeft: 8 }}>
                    · {activeTypingAgent.name} 正在回复...
                  </span>
                )}
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="chat-header-avatar">
              <IconAvatar agentId={conv.agentId} size={20} />
            </div>
            <div className="chat-header-info">
              <div className="chat-header-name">{conv.name}</div>
              <div className="chat-header-desc">
                {agents.find((a) => a.agent_id === conv.agentId)?.role || ''}
              </div>
            </div>
          </>
        )}
      </div>
      <div className="chat-header-spacer" />
      <div className="chat-header-right">
        {typingAgentIds.length > 0 && !activeTypingAgent && (
          <span className="chat-header-badge">{typingAgentIds.length} 人输入中</span>
        )}
        <button
          className="header-icon-btn"
          onClick={() => toggleSlidePanel('search')}
          style={slidePanelOpen && slidePanelContent === 'search' ? { color: 'var(--accent)' } : undefined}
        >
          <Search size={20} />
          <span className="icon-tooltip">搜索对话</span>
        </button>
        <button
          className="header-icon-btn"
          onClick={onToggleTask}
          style={taskOpen ? { color: 'var(--accent)' } : undefined}
        >
          <LayoutList size={20} />
          <span className="icon-tooltip">任务看板</span>
        </button>
        <button
          className="header-icon-btn"
          onClick={onToggleDag}
          style={dagOpen ? { color: 'var(--accent)' } : undefined}
        >
          <GitBranch size={20} />
          <span className="icon-tooltip">协作图</span>
        </button>
        <button
          className="header-icon-btn"
          onClick={() => toggleSlidePanel('code')}
          style={slidePanelOpen && slidePanelContent === 'code' ? { color: 'var(--accent)' } : undefined}
        >
          {slidePanelOpen && slidePanelContent === 'code' ? (
            <PanelRightClose size={20} />
          ) : (
            <Code2 size={20} />
          )}
          <span className="icon-tooltip">
            {slidePanelOpen && slidePanelContent === 'code' ? '收起侧边栏' : '展开侧边栏'}
          </span>
        </button>
        <div
          className="header-icon-btn-wrapper"
          onMouseEnter={() => setMoreHover(true)}
          onMouseLeave={() => setMoreHover(false)}
        >
          <button className="header-icon-btn">
            <MoreHorizontal size={20} />
          </button>
          {moreHover && (
            <div className="header-popup more-popup">
              <button className="header-popup-item" onClick={() => setMoreHover(false)}>
                <Share2 size={16} />
                <span>分享</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
})

export default ChatPanelHeader
