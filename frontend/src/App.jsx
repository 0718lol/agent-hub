import React, { lazy, Suspense, useState, useEffect } from 'react'
import Sidebar from './components/Layout/Sidebar'
import ChatPanel from './components/Layout/ChatPanel'
import SlidePanel from './components/Layout/SlidePanel'
import DesktopPet from './components/AgentCharacter/DesktopPet'
import ConnectionBanner from './components/ConnectionBanner'
import { useChatStore } from './stores/chatStore'
import { useAgentStore } from './stores/agentStore'
import { useCanvasStore } from './stores/canvasStore'
import { useTabStore } from './stores/tabStore'

const VirtualOffice = lazy(() => import('./components/VirtualOffice/VirtualOffice'))

export default function App() {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [officeOpen, setOfficeOpen] = useState(false)

  useEffect(() => {
    const onOpen = () => setOfficeOpen(true)
    const onClose = () => setOfficeOpen(false)
    const onToggle = () => setOfficeOpen((v) => !v)
    window.addEventListener('agenthub:open-office', onOpen)
    window.addEventListener('agenthub:close-office', onClose)
    window.addEventListener('agenthub:toggle-office', onToggle)
    return () => {
      window.removeEventListener('agenthub:open-office', onOpen)
      window.removeEventListener('agenthub:close-office', onClose)
      window.removeEventListener('agenthub:toggle-office', onToggle)
    }
  }, [])

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
      <ConnectionBanner />
      <div
        className={`sidebar-overlay ${mobileSidebarOpen ? 'visible' : ''}`}
        onClick={() => setMobileSidebarOpen(false)}
      />
      <Sidebar mobileOpen={mobileSidebarOpen} onClose={() => setMobileSidebarOpen(false)} />
      <ChatPanel onToggleSidebar={() => setMobileSidebarOpen((v) => !v)} />
      <SlidePanel />
      <DesktopPet />
      {officeOpen && (
        <Suspense fallback={null}>
          <VirtualOffice open={officeOpen} onClose={() => setOfficeOpen(false)} />
        </Suspense>
      )}
    </div>
  )
}
