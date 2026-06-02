import React from 'react'

/**
 * 通用气泡组件 — 可挂在任何元素上方
 * 桌宠用：贴在 AgentCharacter 头顶
 * VirtualOffice 用：贴在工位、休息区、主管喊话
 *
 * Props:
 *   text: string | null   — 气泡内容，null 不渲染
 *   variant: 'default' | 'thinking' | 'alert'
 *   maxWidth: number      — 最大宽度（px）
 *   align: 'left' | 'center' | 'right'  — 锚点对齐
 *   offset: number        — 距离锚点的垂直距离
 */
export default function AgentBubble({
  text,
  variant = 'default',
  maxWidth = 220,
  align = 'center',
  offset = 6,
  children,
}) {
  if (!text && !children) return null

  const alignStyle = {
    left: { left: 0, transform: 'translateX(0)' },
    center: { left: '50%', transform: 'translateX(-50%)' },
    right: { right: 0, transform: 'translateX(0)' },
  }[align] || {}

  return (
    <div
      className={`ac-bubble ac-bubble-${variant} ac-bubble-${align}`}
      style={{
        bottom: `calc(100% + ${offset}px)`,
        maxWidth,
        ...alignStyle,
      }}
    >
      <span className="ac-bubble-text">{text || children}</span>
    </div>
  )
}
