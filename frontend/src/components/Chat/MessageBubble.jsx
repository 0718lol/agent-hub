import React, { useEffect, useRef } from 'react'
import { useAgentStore } from '../../stores/agentStore'
import { useChatStore } from '../../stores/chatStore'
import { useCanvasStore } from '../../stores/canvasStore'
import CodeCard from './CodeCard'
import MockupCard from './MockupCard'
import ClarificationCard from './ClarificationCard'
import { PREVIEW_HTML } from '../Canvas/previewHtml'
import { wsClient } from '../../utils/websocket'

export default function MessageBubble({ message }) {
  const agents = useAgentStore((s) => s.agents)
  const activeId = useChatStore((s) => s.activeConversationId)
  const addMessage = useChatStore((s) => s.addMessage)
  const allRead = useChatStore((s) => s.allRead)
  const isUser = message.sender === 'user'
  const agent = agents.find((a) => a.agent_id === message.sender)
  const avatar = isUser ? '👤' : agent?.avatar || '🤖'
  const text = message.content?.text || ''
  const setPreviewHtml = useCanvasStore((s) => s.setPreviewHtml)
  const setGeneratedCode = useCanvasStore((s) => s.setGeneratedCode)
  const previewHandled = useRef(false)

  useEffect(() => {
    if (!message.streaming && !previewHandled.current) {
      const m = text.match(/\[preview:(\w+)\]/)
      if (m && PREVIEW_HTML[m[1]]) {
        previewHandled.current = true
        setPreviewHtml(PREVIEW_HTML[m[1]])
        setGeneratedCode('html', PREVIEW_HTML[m[1]])
      } else {
        const codeMatch = text.match(/```(\w*)\n([\s\S]*?)```/)
        if (codeMatch) {
          previewHandled.current = true
          const lang = codeMatch[1] || 'text'
          const code = codeMatch[2]
          setGeneratedCode(lang, code)
          if (lang === 'html') {
            setPreviewHtml(code)
          }
        }
      }
    }
  }, [message.streaming, text])

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
      content: {
        text: `[clarified] ${answerText}`,
        target_agent: 'agent_pm',
      },
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
    // Strip thinking tags
    let clean = t.replace(/\[thinking\][\s\S]*?\[\/thinking\]/g, '')
    // Strip code blocks (code is sent to canvas panel)
    if (clean.match(/```[\s\S]*?```/)) {
      clean = clean.replace(/```[\s\S]*?```/g, '\n[code_generated]\n')
    }
    // Strip assign tags
    clean = clean.replace(/\[assign:\w+\]/g, '')
    clean = clean.trim()

    if (!clean) return null

    const parts = clean.split(/(\[mockup:\w+\]|\[preview:\w+\]|\[clarify:[^\]]+\]|\[options:[^\]]+\]|\[code_generated\])/g)
    return parts.map((part, i) => {
      if (!part) return null
      const mockupMatch = part.match(/\[mockup:(\w+)\]/)
      if (mockupMatch) {
        return <MockupCard key={i} type={mockupMatch[1]} />
      }
      const previewMatch = part.match(/\[preview:(\w+)\]/)
      if (previewMatch) {
        return (
          <div key={i} style={{
            margin: '8px 0', padding: '10px 14px',
            background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.2)',
            borderRadius: 8, fontSize: 13, color: '#10b981',
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            ↗ 预览已更新到右侧面板
          </div>
        )
      }
      if (part === '[code_generated]') {
        return (
          <div key={i} style={{
            margin: '8px 0', padding: '10px 14px',
            background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.2)',
            borderRadius: 8, fontSize: 13, color: '#3b82f6',
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            ↗ 代码已更新到右侧面板
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
          <div key={i} style={{ display: 'flex', flexWrap: 'wrap', gap: 8, margin: '8px 0' }}>
            {options.map((opt, j) => (
              <button
                key={j}
                onClick={() => handleOptionClick(opt)}
                style={{
                  padding: '8px 16px', borderRadius: 20,
                  background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.3)',
                  color: '#818cf8', fontSize: 13, cursor: 'pointer',
                  transition: 'all 0.2s',
                }}
                onMouseOver={(e) => { e.target.style.background = 'rgba(99,102,241,0.2)' }}
                onMouseOut={(e) => { e.target.style.background = 'rgba(99,102,241,0.1)' }}
              >
                {opt}
              </button>
            ))}
          </div>
        )
      }
      return <span key={i}>{part}</span>
    })
  }

  const isRead = allRead[activeId]

  return (
    <div className={`message-row ${isUser ? 'user' : ''}`}>
      <div className="msg-avatar">{avatar}</div>
      <div className="message-bubble">
        {renderText(text)}
        {message.streaming && <span className="streaming-cursor" />}
        {isUser && !message.streaming && (
          <div className="read-status">
            {isRead ? (
              <span className="read-check read">✓✓</span>
            ) : (
              <span className="read-check">✓</span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
