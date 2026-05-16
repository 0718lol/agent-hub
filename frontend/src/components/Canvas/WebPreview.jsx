import React from 'react'
import { useCanvasStore } from '../../stores/canvasStore'
import { PREVIEW_HTML } from './previewHtml'

export default function WebPreview() {
  const previewHtml = useCanvasStore((s) => s.previewHtml)
  const html = previewHtml || PREVIEW_HTML.todo

  return (
    <div className="web-preview">
      <div className="preview-url-bar">
        <span style={{ color: '#10b981', fontSize: 12 }}>●</span>
        <input value="http://localhost:3000/preview" readOnly />
      </div>
      <iframe
        className="preview-iframe"
        srcDoc={html}
        sandbox="allow-scripts"
        title="Preview"
      />
    </div>
  )
}
