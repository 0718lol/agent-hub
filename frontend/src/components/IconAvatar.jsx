import React, { useState } from 'react'
import { getIconForAgent } from '../utils/iconMap'
import { useAgentStore } from '../stores/agentStore'
import { Bot } from 'lucide-react'

function isImageUrl(val) {
  if (!val || typeof val !== 'string') return false
  return val.startsWith('/uploads/') || val.startsWith('/avatars/') || val.startsWith('http://') || val.startsWith('https://')
}

/**
 * Agent 头像组件 — Lucide 图标 / 自定义图片自适应。
 * @param {{ agentId?: string, iconKey?: string, size?: number, className?: string, style?: object }} props
 */
export default function IconAvatar({ agentId, iconKey, size = 20, className = '', style = {} }) {
  const [imgError, setImgError] = useState(false)

  // 查找 Agent 数据
  const agent = agentId ? useAgentStore.getState().agents.find((a) => a.agent_id === agentId) : null
  const avatarUrl = isImageUrl(agent?.avatar) ? agent.avatar : null

  // 自定义图片头像
  if (avatarUrl && !imgError) {
    return (
      <img
        src={avatarUrl}
        alt={agent?.name || ''}
        className={className}
        onError={() => setImgError(true)}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          flexShrink: 0,
          ...style,
        }}
      />
    )
  }

  // 纯图标头像 → Lucide 图标
  const { icon: IconComponent, color } =
    agentId ? getIconForAgent(agentId) :
    iconKey ? getIconForAgent(iconKey) :
    { icon: Bot, color: '#6366f1' }

  return (
    <IconComponent
      size={size}
      color={color}
      className={className}
      style={{ flexShrink: 0, ...style }}
      strokeWidth={1.8}
    />
  )
}
