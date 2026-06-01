import React, { useState, useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import { Check, Reply, Copy, RefreshCw, Pin } from 'lucide-react'
import { useAgentStore } from '../../stores/agentStore'
import { useChatStore } from '../../stores/chatStore'
import { useCanvasStore } from '../../stores/canvasStore'
import CodeCard from './CodeCard'
import MockupCard from './MockupCard'
import ClarificationCard from './ClarificationCard'
import AskUserCard from './AskUserCard'
import FileAttachmentCard from './FileAttachmentCard'
import IconAvatar from '../IconAvatar'
import { PREVIEW_HTML } from '../Canvas/previewHtml'
import { wsClient } from '../../utils/websocket'

const MD_COMPONENTS = {
  p: ({ children }) => <div style={{ margin: '0.2em 0', lineHeight: 1.55 }}>{children}</div>,
  ul: ({ children }) => <ul style={{ margin: '0.3em 0', paddingLeft: 20 }}>{children}</ul>,
  ol: ({ children }) => <ol style={{ margin: '0.3em 0', paddingLeft: 22 }}>{children}</ol>,
  li: ({ children }) => <li style={{ margin: '0.1em 0', lineHeight: 1.5 }}>{children}</li>,
  h1: ({ children }) => <div style={{ fontSize: 16, margin: '0.45em 0 0.25em', fontWeight: 700 }}>{children}</div>,
  h2: ({ children }) => <div style={{ fontSize: 15, margin: '0.45em 0 0.25em', fontWeight: 700 }}>{children}</div>,
  h3: ({ children }) => <div style={{ fontSize: 14, margin: '0.4em 0 0.2em', fontWeight: 600 }}>{children}</div>,
  strong: ({ children }) => <strong style={{ fontWeight: 700, color: '#f8fafc' }}>{children}</strong>,
  em: ({ children }) => <em style={{ fontStyle: 'italic' }}>{children}</em>,
  code: ({ children }) => (
    <code style={{
      background: 'rgba(99,102,241,0.16)', color: '#a5b4fc',
      padding: '1px 6px', borderRadius: 4,
      fontSize: '0.9em', fontFamily: 'Consolas, Monaco, monospace',
    }}>{children}</code>
  ),
  blockquote: ({ children }) => (
    <blockquote style={{
      borderLeft: '3px solid rgba(99,102,241,0.45)',
      paddingLeft: 10, margin: '0.45em 0',
      color: '#94a3b8',
    }}>{children}</blockquote>
  ),
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" style={{ color: '#a5b4fc', textDecoration: 'underline' }}>{children}</a>
  ),
  hr: () => <hr style={{ border: 'none', borderTop: '1px solid rgba(255,255,255,0.08)', margin: '0.6em 0' }} />,
}

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

  const handleAskUserReply = (answer) => {
    addMessage(activeId, {
      sender: 'user',
      content: { text: answer },
      streaming: false,
    })
    wsClient.send({
      type: 'message',
      conversation_id: activeId,
      sender: 'user',
      content: {
        text: `[ask_user_reply] ${answer}`,
        target_agent: message.sender,
      },
    })
  }

  const renderText = (t) => {
    let clean = t.replace(/\[thinking\][\s\S]*?\[\/thinking\]/g, '')
    clean = clean.replace(/\[assign:\w+\]/g, '')
    clean = clean.trim()

    if (!clean) return null

    const parts = clean.split(/(\[mockup:\w+\]|\[preview:\w+\]|\[clarify:[^\]]+\]|\[ask_user:[^\]]+\]|\[options:[^\]]+\]|```[\s\S]*?```)/g)
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

      const askUserMatch = part.match(/\[ask_user:([^\]]+)\]/)
      if (askUserMatch) {
        const raw = askUserMatch[1]
        const segments = raw.split('|').map((s) => s.trim()).filter(Boolean)
        const question = segments[0] || ''
        const options = segments.slice(1, 5).map((seg) => {
          const [labelRaw, ...descParts] = seg.split('::')
          let label = labelRaw.trim()
          let recommended = false
          if (label.startsWith('*')) {
            recommended = true
            label = label.slice(1).trim()
          }
          const description = descParts.join('::').trim()
          return { label, description, recommended }
        })
        return (
          <AskUserCard
            key={i}
            question={question}
            options={options}
            onAnswer={handleAskUserReply}
          />
        )
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
      return <ReactMarkdown key={i} components={MD_COMPONENTS}>{part}</ReactMarkdown>
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
