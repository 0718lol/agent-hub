import React, { useRef, useCallback, useEffect, useState } from 'react'
import { useCanvasStore } from '../../stores/canvasStore'
import { PREVIEW_HTML } from './previewHtml'

// Check if HTML is complete (has closing tags)
function isCompleteHtml(html) {
  if (!html) return false
  return html.includes('</html>') || html.includes('</body>')
}

export default function WebPreview() {
  const previewHtml = useCanvasStore((s) => s.previewHtml)
  const streamingHtml = useCanvasStore((s) => s.streamingHtml)
  const clearStreamingHtml = useCanvasStore((s) => s.clearStreamingHtml)
  
  // Priority: streamingHtml > previewHtml > default
  const html = (streamingHtml && isCompleteHtml(streamingHtml)) ? streamingHtml 
    : previewHtml || PREVIEW_HTML.todo
  
  const iframeRef = useRef(null)
  const [isLoading, setIsLoading] = useState(false)
  const debounceRef = useRef(null)
  const lastHtmlRef = useRef('')

  // Click on iframe area to give it keyboard focus (critical for games)
  const handleFocus = useCallback(() => {
    if (iframeRef.current) {
      iframeRef.current.focus()
    }
  }, [])

  // Update iframe content via postMessage (no flicker)
  useEffect(() => {
    if (!iframeRef.current || !html) return
    
    // Skip if content hasn't changed
    if (html === lastHtmlRef.current) return
    lastHtmlRef.current = html

    // Debounce rapid updates (300ms)
    if (debounceRef.current) {
      clearTimeout(debounceRef.current)
    }

    setIsLoading(true)
    debounceRef.current = setTimeout(() => {
      try {
        if (iframeRef.current && iframeRef.current.contentWindow) {
          iframeRef.current.contentWindow.postMessage(
            { type: 'update', html },
            '*'
          )
        }
      } catch (e) {
        // If postMessage fails, fall back to srcdoc
        console.warn('postMessage failed, using srcdoc fallback:', e)
      }
      setIsLoading(false)
    }, 300)

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
    }
  }, [html])

  // Clean up on unmount
  useEffect(() => {
    return () => {
      clearStreamingHtml()
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
    }
  }, [clearStreamingHtml])

  return (
    <div className="web-preview">
      <div className="preview-url-bar">
        <span style={{ color: '#10b981', fontSize: 12 }}>●</span>
        <input value="http://localhost:3000/preview" readOnly />
        {isLoading && (
          <span style={{ color: 'var(--text-muted)', fontSize: 11, marginLeft: 8 }}>
            更新中...
          </span>
        )}
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
        sandbox="allow-scripts allow-popups allow-forms"
        title="Preview"
        tabIndex={0}
        onClick={handleFocus}
        style={{ outline: 'none' }}
      />
    </div>
  )
}
