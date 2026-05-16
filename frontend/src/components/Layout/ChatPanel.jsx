import React, { useRef, useEffect } from 'react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
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
  const markRead = useChatStore((s) => s.markRead)
  const typingAgents = useChatStore((s) => s.typingAgents)
  const messagesRef = useRef(null)

  const conv = conversations.find((c) => c.id === activeId)
  const typingSet = typingAgents[activeId] || new Set()
  const typingAgentIds = [...typingSet]

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

  if (!conv) return <div className="chat-panel"><div className="empty-state"><div className="icon">💬</div><div className="text">选择一个会话开始</div></div></div>

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <div className="avatar">{conv.avatar}</div>
        <div>
          <div className="title">{conv.name}</div>
          <div className="subtitle">
            {typingAgentIds.length > 0
              ? `${typingAgentIds.map(id => {
                  const a = useAgentStore.getState().agents.find(ag => ag.agent_id === id)
                  return a?.name || id
                }).join('、')} 正在输入...`
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
            <div className="msg-avatar">
              {useAgentStore.getState().agents.find(a => a.agent_id === typingAgentIds[0])?.avatar || '🤖'}
            </div>
            <div className="message-bubble typing-bubble">
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
            </div>
          </div>
        )}
      </div>

      <InputBar onSend={handleSend} />
    </div>
  )
}
