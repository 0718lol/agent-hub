import React from 'react'
import { useAgentStore } from '../../stores/agentStore'
import { useChatStore } from '../../stores/chatStore'
import CodeCard from './CodeCard'
import MockupCard from './MockupCard'
import ClarificationCard from './ClarificationCard'
import { wsClient } from '../../utils/websocket'

export default function MessageBubble({ message }) {
  const agents = useAgentStore((s) => s.agents)
  const activeId = useChatStore((s) => s.activeConversationId)
  const addMessage = useChatStore((s) => s.addMessage)
  const isUser = message.sender === 'user'
  const agent = agents.find((a) => a.agent_id === message.sender)
  const avatar = isUser ? '👤' : agent?.avatar || '🤖'
  const text = message.content?.text || ''

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
    const parts = t.split(/(```[\s\S]*?```|\[mockup:\w+\]|\[clarify:[^\]]+\])/g)
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
