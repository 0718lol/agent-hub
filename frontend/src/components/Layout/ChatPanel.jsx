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
  const setAgentStatus = useAgentStore((s) => s.setAgentStatus)
  const messagesRef = useRef(null)

  const conv = conversations.find((c) => c.id === activeId)

  useEffect(() => {
    wsClient.connect(activeId)

    const unsub = wsClient.onMessage((data) => {
      if (data.type === 'message' && data.conversation_id === activeId) {
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
          <div className="subtitle">{conv.type === 'group' ? `${conv.agents?.length || 0} 个 Agent` : conv.agentId}</div>
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
      </div>

      <InputBar onSend={handleSend} />
    </div>
  )
}
