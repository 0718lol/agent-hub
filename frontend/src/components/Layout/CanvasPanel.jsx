import React, { lazy, Suspense } from 'react'
import { useCanvasStore } from '../../stores/canvasStore'
import TaskBoard from '../Canvas/TaskBoard'
import WebPreview from '../Canvas/WebPreview'
import TraceView from '../Canvas/TraceView'

const AgentFlow = lazy(() => import('../Canvas/AgentFlow'))
const DiffViewer = lazy(() => import('../Canvas/DiffViewer'))
const DeployPanel = lazy(() => import('../Canvas/DeployPanel'))
const EvalDashboard = lazy(() => import('../Canvas/EvalDashboard'))

function DeferredPanel({ children }) {
  return <Suspense fallback={<div style={{ padding: 16, color: 'var(--text-muted)' }}>正在加载...</div>}>{children}</Suspense>
}

export default function CanvasPanel() {
  const activeTab = useCanvasStore((s) => s.activeTab)
  const setActiveTab = useCanvasStore((s) => s.setActiveTab)

  const tabs = [
    { key: 'dag', label: '协作图' },
    { key: 'tasks', label: '任务' },
    { key: 'diff', label: '代码' },
    { key: 'preview', label: '预览' },
    { key: 'deploy', label: '部署' },
    { key: 'eval', label: '📊 评估' },
    { key: 'trace', label: '🔍 Trace' },
  ]

  return (
    <div className="canvas-panel">
      <div className="canvas-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className={`canvas-tab ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="canvas-content">
        {activeTab === 'dag' && <DeferredPanel><AgentFlow /></DeferredPanel>}
        {activeTab === 'tasks' && <TaskBoard />}
        {activeTab === 'diff' && <DeferredPanel><DiffViewer /></DeferredPanel>}
        {activeTab === 'preview' && <WebPreview />}
        {activeTab === 'deploy' && <DeferredPanel><DeployPanel /></DeferredPanel>}
        {activeTab === 'eval' && <DeferredPanel><EvalDashboard /></DeferredPanel>}
        {activeTab === 'trace' && <TraceView />}
      </div>
    </div>
  )
}
