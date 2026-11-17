import React, { lazy, Suspense, useState, useEffect } from 'react'
import Sidebar from './components/Layout/Sidebar'
import ChatPanel from './components/Layout/ChatPanel'
import SlidePanel from './components/Layout/SlidePanel'
import DesktopPet from './components/AgentCharacter/DesktopPet'
import ConnectionBanner from './components/ConnectionBanner'
import WorkbenchModal from './components/Workbench/WorkbenchModal'
import { useChatStore } from './stores/chatStore'
import { useAgentStore } from './stores/agentStore'
import { useCanvasStore } from './stores/canvasStore'
import { useTabStore } from './stores/tabStore'
import { useReadiness } from './hooks/useReadiness'

const VirtualOffice = lazy(() => import('./components/VirtualOffice/VirtualOffice'))

export default function App({ currentUser }) {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [officeOpen, setOfficeOpen] = useState(false)
  const [workbenchOpen, setWorkbenchOpen] = useState(false)
  const activeTabId = useTabStore((s) => s.activeTabId)
  const openTabs = useTabStore((s) => s.openTabs)
  const activeConvId = openTabs.find((t) => t.id === activeTabId)?.convId || 'conv_pm'
  const readiness = useReadiness()
  const workbenchEnabled = Boolean(readiness.workbench || currentUser?.workbench_mode || currentUser?.user_id === 'local')

  useEffect(() => {
    const onOpen = () => setOfficeOpen(true)
    const onClose = () => setOfficeOpen(false)
    const onToggle = () => setOfficeOpen((v) => !v)
    const onOpenWorkbench = () => setWorkbenchOpen(true)
    window.addEventListener('agenthub:open-office', onOpen)
    window.addEventListener('agenthub:close-office', onClose)
    window.addEventListener('agenthub:toggle-office', onToggle)
    window.addEventListener('agenthub:open-workbench', onOpenWorkbench)
    return () => {
      window.removeEventListener('agenthub:open-office', onOpen)
      window.removeEventListener('agenthub:close-office', onClose)
      window.removeEventListener('agenthub:toggle-office', onToggle)
      window.removeEventListener('agenthub:open-workbench', onOpenWorkbench)
    }
  }, [])

  // Scope browser state before fetching tenant-owned data.
  useEffect(() => {
    useTabStore.getState().setOwner(currentUser.tenant_id)
    useAgentStore.getState().setOwner(currentUser.tenant_id)
    useChatStore.getState().setOwner(currentUser.tenant_id)
    useCanvasStore.getState().setOwner(currentUser.tenant_id)
    useChatStore.getState().fetchConversations().then(() => {
      // 对话加载完成后，清理指向不存在对话的幽灵标签
      const convIds = useChatStore.getState().conversations.map((c) => c.id)
      useTabStore.getState().syncWithConversations(convIds)
    })
    useAgentStore.getState().fetchAgents()
    useCanvasStore.getState().fetchDAGFromBackend()
  }, [currentUser.tenant_id])

  return (
    <div className="app-layout">
      <ConnectionBanner />
      <div
        className={`sidebar-overlay ${mobileSidebarOpen ? 'visible' : ''}`}
        onClick={() => setMobileSidebarOpen(false)}
      />
      <Sidebar currentUser={currentUser} mobileOpen={mobileSidebarOpen} onClose={() => setMobileSidebarOpen(false)} />
      <ChatPanel readiness={readiness} onToggleSidebar={() => setMobileSidebarOpen((v) => !v)} />
      <SlidePanel />
      <DesktopPet />
      {workbenchEnabled && (
        <WorkbenchModal
          open={workbenchOpen}
          onClose={() => setWorkbenchOpen(false)}
          activeConvId={activeConvId}
        />
      )}
      {officeOpen && (
        <Suspense fallback={null}>
          <VirtualOffice open={officeOpen} onClose={() => setOfficeOpen(false)} />
        </Suspense>
      )}
    </div>
  )
}
