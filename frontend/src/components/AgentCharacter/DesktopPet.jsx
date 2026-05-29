import React, { useState, useEffect } from 'react'
import AgentCharacter from './AgentCharacter'
import DraggableFloating from './DraggableFloating'
import PetMiniChat from './PetMiniChat'
import { useAgentAction } from '../../hooks/useAgentAction'
import './DesktopPet.css'

const PET_WIDTH = 96
const PET_HEIGHT = 130

export default function DesktopPet({ enabled = true }) {
  const [chatOpen, setChatOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [officeOpen, setOfficeOpen] = useState(false)
  const [hidden, setHidden] = useState(() => {
    try { return localStorage.getItem('agenthub-pet-hidden') === '1' } catch { return false }
  })

  const { action, bubble, setBubble } = useAgentAction(null)

  useEffect(() => {
    try { localStorage.setItem('agenthub-pet-hidden', hidden ? '1' : '0') } catch {}
  }, [hidden])

  useEffect(() => {
    const onOfficeOpen = () => setOfficeOpen(true)
    const onOfficeClose = () => setOfficeOpen(false)
    const onOfficeToggle = () => setOfficeOpen((v) => !v)
    window.addEventListener('agenthub:open-office', onOfficeOpen)
    window.addEventListener('agenthub:close-office', onOfficeClose)
    window.addEventListener('agenthub:toggle-office', onOfficeToggle)
    return () => {
      window.removeEventListener('agenthub:open-office', onOfficeOpen)
      window.removeEventListener('agenthub:close-office', onOfficeClose)
      window.removeEventListener('agenthub:toggle-office', onOfficeToggle)
    }
  }, [])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') {
        setChatOpen(false)
        setMenuOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // 工作室开着时桌宠完全隐藏（共用资源、避免遮挡）
  if (officeOpen) return null

  if (!enabled || hidden) {
    return (
      <button
        className="pet-show-btn"
        onClick={() => setHidden(false)}
        title="召唤桌宠"
      >🤖</button>
    )
  }

  const handleClick = () => {
    setMenuOpen(false)
    setChatOpen((v) => !v)
  }

  const handleContextMenu = (e) => {
    e.preventDefault()
    setChatOpen(false)
    setMenuOpen(true)
  }

  const handleMenuAction = (key) => {
    setMenuOpen(false)
    if (key === 'chat') setChatOpen(true)
    else if (key === 'sleep') setBubble('该睡了 zzz...', 2000)
    else if (key === 'hide') setHidden(true)
    else if (key === 'office') window.dispatchEvent(new Event('agenthub:toggle-office'))
  }

  return (
    <DraggableFloating
      width={PET_WIDTH}
      height={PET_HEIGHT}
      storageKey="agenthub-pet-pos"
      snapToEdge={false}
    >
      {chatOpen && (
        <div className="pet-mini-chat-wrap">
          <PetMiniChat
            agentId={null}
            onClose={() => setChatOpen(false)}
            onBubble={(t) => setBubble(t, 2500)}
          />
        </div>
      )}

      {menuOpen && (
        <div className="pet-context-menu" onPointerDown={(e) => e.stopPropagation()}>
          <button onClick={() => handleMenuAction('chat')}>💬 快速对话</button>
          <button onClick={() => handleMenuAction('office')}>🏢 打开工作室</button>
          <button onClick={() => handleMenuAction('sleep')}>😴 让它休息</button>
          <button onClick={() => handleMenuAction('hide')}>❌ 隐藏桌宠</button>
        </div>
      )}

      <AgentCharacter
        agentId="agent_pet"
        agentName="AgentHub 助手"
        avatar="🤖"
        themeColor="var(--accent, #6366f1)"
        position={{ x: 8, y: 16 }}
        action={action}
        bubble={bubble}
        scale={1}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
      />
    </DraggableFloating>
  )
}
