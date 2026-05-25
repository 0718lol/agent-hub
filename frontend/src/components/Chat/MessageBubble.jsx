import React, { useState } from 'react'
import { Copy, RefreshCw, Reply, Pin, Check } from 'lucide-react'
import { useAgentStore } from '../../stores/agentStore'
import { useChatStore } from '../../stores/chatStore'
import { useCanvasStore } from '../../stores/canvasStore'
import CodeCard from './CodeCard'
import MockupCard from './MockupCard'
import ClarificationCard from './ClarificationCard'
import FileAttachmentCard from './FileAttachmentCard'
import { PREVIEW_HTML } from '../Canvas/previewHtml'
import { wsClient } from '../../utils/websocket'
import IconAvatar from '../IconAvatar'

export default function MessageBubble({ message, isPinned }) {
  const agents = useAgentStore((s) => s.agents)
  const activeId = useChatStore((s) => s.activeConversationId)
  const addMessage = useChatStore((s) => s.addMessage)
  const allRead = useChatStore((s) => s.allRead)
  const togglePinMessage = useChatStore((s) => s.togglePinMessage)
  const setPreviewHtml = useCanvasStore((s) => s.setPreviewHtml)
  const setGeneratedCode = useCanvasStore((s) => s.setGeneratedCode)

  const isUser = message.sender === 'user'
  const agent = agents.find((a) => a.agent_id === message.sender)
  const text = message.content?.text || ''
  const attachments = message.content?.attachments || []
  const isRead = allRead[activeId]
  const [copied, setCopied] = useState(false)

  const timeStr = message.timestamp
    ? new Date(message.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    : ''

  const handleCopy = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleRegenerate = () => {
    wsClient.send({
      type: 'message',
      conversation_id: activeId,
      sender: 'user',
      content: { text: '请重新生成', regenerate: true, original_message_id: message.id },
    })
  }

  const handleReply = () => {
    addMessage(activeId, {
      sender: 'user',
      content: { text: `> ${text.slice(0, 80)}${text.length > 80 ? '...' : ''}\n\n` },
      streaming: false,
    })
  }

  const handleClarifySubmit = (qaList) => {
    const answerText = qaList.map((qa) => `**${qa.question}**\n${qa.answer}`).join('\n\n')
    addMessage(activeId, {
      sender: 'user',
      content: { text: `需求澄清回答：\n\n${answerText}` },
      streaming: false,
    })
    wsClient.send({
      type: 'message',
      conversation_id: activeId,
      sender: 'user',
      content: { text: `[clarified] ${answerText}`, target_agent: 'agent_pm' },
    })
  }

  const handleOptionClick = (option) => {
    addMessage(activeId, {
      sender: 'user',
      content: { text: option },
      streaming: false,
    })
    wsClient.send({
      type: 'message',
      conversation_id: activeId,
      sender: 'user',
      content: { text: option },
    })
  }

  const renderText = (t) => {
    let clean = t.replace(/\[thinking\][\s\S]*?\[\/thinking\]/g, '')
    clean = clean.replace(/\[assign:\w+\]/g, '')
    clean = clean.trim()

    if (!clean) return null

    const parts = clean.split(/(\[mockup:\w+\]|\[preview:\w+\]|\[clarify:[^\]]+\]|\[options:[^\]]+\]|```[\s\S]*?```)/g)
    return parts.map((part, i) => {
      if (!part) return null

      const mockupMatch = part.match(/\[mockup:(\w+)\]/)
      if (mockupMatch) return <MockupCard key={i} type={mockupMatch[1]} />

      const previewMatch = part.match(/\[preview:(\w+)\]/)
      if (previewMatch) {
        return (
          <div key={i} style={{
            margin: '8px 0', padding: '8px 12px',
            background: 'var(--accent-bg)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)', fontSize: 'var(--text-xs)', color: 'var(--accent)',
            display: 'flex', alignItems: 'center', gap: 6, opacity: 0.8,
          }}>
            预览已更新到右侧面板
          </div>
        )
      }

      const clarifyMatch = part.match(/\[clarify:([^\]]+)\]/)
      if (clarifyMatch) {
        const questions = clarifyMatch[1].split('|')
        return <ClarificationCard key={i} questions={questions} onSubmit={handleClarifySubmit} />
      }

      const optionsMatch = part.match(/\[options:([^\]]+)\]/)
      if (optionsMatch) {
        const options = optionsMatch[1].split('|')
        return (
          <div key={i} style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '8px 0' }}>
            {options.map((opt, j) => (
              <button key={j} onClick={() => handleOptionClick(opt)} style={{
                padding: '6px 14px', borderRadius: 'var(--radius-full)',
                background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                color: 'var(--text-primary)', fontSize: 'var(--text-xs)', cursor: 'pointer',
              }}>
                {opt}
              </button>
            ))}
          </div>
        )
      }

      const codeMatch = part.match(/```(\w*)\n([\s\S]*?)```/)
      if (codeMatch) {
        const lang = codeMatch[1] || 'text'
        const code = codeMatch[2]
        return (
          <div key={i} className="code-block">
            <div className="code-block-header">
              <span>{lang}</span>
              <button onClick={() => navigator.clipboard.writeText(code)}>
                <Copy size={12} />
              </button>
            </div>
            <pre><code>{code}</code></pre>
          </div>
        )
      }

      return <span key={i}>{part}</span>
    })
  }

  return (
    <div className={`message-row ${isUser ? 'user' : ''}`}>
      {!isUser && (
        <div className="msg-avatar">
          <IconAvatar agentId={message.sender} size={16} />
        </div>
      )}

      <div className="message-content">
        {/* Pin indicator */}
        {isPinned && (
          <div style={{ fontSize: 11, color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 4, marginBottom: 2 }}>
            <Pin size={10} /> 已固定
          </div>
        )}

        {/* 附件预览 */}
        {attachments.length > 0 && (
          <div style={{
            display: 'flex', flexDirection: 'column', gap: 6,
            marginBottom: text ? 8 : 0,
          }}>
            {attachments.map((att, i) => (
              <FileAttachmentCard key={i} attachment={att} />
            ))}
          </div>
        )}

        {isUser ? (
          <div className="message-bubble-user">{renderText(text)}</div>
        ) : (
          <div className="message-bubble-agent">
            {renderText(text)}
            {message.streaming && <span className="streaming-cursor" />}
          </div>
        )}

        {/* Meta + Actions */}
        <div className="message-meta">
          <span className="time">{timeStr}</span>
          {isUser && !message.streaming && (
            <span className={`read-check ${isRead ? 'read' : ''}`}>
              <Check size={10} strokeWidth={3} />
            </span>
          )}
          <div className="message-actions">
            <button onClick={handleReply} title="回复"><Reply size={14} /></button>
            <button onClick={handleCopy} title="复制">{copied ? <Check size={14} /> : <Copy size={14} />}</button>
            {!isUser && !message.streaming && (
              <button onClick={handleRegenerate} title="重新生成"><RefreshCw size={14} /></button>
            )}
            <button onClick={() => togglePinMessage(activeId, message.id)} title="固定消息">
              <Pin size={14} color={isPinned ? 'var(--accent)' : undefined} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
