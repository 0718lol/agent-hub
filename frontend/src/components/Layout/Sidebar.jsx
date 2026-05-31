import React, { useState, useMemo, useCallback } from 'react'
import { Plus, Settings, Pin, MoreHorizontal, X, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { useTabStore } from '../../stores/tabStore'
import SettingsPanel from './SettingsPanel'
import IconAvatar from '../IconAvatar'
import AgentSelector from '../Chat/AgentSelector'

export default function Sidebar({ mobileOpen = false, onClose = () => {} }) {
  const conversations = useChatStore((s) => s.conversations)
  const setActive = useChatStore((s) => s.setActiveConversation)
  const togglePin = useChatStore((s) => s.togglePin)
  const archiveConversation = useChatStore((s) => s.archiveConversation)
  const reorderConversations = useChatStore((s) => s.reorderConversations)
  const typingAgents = useChatStore((s) => s.typingAgents)

  const openTab = useTabStore((s) => s.openTab)
  const activeTabId = useTabStore((s) => s.activeTabId)
  const openTabs = useTabStore((s) => s.openTabs)
  const activeTab = openTabs.find((t) => t.id === activeTabId)
  const activeId = activeTab?.convId || 'conv_pm'

  const [collapsed, setCollapsed] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [showNewDialog, setShowNewDialog] = useState(false)
  const [contextMenu, setContextMenu] = useState(null)
  const [dragIndex, setDragIndex] = useState(null)

  // 所有已打开标签的 convId 集合
  const openConvIds = useMemo(() => new Set(openTabs.map((t) => t.convId)), [openTabs])

  // Sort: opened tabs first, then pinned, then by updatedAt desc. Filter archived.
  const sorted = useMemo(() => {
    return conversations
      .filter((c) => !c.archived)
      .sort((a, b) => {
        const aOpen = openConvIds.has(a.id)
        const bOpen = openConvIds.has(b.id)
        if (aOpen !== bOpen) return aOpen ? -1 : 1
        if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
        return (b.updatedAt || 0) - (a.updatedAt || 0)
      })
  }, [conversations, openConvIds])

  const handleContextMenu = useCallback((e, convId) => {
    e.preventDefault()
    setContextMenu({ convId, x: e.clientX, y: e.clientY })
  }, [])

  const closeContextMenu = () => setContextMenu(null)

  const formatTime = (ts) => {
    if (!ts) return ''
    const d = new Date(ts)
    const now = new Date()
    const isToday = d.toDateString() === now.toDateString()
    if (isToday) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  }

  // HTML5 Drag
  const handleDragStart = useCallback((e, index) => {
    setDragIndex(index)
    e.dataTransfer.effectAllowed = 'move'
  }, [])

  const handleDragOver = useCallback((e) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const handleDrop = useCallback((e, dropIndex) => {
    e.preventDefault()
    if (dragIndex !== null && dragIndex !== dropIndex) {
      reorderConversations(dragIndex, dropIndex)
    }
    setDragIndex(null)
  }, [dragIndex, reorderConversations])

  return (
    <>
      <div className={`sidebar ${mobileOpen ? 'mobile-open' : ''} ${collapsed ? 'collapsed' : ''}`}>
        {/* Header */}
        <div className="sidebar-header">
          {!collapsed && <span className="sidebar-logo">AgentHub</span>}
          <button
            className="sidebar-collapse-btn"
            onClick={() => setCollapsed(!collapsed)}
            title={collapsed ? '展开侧边栏' : '收起侧边栏'}
          >
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
          {!collapsed && (
            <button className="hamburger-btn" onClick={onClose} title="关闭菜单">
              <X size={18} />
            </button>
          )}
        </div>

        {/* Conversation List */}
        <div className="conversation-list">
          {sorted.map((conv, i) => (
            <div
              key={conv.id}
              className={`conversation-item ${openConvIds.has(conv.id) ? 'active' : ''}`}
              onClick={() => { openTab(conv.id, conv.name, conv.agentId) }}
              onContextMenu={(e) => handleContextMenu(e, conv.id)}
              draggable={!collapsed}
              onDragStart={(e) => handleDragStart(e, i)}
              onDragOver={handleDragOver}
              onDrop={(e) => handleDrop(e, i)}
              title={collapsed ? conv.name : undefined}
            >
              {conv.pinned && <span className="pin-indicator"><Pin size={10} /></span>}
              <div className="conv-avatar">
                <IconAvatar
                  agentId={conv.type === 'single' ? conv.agentId : undefined}
                  iconKey={conv.type === 'group' ? 'group' : undefined}
                  size={20}
                />
              </div>
              {!collapsed && (
                <>
                  <div className="conv-info">
                    <div className={`conv-name ${conv.unread ? 'unread' : ''}`}>{conv.name}</div>
                    {activeId === conv.id && (
                      <div className="conv-status">
                        {(typingAgents[conv.id]?.size > 0) ? (
                          <span className="conv-status-typing">
                            正在输入
                            <span className="typing-dots">
                              <span /><span /><span />
                            </span>
                          </span>
                        ) : (
                          <span className="conv-status-idle">空闲中</span>
                        )}
                      </div>
                    )}
                  </div>
                  <span className="conv-time">{formatTime(conv.updatedAt)}</span>
                  {conv.unread && <span className="unread-dot" />}
                  <button
                    className="conv-menu-btn"
                    onClick={(e) => { e.stopPropagation(); handleContextMenu(e, conv.id) }}
                  >
                    <MoreHorizontal size={14} />
                  </button>
                </>
              )}
            </div>
          ))}
        </div>

        {/* 新建 Agent */}
        <div
          className="conversation-item sidebar-new-conv"
          onClick={() => setShowNewDialog(true)}
          title={collapsed ? '新建 Agent' : undefined}
        >
          <div className="conv-avatar" style={{ background: 'var(--accent-bg)', color: 'var(--accent)' }}>
            <Plus size={18} />
          </div>
          {!collapsed && (
            <div className="conv-info">
              <div className="conv-name" style={{ color: 'var(--accent)' }}>新建 Agent</div>
            </div>
          )}
        </div>

        {/* Settings */}
        <div className="sidebar-footer">
          <div
            className="sidebar-footer-item"
            onClick={() => setShowSettings(true)}
            title={collapsed ? '设置' : undefined}
          >
            <Settings size={16} />
            {!collapsed && <span>设置</span>}
          </div>
        </div>
      </div>

      {/* Context Menu */}
      {contextMenu && (
        <>
          <div style={{ position: 'fixed', inset: 0, zIndex: 999 }} onClick={closeContextMenu} />
          <div className="context-menu" style={{ left: contextMenu.x, top: contextMenu.y }}>
            <button className="context-menu-item" onClick={() => {
              togglePin(contextMenu.convId)
              closeContextMenu()
            }}>
              <Pin size={14} />
              {conversations.find((c) => c.id === contextMenu.convId)?.pinned ? '取消置顶' : '置顶'}
            </button>
            <button className="context-menu-item danger" onClick={() => {
              archiveConversation(contextMenu.convId)
              closeContextMenu()
            }}>
              <X size={14} />
              归档
            </button>
          </div>
        </>
      )}

      {/* New Conversation Dialog */}
      {showNewDialog && (
        <AgentSelector
          onSelect={(agentId) => {
            setShowNewDialog(false)
            const convId = `conv_${agentId}_${Date.now()}`
            const agent = useAgentStore.getState().agents.find((a) => a.agent_id === agentId)
            useChatStore.getState().addConversation({
              id: convId,
              type: 'single',
              agentId,
              name: agent?.name || '新对话',
              avatar: null,
              messages: [],
              pinned: false,
              unread: false,
              updatedAt: Date.now(),
            })
            openTab(convId, agent?.name || '新对话', agentId)
          }}
          onClose={() => setShowNewDialog(false)}
        />
      )}

      {/* Settings */}
      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} />}
    </>
  )
}
