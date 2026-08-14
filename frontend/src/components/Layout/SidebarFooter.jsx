import React from 'react'
import { LogOut, Settings, UserRound } from 'lucide-react'

export default function SidebarFooter({ currentUser, setSettingsTab, setShowSettings }) {
  const logout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' }).catch(() => {})
    window.location.reload()
  }

  return (
    <div className="sidebar-footer">
      <button className="sidebar-footer-item" onClick={() => { setSettingsTab('llm'); setShowSettings(true) }} title="设置">
        <Settings size={16} />
        <span>设置</span>
      </button>
      <div className="sidebar-account" title={currentUser?.username || ''}>
        <UserRound size={16} />
        <span>{currentUser?.username}</span>
      </div>
      <button className="sidebar-footer-item sidebar-logout" onClick={logout} title="退出登录">
        <LogOut size={16} />
        <span>退出</span>
      </button>
    </div>
  )
}
