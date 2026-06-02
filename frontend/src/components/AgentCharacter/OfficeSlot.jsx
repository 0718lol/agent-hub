import React from 'react'

/**
 * OfficeSlot — 工位/休息位包装器（VirtualOffice 专用）
 *
 * 与 DraggableFloating 并列，是 AgentCharacter 的另一种"挂载方式"：
 *   - DraggableFloating: 用户可拖动，全屏 fixed 定位（桌宠场景）
 *   - OfficeSlot:        位置固定，相对父容器 absolute 定位（工作室场景）
 *
 * Props:
 *   position: { x, y }    工位坐标（相对 VirtualOffice 容器）
 *   width / height        槽位尺寸（用于碰撞检测、命名牌定位）
 *   slotType: 'desk' | 'sofa' | 'gym' | 'coffee' | 'walk'
 *   slotLabel: string     可选：工位 / 沙发 等家具说明文字
 *   highlight: boolean    高亮（如主管走过来时）
 */
export default function OfficeSlot({
  position = { x: 0, y: 0 },
  width = 96,
  height = 130,
  slotType = 'desk',
  slotLabel = '',
  highlight = false,
  zIndex = 1,
  children,
}) {
  return (
    <div
      className={`office-slot office-slot-${slotType} ${highlight ? 'office-slot-highlight' : ''}`}
      style={{
        position: 'absolute',
        left: position.x,
        top: position.y,
        width,
        height,
        zIndex,
        transition: 'left 0.6s ease, top 0.6s ease',
      }}
      data-slot-type={slotType}
    >
      {slotLabel && (
        <div className="office-slot-label">{slotLabel}</div>
      )}
      {children}
    </div>
  )
}
