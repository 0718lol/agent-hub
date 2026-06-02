import React, { useState, useCallback, memo } from 'react'
import { X } from 'lucide-react'
import { useTabStore } from '../../stores/tabStore'
import { useChatStore } from '../../stores/chatStore'
import IconAvatar from '../IconAvatar'

const TabItem = memo(function TabItem({ tab, conv, isActive, isDragging, onActivate, onClose, onDragStart, onDragOver, onDrop }) {
  return (
    <div
      className={`tab-item ${isActive ? 'active' : ''} ${isDragging ? 'dragging' : ''}`}
      onClick={onActivate}
      draggable
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      <IconAvatar
        agentId={tab.agentId || conv?.agentId}
        iconKey={conv?.type === 'group' ? 'group' : undefined}
        size={14}
      />
      <span className="tab-item-title">{tab.title}</span>
      {conv?.unread && <span className="unread-tab-dot" />}
      <button
        className="tab-close"
        onClick={onClose}
        title="关闭标签"
      >
        <X size={12} />
      </button>
    </div>
  )
})

export default function TabBar() {
  const openTabs = useTabStore((s) => s.openTabs)
  const activeTabId = useTabStore((s) => s.activeTabId)
  const setActiveTab = useTabStore((s) => s.setActiveTab)
  const closeTab = useTabStore((s) => s.closeTab)
  const reorderTabs = useTabStore((s) => s.reorderTabs)
  const conversations = useChatStore((s) => s.conversations)

  const [dragIndex, setDragIndex] = useState(null)

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
      reorderTabs(dragIndex, dropIndex)
    }
    setDragIndex(null)
  }, [dragIndex, reorderTabs])

  if (openTabs.length <= 1) return null

  return (
    <div className="tab-bar">
      {openTabs.map((tab, i) => {
        const conv = conversations.find((c) => c.id === tab.convId)
        return (
          <TabItem
            key={tab.id}
            tab={tab}
            conv={conv}
            isActive={tab.id === activeTabId}
            isDragging={dragIndex === i}
            onActivate={() => setActiveTab(tab.id)}
            onClose={(e) => { e.stopPropagation(); closeTab(tab.id) }}
            onDragStart={(e) => handleDragStart(e, i)}
            onDragOver={handleDragOver}
            onDrop={(e) => handleDrop(e, i)}
          />
        )
      })}
    </div>
  )
}
