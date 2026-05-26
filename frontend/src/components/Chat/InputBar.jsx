import React, { useState, useRef, useEffect } from 'react'

export default function InputBar({ onSend, isGenerating, onStop }) {
  const [text, setText] = useState('')
  const textareaRef = useRef(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px'
    }
  }, [text])

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || isGenerating) return
    onSend(trimmed)
    setText('')
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      if (e.nativeEvent.isComposing) return
      e.preventDefault()
      handleSend()
    }
  }

  if (isGenerating) {
    return (
      <div className="input-bar">
        <div className="input-wrapper" style={{ borderColor: 'rgba(239,68,68,0.3)' }}>
          <textarea
            value=""
            readOnly
            placeholder="Agent 正在工作中..."
            rows={1}
            style={{ opacity: 0.5, cursor: 'not-allowed' }}
          />
          <button
            className="send-btn"
            onClick={onStop}
            style={{ background: '#ef4444' }}
            title="停止生成"
          >
            ■
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="input-bar">
      <div className="input-wrapper">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入消息... (Enter 发送，Shift+Enter 换行)"
          rows={1}
        />
        <button className="send-btn" onClick={handleSend} disabled={!text.trim()}>
          ➤
        </button>
      </div>
    </div>
  )
}
