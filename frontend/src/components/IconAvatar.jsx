import React from 'react'
import { getIconForEmoji } from '../utils/iconMap'

/**
 * Renders a Lucide SVG icon from an emoji string.
 * Falls back to rendering the emoji as text if no match found.
 */
export default function IconAvatar({ emoji, size = 20, className = '', style = {} }) {
  if (!emoji) return null
  const mapped = getIconForEmoji(emoji)
  if (!mapped) return <span style={style}>{emoji}</span>

  const { icon: IconComponent, color } = mapped
  return (
    <IconComponent
      size={size}
      color={color}
      className={className}
      style={{ flexShrink: 0, ...style }}
      strokeWidth={2}
    />
  )
}
