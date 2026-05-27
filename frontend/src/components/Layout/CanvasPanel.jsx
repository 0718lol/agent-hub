import React from 'react'
import { useCanvasStore } from '../../stores/canvasStore'
import AgentDAG from '../Canvas/AgentDAG'
import TaskBoard from '../Canvas/TaskBoard'
import DiffViewer from '../Canvas/DiffViewer'
import WebPreview from '../Canvas/WebPreview'
import DeployPanel from '../Canvas/DeployPanel'

export default function CanvasPanel() {
  const activeTab = useCanvasStore((s) => s.activeTab)
  const setActiveTab = useCanvasStore((s) => s.setActiveTab)

  const tabs = [
    { key: 'dag', label: '协作图' },
    { key: 'tasks', label: '任务' },
    { key: 'diff', label: '代码' },
    { key: 'preview', label: '预览' },
    { key: 'deploy', label: '部署' },
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
        {activeTab === 'dag' && <AgentDAG />}
        {activeTab === 'tasks' && <TaskBoard />}
        {activeTab === 'diff' && <DiffViewer />}
        {activeTab === 'preview' && <WebPreview />}
        {activeTab === 'deploy' && <DeployPanel />}
      </div>
    </div>
  )
}

