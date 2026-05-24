import React, { useState, useRef, useEffect } from 'react'
import { Send, Square, AtSign, Plus } from 'lucide-react'
import { useAgentStore } from '../../stores/agentStore'
import AgentSelector from './AgentSelector'

export default function InputBar({ onSend, isGenerating, onStop, isGroup }) {
  const [text, setText] = useState('')
  const [mentionedAgents, setMentionedAgents] = useState([])
  const [showSelector, setShowSelector] = useState(false)
  const textareaRef = useRef(null)

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
    el.style.overflowY = el.scrollHeight > 120 ? 'auto' : 'hidden'
  }, [text])

  const handleSend = () => {
    if (!text.trim() || isGenerating) return
    onSend(text.trim(), mentionedAgents)
    setText('')
    setMentionedAgents([])
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

  if (isGenerating) {
    return (
      <div className="input-bar">
        <div className="input-wrapper" style={{ borderColor: 'var(--red)', opacity: 0.6 }}>
          <textarea value="" readOnly placeholder="Agent 正在回复..." rows={1} style={{ opacity: 0.5, cursor: 'not-allowed', minHeight: 48 }} />
          <button className="stop-btn" onClick={onStop} title="停止生成">
            <Square size={14} fill="currentColor" />
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="input-bar">
      <div className="input-wrapper">
        {isGroup && (
          <button
            className="input-btn"
            onClick={() => setShowSelector(!showSelector)}
            title="@ 指定 Agent"
            style={{ color: mentionedAgents.length > 0 ? 'var(--accent)' : undefined }}
          >
            <AtSign size={18} />
          </button>
        )}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={isGroup ? '@ 指定 Agent 或输入消息...' : '输入消息...'}
          rows={1}
        />
        <button className="send-btn" onClick={handleSend} disabled={!text.trim()}>
          <Send size={16} />
        </button>
      </div>

      {/* Bottom toolbar */}
      <div className="input-toolbar">
        <button className="input-toolbar-btn" title="上传文件（即将支持）">
          <Plus size={18} />
        </button>
      </div>

      {/* Mentioned tags */}
      {mentionedAgents.length > 0 && (
        <div style={{ display: 'flex', gap: 4, marginTop: 6, flexWrap: 'wrap' }}>
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

      {showSelector && (
        <AgentSelector
          multiSelect
          selected={mentionedAgents}
          onToggle={handleToggleAgent}
          onClose={() => setShowSelector(false)}
          onSelect={() => {}}
        />
      )}
    </div>
  )
}
