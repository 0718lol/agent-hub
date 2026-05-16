import React, { useRef, useEffect } from 'react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { useCanvasStore } from '../../stores/canvasStore'
import MessageBubble from '../Chat/MessageBubble'
import InputBar from '../Chat/InputBar'
import { wsClient } from '../../utils/websocket'

export default function ChatPanel() {
  const activeId = useChatStore((s) => s.activeConversationId)
  const conversations = useChatStore((s) => s.conversations)
  const addMessage = useChatStore((s) => s.addMessage)
  const updateLastAgentMessage = useChatStore((s) => s.updateLastAgentMessage)
  const loadMessages = useChatStore((s) => s.loadMessages)
  const setAgentStatus = useAgentStore((s) => s.setAgentStatus)
  const setTyping = useChatStore((s) => s.setTyping)
  const setThinking = useChatStore((s) => s.setThinking)
  const setGenerating = useChatStore((s) => s.setGenerating)
  const generatingConvs = useChatStore((s) => s.generatingConvs)
  const markRead = useChatStore((s) => s.markRead)
  const typingAgents = useChatStore((s) => s.typingAgents)
  const thinkingAgents = useChatStore((s) => s.thinkingAgents)
  const messagesRef = useRef(null)

  const conv = conversations.find((c) => c.id === activeId)
  const setGeneratedCode = useCanvasStore((s) => s.setGeneratedCode)
  const typingSet = typingAgents[activeId] || new Set()
  const typingAgentIds = [...typingSet]
  const thinkingMap = thinkingAgents[activeId] || {}
  const thinkingEntries = Object.entries(thinkingMap)
  const isGenerating = generatingConvs.has(activeId)

  useEffect(() => {
    loadMessages(activeId)
  }, [activeId])

  // Send read receipt when conversation opens
  useEffect(() => {
    markRead(activeId)
    wsClient.send({ type: 'read', conversation_id: activeId, sender: 'user' })
  }, [activeId])

  useEffect(() => {
    wsClient.connect(activeId)

    const unsub = wsClient.onMessage((data) => {
      if (data.conversation_id !== activeId) return

      if (data.type === 'typing') {
        setTyping(activeId, data.agent_id, data.is_typing)
        return
      }

      if (data.type === 'thinking') {
        setThinking(activeId, data.agent_id, data.text)
        return
      }

      if (data.type === 'code') {
        setGeneratedCode(data.language, data.code)
        return
      }

      if (data.type === 'generating') {
        setGenerating(activeId, data.is_generating)
        return
      }

      if (data.type === 'read') {
        markRead(activeId)
        return
      }

      if (data.type === 'message') {
        const isStreaming = data.stream

        if (isStreaming) {
          const convNow = useChatStore.getState().conversations.find((c) => c.id === activeId)
          const msgs = convNow?.messages || []
          const last = msgs[msgs.length - 1]

          if (last && last.sender === data.sender && last.streaming) {
            updateLastAgentMessage(activeId, data.sender, data.content.text, true)
          } else {
            addMessage(activeId, {
              sender: data.sender,
              content: data.content,
              streaming: true,
            })
          }
          setAgentStatus(data.sender, 'working')
        } else {
          updateLastAgentMessage(activeId, data.sender, data.content.text, false)
          setAgentStatus(data.sender, 'done')
          setTimeout(() => setAgentStatus(data.sender, 'idle'), 2000)
        }
      }
    })

    return () => {
      unsub()
      wsClient.disconnect()
    }
  }, [activeId])

  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight
    }
  }, [conv?.messages])

  const handleSend = (text) => {
    addMessage(activeId, {
      sender: 'user',
      content: { text },
      streaming: false,
    })

    const targetAgent = conv?.type === 'single' ? conv.agentId : undefined
    wsClient.send({
      type: 'message',
      conversation_id: activeId,
      sender: 'user',
      content: { text, target_agent: targetAgent },
    })
  }

  const handleStop = () => {
    wsClient.send({ type: 'stop', conversation_id: activeId })
  }

  if (!conv) return <div className="chat-panel"><div className="empty-state"><div className="icon">💬</div><div className="text">选择一个会话开始</div></div></div>

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <div className="avatar">{conv.avatar}</div>
        <div>
          <div className="title">{conv.name}</div>
          <div className="subtitle">
            {typingAgentIds.length > 0
              ? typingAgentIds.length === 1
                ? `${useAgentStore.getState().agents.find(a => a.agent_id === typingAgentIds[0])?.name || typingAgentIds[0]} 正在输入...`
                : `${typingAgentIds.length}人正在输入...`
              : conv.type === 'group' ? `${conv.agents?.length || 0} 个 Agent` : ''
            }
          </div>
        </div>
      </div>

      <div className="chat-messages" ref={messagesRef}>
        {conv.messages.length === 0 && (
          <div className="empty-state">
            <div className="icon">{conv.avatar}</div>
            <div className="text">发送消息开始对话</div>
          </div>
        )}
        {conv.messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {/* Typing indicator bubble */}
        {typingAgentIds.length > 0 && (
          <div className="message-row">
            <div className="msg-avatar" style={{ position: 'relative' }}>
              {typingAgentIds.slice(0, 3).map((id, i) => {
                const agent = useAgentStore.getState().agents.find(a => a.agent_id === id)
                return (
                  <span key={id} style={{
                    position: i === 0 ? 'relative' : 'absolute',
                    left: i > 0 ? `${-8 * i}px` : undefined,
                    fontSize: i > 0 ? '12px' : undefined,
                  }}>{agent?.avatar || '🤖'}</span>
                )
              })}
            </div>
            <div className="message-bubble typing-bubble">
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
              {typingAgentIds.length > 1 && (
                <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 6 }}>
                  {typingAgentIds.length}人
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Thinking bubbles */}
      {thinkingEntries.length > 0 && (
        <div style={{ padding: '8px 24px 0', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {thinkingEntries.map(([agentId, text]) => {
            const agent = useAgentStore.getState().agents.find(a => a.agent_id === agentId)
            return (
              <div key={agentId} style={{
                display: 'flex', alignItems: 'flex-start', gap: 10,
                padding: '10px 14px', borderRadius: 12,
                background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.15)',
              }}>
                <span style={{ fontSize: 18, flexShrink: 0 }}>{agent?.avatar || '🤖'}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, color: '#6366f1', fontWeight: 600, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span className="thinking-spinner" />
                    {agent?.name || agentId} 正在思考...
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5, wordBreak: 'break-word' }}>
                    {text}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      <InputBar onSend={handleSend} isGenerating={isGenerating} onStop={handleStop} />
    </div>
  )
}
