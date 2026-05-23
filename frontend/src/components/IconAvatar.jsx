import React from 'react'
import { getIconForAgent } from '../utils/iconMap'
import { Bot } from 'lucide-react'

/**
 * Agent 头像组件 — 纯 Lucide 线性图标渲染。
 * @param {{ agentId?: string, iconKey?: string, size?: number, className?: string, style?: object }} props
 */
export default function IconAvatar({ agentId, iconKey, size = 20, className = '', style = {} }) {
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
