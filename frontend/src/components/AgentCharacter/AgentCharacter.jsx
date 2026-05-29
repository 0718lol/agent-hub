import React from 'react'
import AgentBubble from './AgentBubble'
import { ALL_ACTIONS, AGENT_ACTIONS, DEFAULT_THEME_COLOR } from './agentAction.types'
import './AgentCharacter.css'

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
  onClick,
  onContextMenu,
  style = {},
  className = '',
}) {
  const safeAction = ALL_ACTIONS.includes(action) ? action : AGENT_ACTIONS.IDLE
  const isEmojiAvatar = typeof avatar === 'string' && avatar.length <= 4 && !avatar.startsWith('http')

  return (
    <div
      className={`ac-root ac-${safeAction} ${className}`}
      style={{
        left: position.x,
        top: position.y,
        transform: `scale(${scale})`,
        '--ac-theme': themeColor,
        ...style,
      }}
      onClick={onClick}
      onContextMenu={onContextMenu}
      data-agent-id={agentId}
      title={agentName}
    >
      {bubble && <AgentBubble text={bubble} variant={bubbleVariant} />}

      <svg
        className="ac-sprite"
        viewBox="0 0 100 140"
        width="80"
        height="112"
        xmlns="http://www.w3.org/2000/svg"
      >
        <g className="ac-antenna">
          <line x1="50" y1="18" x2="50" y2="6" stroke="var(--ac-theme)" strokeWidth="2" strokeLinecap="round" />
          <circle cx="50" cy="5" r="3" fill="var(--ac-theme)" />
        </g>

        <g className="ac-body">
          <rect x="22" y="60" width="56" height="50" rx="10" fill="#f5f5f7" stroke="#d1d1d6" strokeWidth="1.5" />
          <rect x="32" y="72" width="36" height="22" rx="4" fill="var(--ac-theme)" opacity="0.15" />
          <circle cx="50" cy="83" r="3" fill="var(--ac-theme)" />

          <g className="ac-arm ac-arm-left">
            <rect x="14" y="65" width="8" height="22" rx="4" fill="#e5e5ea" />
          </g>
          <g className="ac-arm ac-arm-right">
            <rect x="78" y="65" width="8" height="22" rx="4" fill="#e5e5ea" />
          </g>

          <rect x="32" y="110" width="12" height="14" rx="3" fill="#a1a1a6" />
          <rect x="56" y="110" width="12" height="14" rx="3" fill="#a1a1a6" />
        </g>

        <g className="ac-head">
          <rect x="20" y="20" width="60" height="44" rx="14" fill="#ffffff" stroke="#d1d1d6" strokeWidth="1.5" />

          <g className="ac-eye ac-eye-left">
            <circle cx="36" cy="40" r="4" fill="#1d1d1f" />
            <circle cx="37" cy="38.5" r="1.2" fill="#ffffff" />
          </g>
          <g className="ac-eye ac-eye-right">
            <circle cx="64" cy="40" r="4" fill="#1d1d1f" />
            <circle cx="65" cy="38.5" r="1.2" fill="#ffffff" />
          </g>

          <path className="ac-mouth" d="M 44 52 Q 50 56 56 52" stroke="#1d1d1f" strokeWidth="1.8" fill="none" strokeLinecap="round" />

          <circle cx="28" cy="50" r="2" fill="#ff9aa2" opacity="0.5" />
          <circle cx="72" cy="50" r="2" fill="#ff9aa2" opacity="0.5" />
        </g>

        {safeAction === 'sleep' && (
          <g className="ac-zzz">
            <text x="72" y="22" fontSize="10" fill="var(--ac-theme)" fontWeight="600">Z</text>
            <text x="80" y="14" fontSize="8" fill="var(--ac-theme)" fontWeight="600" opacity="0.7">z</text>
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
