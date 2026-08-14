import React from 'react'
import { Plus, Search, Pin, MoreHorizontal } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { useTabStore } from '../../stores/tabStore'
import IconAvatar from '../IconAvatar'

export default function SidebarHistorySection({
  searchQuery,
  setSearchQuery,
  historyConversations,
  openTabs,
  openTab,
  handleContextMenu,
  handleDragStart,
  handleDragOver,
  handleDrop,
  formatTime,
  activeAgentId,
  convCounterRef,
}) {
  return (
    <>
      {/* ===== 新对话 + 搜索 + 历史对话 ===== */}
      <div className="sidebar-new-conv-wrap">
        <div className="sidebar-new-conv-btn" onClick={async () => {
          if (!activeAgentId) return
          const convId = `conv_${activeAgentId}_${Date.now()}`
          const defaultName = `新对话${convCounterRef.current}`
          convCounterRef.current += 1
          try {
            await useChatStore.getState().addConversation({
              id: convId, type: 'single', agentId: activeAgentId,
              name: defaultName, avatar: null,
              messages: [], pinned: false, unread: false, updatedAt: Date.now(),
            })
            openTab(convId, defaultName, activeAgentId)
          } catch (error) {
            useChatStore.getState().removeConversation(convId)
            console.error('Failed to create conversation:', error)
          }
        }}>
          <Plus size={16} />
          <span>新对话</span>
        </div>
      </div>

      <div className="sidebar-search-wrap" style={{ position: 'relative' }}>
        <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
        <input
          type="text"
          placeholder="搜索对话..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{ paddingLeft: 30 }}
        />
      </div>

      <div className="sidebar-history-label" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span>历史对话</span>
        {historyConversations.length > 0 && (
          <button
            onClick={() => {
              if (!window.confirm(`确定删除当前 Agent 下的 ${historyConversations.length} 条对话？`)) return
              const { closeTab } = useTabStore.getState()
              for (const conv of historyConversations) {
                // 关闭对应标签
                const tab = openTabs.find((t) => t.convId === conv.id)
                if (tab) closeTab(tab.id)
                // 归档对话
                useChatStore.getState().archiveConversation(conv.id)
              }
            }}
            style={{
              background: 'none', border: 'none', color: 'var(--text-muted)',
              fontSize: 'var(--text-xs)', cursor: 'pointer', padding: '2px 4px',
            }}
            title="清空当前 Agent 的所有历史对话"
          >
            清空
          </button>
        )}
      </div>

      <div className="sidebar-history-list">
        {historyConversations.length === 0 && !searchQuery.trim() ? null : historyConversations.length === 0 ? (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 'var(--text-xs)', padding: 'var(--space-3)' }}>
            无匹配对话
          </div>
        ) : (
          historyConversations.map((conv) => {
            const openConvIds = new Set(openTabs.map((t) => t.convId))
            return (
              <div
                key={conv.id}
                className={`conversation-item ${openConvIds.has(conv.id) ? 'active' : ''}`}
                style={{ paddingLeft: 'var(--space-5)' }}
                onClick={() => {
                  const existingTab = openTabs.find((t) => t.convId === conv.id)
                  if (existingTab) {
                    // 标签页已存在 → 直接切换到该标签
                    useTabStore.getState().setActiveTab(existingTab.id)
                  } else {
                    // 标签页不存在 → 新建标签并打开该对话
                    openTab(conv.id, conv.name, conv.agentId)
                  }
                }}
                onContextMenu={(e) => handleContextMenu(e, conv.id)}
                draggable
                onDragStart={(e) => handleDragStart(e, conv.id)}
                onDragOver={handleDragOver}
                onDrop={(e) => handleDrop(e, conv.id)}
              >
                {conv.pinned && <span className="pin-indicator"><Pin size={10} /></span>}
                <div className="conv-avatar" style={{ width: 32, height: 32 }}>
                  <IconAvatar
                    agentId={conv.type === 'single' ? conv.agentId : undefined}
                    iconKey={conv.type === 'group' ? 'group' : undefined}
                    size={18}
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
            )
          })
        )}
      </div>
    </>
  )
}
