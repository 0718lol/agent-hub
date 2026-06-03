import React, { useState, useRef, useEffect, useCallback } from 'react'
import { X } from 'lucide-react'
import { useCanvasStore } from '../../stores/canvasStore'
import DiffViewer from '../Canvas/DiffViewer'
import WebPreview from '../Canvas/WebPreview'
import DeployPanel from '../Canvas/DeployPanel'
import ToolsPanel from './ToolsPanel'
import KnowledgePanel from './KnowledgePanel'

const MIN_WIDTH = 280
const MAX_WIDTH = 680

export default function SlidePanel() {
  const open = useCanvasStore((s) => s.slidePanelOpen)
  const content = useCanvasStore((s) => s.slidePanelContent)
  const tab = useCanvasStore((s) => s.slidePanelTab)
  const storedWidth = useCanvasStore((s) => s.slidePanelWidth)
  const toggleSlidePanel = useCanvasStore((s) => s.toggleSlidePanel)
  const setTab = useCanvasStore((s) => s.setSlidePanelTab)
  const setSlidePanelWidth = useCanvasStore((s) => s.setSlidePanelWidth)

  const [dragging, setDragging] = useState(false)
  const panelRef = useRef(null)
  const dragStartX = useRef(0)
  const dragStartWidth = useRef(0)

  const handleMouseDown = useCallback((e) => {
    e.preventDefault()
    dragStartX.current = e.clientX
    dragStartWidth.current = storedWidth
    setDragging(true)
  }, [storedWidth])

  useEffect(() => {
    if (!dragging) return

    const handleMouseMove = (e) => {
      const delta = dragStartX.current - e.clientX
      const newWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, dragStartWidth.current + delta))
      setSlidePanelWidth(newWidth)
    }

    const handleMouseUp = () => {
      setDragging(false)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }
  }, [dragging, setSlidePanelWidth])

  return (
    <div
      ref={panelRef}
      className={`slide-panel ${open ? 'open' : ''} ${dragging ? 'dragging' : ''}`}
      style={{ width: open ? storedWidth : 0 }}
    >
      {/* 拖拽手柄 */}
      <div
        className="slide-panel-handle"
        onMouseDown={handleMouseDown}
        title="拖拽调节宽度"
      />

      {/* Header: 只有 code 类型显示 tab 切换 */}
      {content === 'code' && (
        <div className="slide-panel-header">
          <div className="slide-panel-tabs">
            <button
              className={`slide-panel-tab ${tab === 'code' ? 'active' : ''}`}
              onClick={() => setTab('code')}
            >
              代码
            </button>
            <button
              className={`slide-panel-tab ${tab === 'preview' ? 'active' : ''}`}
              onClick={() => setTab('preview')}
            >
              预览
            </button>
            <button
              className={`slide-panel-tab ${tab === 'deploy' ? 'active' : ''}`}
              onClick={() => setTab('deploy')}
            >
              部署
            </button>
          </div>
          <div className="slide-panel-actions">
            <button className="slide-panel-btn" onClick={() => toggleSlidePanel(content)} title="关闭面板">
              <X size={16} />
            </button>
          </div>
        </div>
      )}

      {/* Header: tools/knowledge 类型只有关闭按钮 */}
      {(content === 'tools' || content === 'knowledge') && (
        <div className="slide-panel-header">
          <div className="slide-panel-tabs" />
          <div className="slide-panel-actions">
            <button className="slide-panel-btn" onClick={() => toggleSlidePanel(content)} title="关闭面板">
              <X size={16} />
            </button>
          </div>
        </div>
      )}

      <div className="slide-panel-content">
        {content === 'code' && tab === 'code' && <DiffViewer />}
        {content === 'code' && tab === 'preview' && <WebPreview />}
        {content === 'code' && tab === 'deploy' && <DeployPanel />}
        {content === 'tools' && <ToolsPanel />}
        {content === 'knowledge' && <KnowledgePanel />}
      </div>
    </div>
  )
}
