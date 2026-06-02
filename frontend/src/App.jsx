import React, { useState, useEffect } from 'react'
import Sidebar from './components/Layout/Sidebar'
import ChatPanel from './components/Layout/ChatPanel'
import SlidePanel from './components/Layout/SlidePanel'
import DesktopPet from './components/AgentCharacter/DesktopPet'
import VirtualOffice from './components/VirtualOffice/VirtualOffice'
import { useChatStore } from './stores/chatStore'
import { useAgentStore } from './stores/agentStore'
import { useCanvasStore } from './stores/canvasStore'

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
    useChatStore.getState().fetchConversations()
    useAgentStore.getState().fetchAgents()
    useCanvasStore.getState().fetchDAGFromBackend()
  }, [])

  return (
    <div className="app-layout">
      <div
        className={`sidebar-overlay ${mobileSidebarOpen ? 'visible' : ''}`}
        onClick={() => setMobileSidebarOpen(false)}
      />
      <Sidebar mobileOpen={mobileSidebarOpen} onClose={() => setMobileSidebarOpen(false)} />
      <ChatPanel onToggleSidebar={() => setMobileSidebarOpen((v) => !v)} />
      <SlidePanel />
      <DesktopPet />
      <VirtualOffice open={officeOpen} onClose={() => setOfficeOpen(false)} />
    </div>
  )
}
