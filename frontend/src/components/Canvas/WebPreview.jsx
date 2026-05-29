import React, { useRef, useCallback } from 'react'
import { useCanvasStore } from '../../stores/canvasStore'
import { PREVIEW_HTML } from './previewHtml'

export default function WebPreview() {
  const previewHtml = useCanvasStore((s) => s.previewHtml)
  const html = previewHtml || PREVIEW_HTML.todo
  const iframeRef = useRef(null)

  // Click on iframe area to give it keyboard focus (critical for games)
  const handleFocus = useCallback(() => {
    if (iframeRef.current) {
      iframeRef.current.focus()
    }
  }, [])

  return (
    <div className="web-preview">
      <div className="preview-url-bar">
        <span style={{ color: '#10b981', fontSize: 12 }}>●</span>
        <input value="http://localhost:3000/preview" readOnly />
        <button
          onClick={handleFocus}
          style={{
            background: 'rgba(99,102,241,0.15)',
            border: '1px solid rgba(99,102,241,0.3)',
            borderRadius: 4,
            color: '#a5b4fc',
            fontSize: 11,
            padding: '2px 8px',
            cursor: 'pointer',
            marginLeft: 6,
          }}
          title="点击聚焦预览窗口，激活键盘操作"
        >
          🎮 聚焦
        </button>
      </div>
      <iframe
        ref={iframeRef}
        className="preview-iframe"
        srcDoc={html}
        sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
        title="Preview"
        tabIndex={0}
        onClick={handleFocus}
        style={{ outline: 'none' }}
      />
    </div>
  )
}
