import React, { useState, useMemo, useCallback } from 'react'
import { Plus, Search, Settings, Pin, MoreHorizontal, X } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import SettingsPanel from './SettingsPanel'
import IconAvatar from '../IconAvatar'
import AgentSelector from '../Chat/AgentSelector'

export default function Sidebar() {
  const conversations = useChatStore((s) => s.conversations)
  const activeId = useChatStore((s) => s.activeConversationId)
  const setActive = useChatStore((s) => s.setActiveConversation)
  const togglePin = useChatStore((s) => s.togglePin)
  const archiveConversation = useChatStore((s) => s.archiveConversation)
  const reorderConversations = useChatStore((s) => s.reorderConversations)

  const [showSettings, setShowSettings] = useState(false)
  const [showNewDialog, setShowNewDialog] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [contextMenu, setContextMenu] = useState(null)
  const [dragIndex, setDragIndex] = useState(null)

  // Sort: pinned first, then by updatedAt desc. Filter archived.
  const sorted = useMemo(() => {
    const active = conversations.filter((c) => !c.archived)
    const filtered = searchQuery
      ? active.filter((c) => c.name.toLowerCase().includes(searchQuery.toLowerCase()))
      : active
    return [...filtered].sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
      return (b.updatedAt || 0) - (a.updatedAt || 0)
    })
  }, [conversations, searchQuery])

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
      <div className="sidebar">
        <div className="sidebar-header">
          <span className="sidebar-logo">AgentHub</span>
          <button className="sidebar-new-btn" onClick={() => setShowNewDialog(true)} title="新建对话">
            <Plus size={18} />
          </button>
        </div>

        <div className="sidebar-search">
          <input
            type="text"
            placeholder="搜索会话..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="conversation-list">
          {sorted.map((conv, i) => (
            <div
              key={conv.id}
              className={`conversation-item ${activeId === conv.id ? 'active' : ''}`}
              onClick={() => setActive(conv.id)}
              onContextMenu={(e) => handleContextMenu(e, conv.id)}
              draggable
              onDragStart={(e) => handleDragStart(e, i)}
              onDragOver={handleDragOver}
              onDrop={(e) => handleDrop(e, i)}
            >
              {conv.pinned && (
                <span className="pin-indicator"><Pin size={10} /></span>
              )}
              <div className="conv-avatar">
                <IconAvatar
                  agentId={conv.type === 'single' ? conv.agentId : undefined}
                  iconKey={conv.type === 'group' ? 'group' : undefined}
                  size={20}
                />
              </div>
              <div className="conv-info">
                <div className={`conv-name ${conv.unread ? 'unread' : ''}`}>{conv.name}</div>
              </div>
              <span className="conv-time">{formatTime(conv.updatedAt)}</span>
              {conv.unread && <span className="unread-dot" />}
              <button
                className="conv-menu-btn"
                onClick={(e) => { e.stopPropagation(); handleContextMenu(e, conv.id) }}
              >
                <MoreHorizontal size={14} />
              </button>
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-footer-item" onClick={() => setShowSettings(true)}>
            <Settings size={16} />
            <span>设置</span>
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
            setActive(convId)
          }}
          onClose={() => setShowNewDialog(false)}
        />
      )}

      {/* Settings */}
      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} />}
    </>
  )
}
