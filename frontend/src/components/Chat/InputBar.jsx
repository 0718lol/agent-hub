import React, { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Square, AtSign, Plus, Mic, Image, Paperclip } from 'lucide-react'
import { useAgentStore } from '../../stores/agentStore'
import AgentSelector from './AgentSelector'
import FileUploader from './FileUploader'

export default function InputBar({ onSend, isGenerating, onStop, isGroup }) {
  const [text, setText] = useState('')
  const [mentionedAgents, setMentionedAgents] = useState([])
  const [showSelector, setShowSelector] = useState(false)
  const [showPlusMenu, setShowPlusMenu] = useState(false)
  const [showFileUploader, setShowFileUploader] = useState(false)
  const [menuPos, setMenuPos] = useState({ bottom: 0, left: 0 })
  const [attachments, setAttachments] = useState([])
  const [uploading, setUploading] = useState(false)
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)
  const plusBtnRef = useRef(null)

  // Auto-resize textarea: grow with content, cap at 120px then scroll
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
    el.style.overflowY = el.scrollHeight > 120 ? 'auto' : 'hidden'
  }, [text])

  const handleSend = () => {
    if ((!text.trim() && attachments.length === 0) || isGenerating) return
    onSend(text.trim(), mentionedAgents, attachments)
    setText('')
    setMentionedAgents([])
    setAttachments([])
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleChange = (e) => {
    const val = e.target.value
    setText(val)
    if (isGroup && val.endsWith('@')) {
      setShowSelector(true)
    }
  }

  const handleToggleAgent = (agentId) => {
    setMentionedAgents((prev) =>
      prev.includes(agentId) ? prev.filter((id) => id !== agentId) : [...prev, agentId]
    )
  }

  const removeMention = (agentId) => {
    setMentionedAgents((prev) => prev.filter((id) => id !== agentId))
  }

  const handleFileUploaded = useCallback((result) => {
    setAttachments((prev) => [...prev, result])
    setShowFileUploader(false)
  }, [])

  const handleFileSelect = useCallback(async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setShowPlusMenu(false)
    setUploading(true)

    try {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await fetch('/api/upload', { method: 'POST', body: formData })
      const data = await resp.json()
      if (data.status === 'uploaded') {
        setAttachments((prev) => [...prev, data])
      }
    } catch {
      // 上传失败时回退为文本标记
      const isImage = file.type.startsWith('image/')
      const prefix = isImage ? '[图片: ' : '[文件: '
      setText((prev) => prev + (prev ? ' ' : '') + prefix + file.name + ']')
    }

    setUploading(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [])

  if (isGenerating) {
    return (
      <div className="input-bar">
        <div className="coze-input" style={{ borderColor: 'var(--red)', opacity: 0.6 }}>
          <textarea value="" readOnly placeholder="Agent 正在回复..." rows={1} style={{ opacity: 0.5, cursor: 'not-allowed' }} />
          <div className="coze-input-toolbar">
            <div className="coze-input-left">
              <button className="coze-toolbar-btn" disabled><Paperclip size={18} /></button>
              <button className="coze-toolbar-btn" disabled><Plus size={18} /></button>
              <span className="coze-input-divider" />
              <button className="coze-toolbar-btn" disabled><AtSign size={18} /></button>
            </div>
            <button className="stop-btn" onClick={onStop} title="停止生成">
              <Square size={14} fill="currentColor" />
            </button>
          </div>
        </div>
      </div>
    )
  }

  const hasContent = text.trim().length > 0 || attachments.length > 0

  return (
    <div className="input-bar">
      <div className="coze-input">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder="发消息..."
          rows={1}
        />

        {/* Mentioned tags + Attachment tags */}
        {(mentionedAgents.length > 0 || attachments.length > 0) && (
          <div style={{ display: 'flex', gap: 4, padding: '0 var(--space-3) 4px', flexWrap: 'wrap', alignItems: 'center' }}>
            {attachments.map((att) => (
              <span key={att.stored_name} className="at-tag" style={{ background: 'var(--bg-secondary)', color: 'var(--text-primary)' }}>
                {att.is_image ? '🖼 ' : '📎 '}{att.original_name}
                <button onClick={() => setAttachments((prev) => prev.filter((a) => a.stored_name !== att.stored_name))}>&times;</button>
              </span>
            ))}
            {mentionedAgents.map((id) => {
              const agent = useAgentStore.getState().agents.find((a) => a.agent_id === id)
              return (
                <span key={id} className="at-tag">
                  @{agent?.name || id}
                  <button onClick={() => removeMention(id)}>&times;</button>
                </span>
              )
            })}
          </div>
        )}

        {/* 上传中指示 */}
        {uploading && (
          <div style={{ padding: '0 var(--space-4) 4px', fontSize: 'var(--text-xs)', color: 'var(--accent)' }}>
            正在上传文件...
          </div>
        )}

        {/* Bottom toolbar */}
        <div className="coze-input-toolbar">
          <div className="coze-input-left">
            <button
              className="coze-toolbar-btn"
              onClick={() => setShowFileUploader(true)}
              title="上传附件"
            >
              <Paperclip size={18} />
            </button>
            <button
              ref={plusBtnRef}
              className="coze-toolbar-btn"
              onClick={(e) => {
                e.stopPropagation()
                const rect = e.currentTarget.getBoundingClientRect()
                setMenuPos({
                  bottom: window.innerHeight - rect.top + 8,
                  left: rect.left - 8,
                })
                setShowPlusMenu(!showPlusMenu)
              }}
              title="添加"
            >
              <Plus size={18} />
            </button>

            <span className="coze-input-divider" />
            <button
              className="coze-toolbar-btn"
              onClick={() => setShowSelector(!showSelector)}
              title="@ 指定 Agent"
              style={{ color: mentionedAgents.length > 0 ? 'var(--accent)' : undefined }}
            >
              <AtSign size={18} />
            </button>
          </div>
          <button className="coze-send-btn" onClick={handleSend} disabled={!hasContent}>
            {hasContent ? <Send size={16} /> : <Mic size={16} />}
          </button>
        </div>
      </div>

      {showSelector && (
        <AgentSelector
          multiSelect
          selected={mentionedAgents}
          onToggle={handleToggleAgent}
          onClose={() => setShowSelector(false)}
          onSelect={() => {}}
        />
      )}

      {/* 文件上传浮窗 — 移出 coze-input 避免 overflow:hidden 裁切 */}
      {showPlusMenu && (
        <>
          <div className="plus-menu-backdrop" onClick={() => setShowPlusMenu(false)} />
          <div
            className="plus-menu"
            style={{ bottom: menuPos.bottom, left: menuPos.left, position: 'fixed', top: 'auto' }}
          >
            <button className="plus-menu-item" onClick={() => fileInputRef.current?.click()}>
              <div className="plus-menu-icon">
                <Image size={20} />
              </div>
              <div className="plus-menu-text">
                <div className="plus-menu-title">上传本地文件或图片</div>
                <div className="plus-menu-desc">支持图片、文档等文件格式</div>
              </div>
            </button>
          </div>
        </>
      )}

      {/* 附件上传弹窗 */}
      {showFileUploader && (
        <FileUploader
          onUploaded={handleFileUploaded}
          onClose={() => setShowFileUploader(false)}
        />
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,.pdf,.doc,.docx,.txt,.md,.json,.csv,.xlsx"
        onChange={handleFileSelect}
        style={{ display: 'none' }}
      />
    </div>
  )
}
