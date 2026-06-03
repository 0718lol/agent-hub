import React, { useState, useRef, useEffect, useCallback, memo } from 'react'
import { X, Lock, Plus } from 'lucide-react'
import { useTabStore } from '../../stores/tabStore'
import { useChatStore } from '../../stores/chatStore'
import IconAvatar from '../IconAvatar'

const PM_CONV_ID = 'conv_pm'

const TabItem = memo(function TabItem({ tab, conv, isActive, onActivate, onClose, isPm }) {
  const [hover, setHover] = useState(false)
  return (
    <div
      className={`tab-item ${isActive ? 'active' : ''}`}
      onClick={onActivate}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <div style={{ width: 14, height: 14, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', borderRadius: 3 }}>
        <IconAvatar
          agentId={tab.agentId || conv?.agentId}
          iconKey={conv?.type === 'group' ? 'group' : undefined}
          size={14}
        />
      </div>
      <span className="tab-item-title">{tab.title}</span>
      {isPm ? (
        <Lock size={10} className="tab-lock" title="默认对话，不可关闭" />
      ) : (
        <button
          className={`tab-close ${hover || isActive ? 'visible' : ''}`}
          onClick={(e) => { e.stopPropagation(); onClose() }}
          title="关闭标签"
        >
          <X size={12} />
        </button>
      )}
    </div>
  )
})

export default function TabBar() {
  const openTabs = useTabStore((s) => s.openTabs)
  const activeTabId = useTabStore((s) => s.activeTabId)
  const setActiveTab = useTabStore((s) => s.setActiveTab)
  const closeTab = useTabStore((s) => s.closeTab)
  const conversations = useChatStore((s) => s.conversations)

  const scrollRef = useRef(null)

  // Auto-scroll active tab into view
  useEffect(() => {
    if (!scrollRef.current) return
    const activeEl = scrollRef.current.querySelector('.tab-item.active')
    if (activeEl) {
      activeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
    }
  }, [activeTabId])

  const handleNewTab = () => {
    const activeTab = openTabs.find((t) => t.id === activeTabId)
    const agentId = activeTab?.agentId || 'agent_pm'
    const convId = `conv_${agentId}_${Date.now()}`
    // 生成不重复的 "新对话N" 名称
    const agentConvs = useChatStore.getState().conversations.filter(
      (c) => c.agentId === agentId && !c.archived
    )
    const usedNames = new Set(agentConvs.map((c) => c.name))
    let n = agentConvs.length + 1
    let name = `新对话${n}`
    while (usedNames.has(name)) {
      n++
      name = `新对话${n}`
    }
    useChatStore.getState().addConversation({
      id: convId, type: 'single', agentId,
      name, avatar: null,
      messages: [], pinned: false, unread: false, updatedAt: Date.now(),
    })
    // 同步到后端
    fetch('/api/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: convId, type: 'single', name, agent_id: agentId }),
    }).catch(() => {})
    useTabStore.getState().openTab(convId, name, agentId)
  }

  return (
    <div className="tab-bar">
      <div className="tab-bar-scroll" ref={scrollRef}>
        {openTabs.map((tab) => {
          const conv = conversations.find((c) => c.id === tab.convId)
          const isPm = tab.convId === PM_CONV_ID
          return (
            <TabItem
              key={tab.id}
              tab={tab}
              conv={conv}
              isActive={tab.id === activeTabId}
              isPm={isPm}
              onActivate={() => setActiveTab(tab.id)}
              onClose={() => closeTab(tab.id)}
            />
          )
        })}
      </div>
      <button className="tab-new-btn" onClick={handleNewTab} title="新建对话">
        <Plus size={16} />
      </button>
    </div>
  )
}
