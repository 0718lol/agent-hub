import React, { useEffect, useRef, useState } from 'react'
import AgentBubble from './AgentBubble'
import { ALL_ACTIONS, AGENT_ACTIONS, DEFAULT_THEME_COLOR } from './agentAction.types'
import './AgentCharacter.css'

const MOOD_EMOJIS = ['❤️', '⭐', '✨', '🎵', '💡', '🌟', '☕', '🍵']

export default function AgentCharacter({
  agentId,
  agentName = '',
  avatar = '🤖',
  themeColor = DEFAULT_THEME_COLOR,
  position = { x: 0, y: 0 },
  action = AGENT_ACTIONS.IDLE,
  scale = 1,
  bubble = null,
  bubbleVariant = 'default',
  followMouse = false,
  hoverHappy = false,
  moodTag = null,
  direction = 'down',  // 'up' | 'down' | 'left' | 'right'
  onClick,
  onDoubleClick,
  onContextMenu,
  style = {},
  className = '',
}) {
  const safeAction = ALL_ACTIONS.includes(action) ? action : AGENT_ACTIONS.IDLE
  const isEmojiAvatar = typeof avatar === 'string' && avatar.length <= 4 && !avatar.startsWith('http')

  const rootRef = useRef(null)
  const [eyeOffset, setEyeOffset] = useState({ x: 0, y: 0 })
  const [hovering, setHovering] = useState(false)

  useEffect(() => {
    if (!followMouse) return
    let raf = 0
    const onMove = (e) => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        const rect = rootRef.current?.getBoundingClientRect()
        if (!rect) return
        const cx = rect.left + rect.width / 2
        const cy = rect.top + rect.height / 2
        const dx = e.clientX - cx
        const dy = e.clientY - cy
        const dist = Math.hypot(dx, dy)
        if (dist < 0.1) return setEyeOffset({ x: 0, y: 0 })
        const max = 1.8
        const ratio = Math.min(1, dist / 400)
        setEyeOffset({
          x: (dx / dist) * max * ratio,
          y: (dy / dist) * max * ratio,
        })
      })
    }
    window.addEventListener('mousemove', onMove)
    return () => {
      window.removeEventListener('mousemove', onMove)
      cancelAnimationFrame(raf)
    }
  }, [followMouse])

  const handleEnter = () => hoverHappy && setHovering(true)
  const handleLeave = () => hoverHappy && setHovering(false)

  const renderAction = hovering ? 'happy' : safeAction

  // 俯视小人：圆头 + 简化身体（椭圆）+ 手臂腿（小圆点或短线）
  return (
    <div
      ref={rootRef}
      className={`ac-root ac-topdown ac-${renderAction} ac-dir-${direction} ${className}`}
      style={{
        left: position.x,
        top: position.y,
        transform: `scale(${scale})`,
        '--ac-theme': themeColor,
        ...style,
      }}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      onContextMenu={onContextMenu}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      data-agent-id={agentId}
      title={agentName}
    >
      {bubble && <AgentBubble text={bubble} variant={bubbleVariant} />}

      {moodTag && (
        <span key={moodTag.key || moodTag.emoji} className="ac-mood-tag">{moodTag.emoji || moodTag}</span>
      )}

      <svg
        className="ac-sprite ac-sprite-topdown"
        viewBox="0 0 100 100"
        width="64"
        height="64"
        xmlns="http://www.w3.org/2000/svg"
      >
        {/* 阴影 */}
        <ellipse cx="50" cy="88" rx="22" ry="6" fill="rgba(0,0,0,0.25)" className="ac-shadow" />

        {/* 身体（椭圆） */}
        <ellipse cx="50" cy="60" rx="18" ry="24" fill="#f5f5f7" stroke="#d1d1d6" strokeWidth="1.5" className="ac-body" />

        {/* 胸口装饰 */}
        <ellipse cx="50" cy="60" rx="10" ry="14" fill="var(--ac-theme)" opacity="0.15" />
        <circle cx="50" cy="60" r="3" fill="var(--ac-theme)" />

        {/* 手臂（两个小圆点，左右） */}
        <circle cx="32" cy="58" r="5" fill="#e5e5ea" className="ac-arm ac-arm-left" />
        <circle cx="68" cy="58" r="5" fill="#e5e5ea" className="ac-arm ac-arm-right" />

        {/* 腿/脚（两个小椭圆，下方） */}
        <ellipse cx="42" cy="82" rx="5" ry="7" fill="#a1a1a6" className="ac-leg ac-leg-left" />
        <ellipse cx="58" cy="82" rx="5" ry="7" fill="#a1a1a6" className="ac-leg ac-leg-right" />

        {/* 头部（圆形） */}
        <circle cx="50" cy="32" r="18" fill="#ffffff" stroke="#d1d1d6" strokeWidth="1.5" className="ac-head" />

        {/* 天线 */}
        <line x1="50" y1="14" x2="50" y2="8" stroke="var(--ac-theme)" strokeWidth="2" strokeLinecap="round" className="ac-antenna" />
        <circle cx="50" cy="7" r="2.5" fill="var(--ac-theme)" className="ac-antenna-tip" />

        {/* 眼睛 */}
        <g className="ac-eye ac-eye-left">
          <circle cx="42" cy="30" r="3" fill="#1d1d1f"
                  transform={followMouse ? `translate(${eyeOffset.x} ${eyeOffset.y})` : undefined} />
          <circle cx="43" cy="29" r="1" fill="#ffffff"
                  transform={followMouse ? `translate(${eyeOffset.x} ${eyeOffset.y})` : undefined} />
        </g>
        <g className="ac-eye ac-eye-right">
          <circle cx="58" cy="30" r="3" fill="#1d1d1f"
                  transform={followMouse ? `translate(${eyeOffset.x} ${eyeOffset.y})` : undefined} />
          <circle cx="59" cy="29" r="1" fill="#ffffff"
                  transform={followMouse ? `translate(${eyeOffset.x} ${eyeOffset.y})` : undefined} />
        </g>

        {/* 嘴巴 */}
        <path className="ac-mouth" d="M 44 38 Q 50 41 56 38" stroke="#1d1d1f" strokeWidth="1.5" fill="none" strokeLinecap="round" />

        {/* 腮红 */}
        <circle cx="36" cy="36" r="2" fill="#ff9aa2" opacity="0.5" />
        <circle cx="64" cy="36" r="2" fill="#ff9aa2" opacity="0.5" />

        {/* sleep 状态：Zzz */}
        {safeAction === 'sleep' && (
          <g className="ac-zzz">
            <text x="66" y="20" fontSize="9" fill="var(--ac-theme)" fontWeight="600">Z</text>
            <text x="72" y="14" fontSize="7" fill="var(--ac-theme)" fontWeight="600" opacity="0.7">z</text>
          </g>
        )}

        {/* coffee 状态：手里的杯子 */}
        {safeAction === 'coffee' && (
          <circle cx="68" cy="58" r="4" fill="#fafafa" stroke="#a16207" strokeWidth="1" className="ac-coffee-cup" />
        )}

        {/* gym 状态：哑铃图标 */}
        {safeAction === 'gym' && (
          <g className="ac-dumbbells">
            <rect x="28" y="56" width="8" height="2" fill="#1f2937" />
            <circle cx="27" cy="57" r="2" fill="#1f2937" />
            <circle cx="37" cy="57" r="2" fill="#1f2937" />
          </g>
        )}
      </svg>

      {isEmojiAvatar && (
        <div className="ac-avatar-badge" title={agentName}>{avatar}</div>
      )}

      {agentName && (
        <div className="ac-nameplate">{agentName}</div>
      )}
    </div>
  )
}
export { MOOD_EMOJIS }
