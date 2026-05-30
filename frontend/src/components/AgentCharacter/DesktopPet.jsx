import React, { useState, useEffect, useRef } from 'react'
import AgentCharacter, { MOOD_EMOJIS } from './AgentCharacter'
import DraggableFloating from './DraggableFloating'
import PetMiniChat from './PetMiniChat'
import { useAgentAction } from '../../hooks/useAgentAction'
import { AGENT_ACTIONS } from './agentAction.types'
import './DesktopPet.css'

const PET_WIDTH = 96
const PET_HEIGHT = 130
const DOUBLE_CLICK_MS = 260

// 空闲时随机小动作池（每 8-18 秒触发一次）
const IDLE_TRICKS = [
  { action: AGENT_ACTIONS.WAVE, duration: 1800, bubble: '嗨~' },
  { action: AGENT_ACTIONS.JUMP, duration: 1400, bubble: 'yeah!' },
  { action: AGENT_ACTIONS.STRETCH, duration: 2000, bubble: '伸个懒腰~' },
  { action: AGENT_ACTIONS.WAVE, duration: 1500, bubble: null },
  { action: AGENT_ACTIONS.JUMP, duration: 1000, bubble: null },
  { action: 'mood', duration: 0, bubble: null },  // 不换动作，只冒个表情
]

export default function DesktopPet({ enabled = true }) {
  const [chatOpen, setChatOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [officeOpen, setOfficeOpen] = useState(false)
  const [hidden, setHidden] = useState(() => {
    try { return localStorage.getItem('agenthub-pet-hidden') === '1' } catch { return false }
  })
  const [trickAction, setTrickAction] = useState(null)
  const [moodTag, setMoodTag] = useState(null)
  const clickTimerRef = useRef(null)
  const trickTimerRef = useRef(null)
  const moodTimerRef = useRef(null)

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

  // 闲时小动作调度：只在 idle 时启动
  useEffect(() => {
    if (action !== AGENT_ACTIONS.IDLE) return
    const scheduleNext = () => {
      const delay = 8000 + Math.random() * 10000  // 8-18 秒
      trickTimerRef.current = setTimeout(() => {
        const trick = IDLE_TRICKS[Math.floor(Math.random() * IDLE_TRICKS.length)]
        if (trick.action === 'mood') {
          const emoji = MOOD_EMOJIS[Math.floor(Math.random() * MOOD_EMOJIS.length)]
          setMoodTag({ emoji, key: Date.now() })
          if (moodTimerRef.current) clearTimeout(moodTimerRef.current)
          moodTimerRef.current = setTimeout(() => setMoodTag(null), 1700)
        } else {
          setTrickAction(trick.action)
          if (trick.bubble) setBubble(trick.bubble, trick.duration)
          setTimeout(() => setTrickAction(null), trick.duration)
        }
        scheduleNext()
      }, delay)
    }
    scheduleNext()
    return () => {
      if (trickTimerRef.current) clearTimeout(trickTimerRef.current)
    }
  }, [action, setBubble])

  useEffect(() => {
    return () => {
      if (clickTimerRef.current) clearTimeout(clickTimerRef.current)
      if (trickTimerRef.current) clearTimeout(trickTimerRef.current)
      if (moodTimerRef.current) clearTimeout(moodTimerRef.current)
    }
  }, [])

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
    if (clickTimerRef.current) {
      clearTimeout(clickTimerRef.current)
      clickTimerRef.current = null
      setChatOpen(false)
      setBubble('打开工作室啦~', 1500)
      window.dispatchEvent(new Event('agenthub:toggle-office'))
      return
    }
    clickTimerRef.current = setTimeout(() => {
      clickTimerRef.current = null
      setChatOpen((v) => !v)
      // 点击时也冒一个爱心
      setMoodTag({ emoji: '💬', key: Date.now() })
      if (moodTimerRef.current) clearTimeout(moodTimerRef.current)
      moodTimerRef.current = setTimeout(() => setMoodTag(null), 1700)
    }, DOUBLE_CLICK_MS)
  }

  const handleContextMenu = (e) => {
    e.preventDefault()
    if (clickTimerRef.current) {
      clearTimeout(clickTimerRef.current)
      clickTimerRef.current = null
    }
    setChatOpen(false)
    setMenuOpen(true)
  }

  const handleMenuAction = (key) => {
    setMenuOpen(false)
    if (key === 'chat') setChatOpen(true)
    else if (key === 'sleep') setBubble('该睡了 zzz...', 2000)
    else if (key === 'hide') setHidden(true)
    else if (key === 'office') window.dispatchEvent(new Event('agenthub:toggle-office'))
    else if (key === 'wave') { setTrickAction(AGENT_ACTIONS.WAVE); setBubble('嗨~', 1800); setTimeout(() => setTrickAction(null), 1800) }
    else if (key === 'jump') { setTrickAction(AGENT_ACTIONS.JUMP); setBubble('yeah!', 1400); setTimeout(() => setTrickAction(null), 1400) }
    else if (key === 'stretch') { setTrickAction(AGENT_ACTIONS.STRETCH); setBubble('伸个懒腰~', 2000); setTimeout(() => setTrickAction(null), 2000) }
  }

  // 最终展示的动作：trick 优先，其次走 hook 算出来的 action
  const renderAction = trickAction || action

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
          <button onClick={() => handleMenuAction('wave')}>👋 让它招招手</button>
          <button onClick={() => handleMenuAction('jump')}>🤸 让它跳一下</button>
          <button onClick={() => handleMenuAction('stretch')}>🙆 让它伸懒腰</button>
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
        action={renderAction}
        bubble={bubble}
        scale={1}
        followMouse={true}
        hoverHappy={true}
        moodTag={moodTag}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
      />
    </DraggableFloating>
  )
}
