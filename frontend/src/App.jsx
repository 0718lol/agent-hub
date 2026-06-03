import React, { useState, useEffect } from 'react'
import Sidebar from './components/Layout/Sidebar'
import ChatPanel from './components/Layout/ChatPanel'
import SlidePanel from './components/Layout/SlidePanel'
import { useChatStore } from './stores/chatStore'
import { useAgentStore } from './stores/agentStore'
import { useCanvasStore } from './stores/canvasStore'
import { useTabStore } from './stores/tabStore'

export default function App() {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

  // Fetch data from backend on first mount
  useEffect(() => {
    useChatStore.getState().fetchConversations().then(() => {
      // 对话加载完成后，清理指向不存在对话的幽灵标签
      const convIds = useChatStore.getState().conversations.map((c) => c.id)
      useTabStore.getState().syncWithConversations(convIds)
    })
    useAgentStore.getState().fetchAgents()
    useCanvasStore.getState().fetchDAGFromBackend()
  }, [])

  return (
    <div className="app-layout">
      {/* 移动端侧边栏遮罩 */}
      <div
        className={`sidebar-overlay ${mobileSidebarOpen ? 'visible' : ''}`}
        onClick={() => setMobileSidebarOpen(false)}
      />
      <Sidebar mobileOpen={mobileSidebarOpen} onClose={() => setMobileSidebarOpen(false)} />
      <ChatPanel onToggleSidebar={() => setMobileSidebarOpen((v) => !v)} />
      <SlidePanel />
    </div>
  )
}
