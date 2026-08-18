import React, { useState, useRef, useEffect, memo } from 'react'
import { Code2, GitBranch, LayoutList, Menu, Search, PanelRightClose, MoreHorizontal, Share2, Building2, Wrench, BookOpen } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { useCanvasStore } from '../../stores/canvasStore'
import IconAvatar from '../IconAvatar'
import ReadinessControl from '../ReadinessControl'

const ChatPanelHeader = memo(function ChatPanelHeader({ convId, onToggleSidebar, onToggleTask, onToggleDag, taskOpen, dagOpen, onToggleOffice, onClearHistory, readiness }) {
  const conv = useChatStore((s) => s.conversations.find((c) => c.id === convId))
  const agents = useAgentStore((s) => s.agents)
  const typingAgents = useChatStore((s) => s.typingAgents)

  const slidePanelOpen = useCanvasStore((s) => s.slidePanelOpen)
  const slidePanelContent = useCanvasStore((s) => s.slidePanelContent)
  const toggleSlidePanel = useCanvasStore((s) => s.toggleSlidePanel)

  const [moreOpen, setMoreOpen] = useState(false)
  const moreRef = useRef(null)

  // 点击外部关闭菜单
  useEffect(() => {
    if (!moreOpen) return
    const handleClickOutside = (e) => {
      if (moreRef.current && !moreRef.current.contains(e.target)) {
        setMoreOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [moreOpen])

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
        <ReadinessControl readiness={readiness} />
        {onToggleOffice && (
          <button
            className="header-icon-btn header-desktop-action"
            onClick={onToggleOffice}
            title="虚拟办公室"
            aria-label="虚拟办公室"
          >
            <Building2 size={20} />
            <span className="icon-tooltip">虚拟办公室</span>
          </button>
        )}
        <button
          className="header-icon-btn header-desktop-action"
          onClick={() => toggleSlidePanel('tools')}
          aria-label="工具"
          style={slidePanelOpen && slidePanelContent === 'tools' ? { color: 'var(--accent)' } : undefined}
        >
          <Wrench size={20} />
          <span className="icon-tooltip">工具</span>
        </button>
        <button
          className="header-icon-btn header-desktop-action"
          onClick={() => toggleSlidePanel('knowledge')}
          aria-label="知识库"
          style={slidePanelOpen && slidePanelContent === 'knowledge' ? { color: 'var(--accent)' } : undefined}
        >
          <BookOpen size={20} />
          <span className="icon-tooltip">知识库</span>
        </button>
        <button
          className="header-icon-btn header-desktop-action"
          onClick={() => toggleSlidePanel('code')}
          aria-label={slidePanelOpen && slidePanelContent === 'code' ? '收起产物面板' : '打开产物面板'}
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
        <div className="header-icon-btn-wrapper header-more-action" ref={moreRef}>
          <button
            className="header-icon-btn"
            onClick={() => setMoreOpen(!moreOpen)}
            style={moreOpen ? { color: 'var(--accent)' } : undefined}
            aria-label="更多操作"
            title="更多操作"
          >
            <MoreHorizontal size={20} />
          </button>
          {moreOpen && (
            <div className="header-popup more-popup">
              <button className="header-popup-item" onClick={() => { toggleSlidePanel('tools'); setMoreOpen(false) }}>
                <Wrench size={16} />
                <span>工具</span>
              </button>
              <button className="header-popup-item" onClick={() => { toggleSlidePanel('knowledge'); setMoreOpen(false) }}>
                <BookOpen size={16} />
                <span>知识库</span>
              </button>
              <button className="header-popup-item" onClick={() => { toggleSlidePanel('code'); setMoreOpen(false) }}>
                <Code2 size={16} />
                <span>产物面板</span>
              </button>
              {onToggleOffice && (
                <button className="header-popup-item" onClick={() => { onToggleOffice(); setMoreOpen(false) }}>
                  <Building2 size={16} />
                  <span>虚拟办公室</span>
                </button>
              )}
              <div style={{ height: 1, background: 'var(--border)', margin: '4px 0' }} />
              <button
                className="header-popup-item"
                style={taskOpen ? { color: 'var(--accent)' } : undefined}
                onClick={() => { onToggleTask(); setMoreOpen(false) }}
              >
                <LayoutList size={16} />
                <span>任务看板</span>
              </button>
              <button
                className="header-popup-item"
                style={dagOpen ? { color: 'var(--accent)' } : undefined}
                onClick={() => { onToggleDag(); setMoreOpen(false) }}
              >
                <GitBranch size={16} />
                <span>协作图</span>
              </button>
              <div style={{ height: 1, background: 'var(--border)', margin: '4px 0' }} />
              <button className="header-popup-item" onClick={() => setMoreOpen(false)}>
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
