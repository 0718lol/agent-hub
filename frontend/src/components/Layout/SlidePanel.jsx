import React from 'react'
import { X, Pin } from 'lucide-react'
import { useCanvasStore } from '../../stores/canvasStore'
import DiffViewer from '../Canvas/DiffViewer'
import WebPreview from '../Canvas/WebPreview'

export default function SlidePanel() {
  const open = useCanvasStore((s) => s.slidePanelOpen)
  const pinned = useCanvasStore((s) => s.slidePanelPinned)
  const tab = useCanvasStore((s) => s.slidePanelTab)
  const toggleSlidePanel = useCanvasStore((s) => s.toggleSlidePanel)
  const togglePin = useCanvasStore((s) => s.toggleSlidePanelPin)
  const setTab = useCanvasStore((s) => s.setSlidePanelTab)

  const handleOverlayClick = () => {
    if (!pinned) toggleSlidePanel()
  }

  return (
    <>
      <div
        className={`slide-panel-overlay ${open ? 'visible' : ''}`}
        onClick={handleOverlayClick}
      />
      <div className={`slide-panel ${open ? 'open' : ''}`}>
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
          </div>
          <div className="slide-panel-actions">
            <button
              className={`slide-panel-btn ${pinned ? 'pinned' : ''}`}
              onClick={togglePin}
              title={pinned ? '取消常驻' : '常驻面板'}
            >
              <Pin size={16} />
            </button>
            <button className="slide-panel-btn" onClick={toggleSlidePanel} title="关闭面板">
              <X size={16} />
            </button>
          </div>
        </div>
        <div className="slide-panel-content">
          {tab === 'code' && <DiffViewer />}
          {tab === 'preview' && <WebPreview />}
        </div>
      </div>
    </>
  )
}
