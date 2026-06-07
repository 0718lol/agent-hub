import React from 'react'
import { Settings } from 'lucide-react'

export default function SidebarFooter({ setSettingsTab, setShowSettings }) {
  return (
    <div className="sidebar-footer">
      <div className="sidebar-footer-item" onClick={() => { setSettingsTab('llm'); setShowSettings(true) }}>
        <Settings size={16} />
        <span>设置</span>
      </div>
    </div>
  )
}
