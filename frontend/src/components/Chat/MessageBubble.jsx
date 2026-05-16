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
  const isUser = message.sender === 'user'
  const agent = agents.find((a) => a.agent_id === message.sender)
  const avatar = isUser ? '👤' : agent?.avatar || '🤖'
  const text = message.content?.text || ''
  const setPreviewHtml = useCanvasStore((s) => s.setPreviewHtml)
  const previewHandled = useRef(false)

  useEffect(() => {
    if (!message.streaming && !previewHandled.current) {
      const m = text.match(/\[preview:(\w+)\]/)
      if (m && PREVIEW_HTML[m[1]]) {
        previewHandled.current = true
        setPreviewHtml(PREVIEW_HTML[m[1]])
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

  const renderText = (t) => {
    const parts = t.split(/(```[\s\S]*?```|\[mockup:\w+\]|\[preview:\w+\]|\[clarify:[^\]]+\])/g)
    return parts.map((part, i) => {
      if (part.startsWith('```')) {
        const match = part.match(/```(\w*)\n([\s\S]*?)```/)
        if (match) {
          return <CodeCard key={i} language={match[1] || 'text'} code={match[2]} />
        }
      }
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
      const clarifyMatch = part.match(/\[clarify:([^\]]+)\]/)
      if (clarifyMatch) {
        const questions = clarifyMatch[1].split('|')
        return <ClarificationCard key={i} questions={questions} onSubmit={handleClarifySubmit} />
      }
      return <span key={i}>{part}</span>
    })
  }

  return (
    <div className={`message-row ${isUser ? 'user' : ''}`}>
      <div className="msg-avatar">{avatar}</div>
      <div className="message-bubble">
        {renderText(text)}
        {message.streaming && <span className="streaming-cursor" />}
      </div>
    </div>
  )
}
