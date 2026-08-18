import React, { useEffect, useRef, useState } from 'react'
import { Activity } from 'lucide-react'

export default function ReadinessControl({ readiness }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const close = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  const tone = readiness?.service === 'offline'
    ? 'error'
    : readiness?.model === 'connected' && readiness?.buildServices === 'ready'
      ? 'ready'
      : 'warning'

  const rows = [
    ['服务', readiness?.service === 'online' ? '在线' : '离线', readiness?.service === 'online'],
    ['模型', readiness?.model === 'connected' ? '已连接' : '演示模式', readiness?.model === 'connected'],
    ['构建服务', readiness?.buildServices === 'ready' ? '已就绪' : '受限', readiness?.buildServices === 'ready'],
  ]

  return (
    <div className="header-icon-btn-wrapper" ref={rootRef}>
      <button
        type="button"
        className={`header-icon-btn readiness-button readiness-${tone}`}
        onClick={() => setOpen((value) => !value)}
        aria-label="运行状态"
        title="运行状态"
      >
        <Activity size={19} />
        <span className="readiness-dot" />
      </button>
      {open && (
        <div className="header-popup readiness-popup" role="status">
          {rows.map(([label, value, ok]) => (
            <div className="readiness-row" key={label}>
              <span>{label}</span>
              <strong className={ok ? 'ok' : 'limited'}>{value}</strong>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
