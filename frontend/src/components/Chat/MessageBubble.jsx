import React from 'react'
import { useAgentStore } from '../../stores/agentStore'
import CodeCard from './CodeCard'
import MockupCard from './MockupCard'

export default function MessageBubble({ message }) {
  const agents = useAgentStore((s) => s.agents)
  const isUser = message.sender === 'user'
  const agent = agents.find((a) => a.agent_id === message.sender)
  const avatar = isUser ? '👤' : agent?.avatar || '🤖'
  const text = message.content?.text || ''

  const renderText = (t) => {
    const parts = t.split(/(```[\s\S]*?```|\[mockup:\w+\])/g)
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
