import React from 'react'
import { Settings } from 'lucide-react'

export default function GoalSnapshot({ readiness }) {
  const openModelSettings = () => {
    window.dispatchEvent(new CustomEvent('open-settings', { detail: { tab: 'llm' } }))
  }

  const showPreflight = readiness && !readiness.loading
  if (!showPreflight) return null

  return (
    <section className="goal-snapshot" aria-label="模型状态">
      <div className={`task-preflight ${readiness.service === 'offline' ? 'error' : readiness.model === 'demo' ? 'warning' : 'ready'}`}>
        <span className="task-preflight-dot" />
        <strong>{readiness.service === 'offline' ? '服务离线' : readiness.model === 'demo' ? '演示模式' : '模型已连接'}</strong>
        <span>{readiness.buildServices === 'ready' ? '构建服务已就绪' : '后台构建受限'}</span>
        {readiness.model === 'demo' && readiness.service === 'online' && (
          <button type="button" onClick={openModelSettings} title="连接模型" aria-label="连接模型">
            <Settings size={14} />
          </button>
        )}
        </div>
    </section>
  )
}
