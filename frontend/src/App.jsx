import React, { useState } from 'react'
import Sidebar from './components/Layout/Sidebar'
import ChatPanel from './components/Layout/ChatPanel'
import SlidePanel from './components/Layout/SlidePanel'

export default function App() {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

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
