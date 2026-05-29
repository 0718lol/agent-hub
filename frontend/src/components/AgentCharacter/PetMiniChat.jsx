import React, { useState, useRef, useEffect } from 'react'
import { useChatStore } from '../../stores/chatStore'
import { wsClient } from '../../utils/websocket'

export default function PetMiniChat({ agentId, onClose, onBubble }) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const inputRef = useRef(null)
  const activeId = useChatStore((s) => s.activeConversationId)
  const conversations = useChatStore((s) => s.conversations)
  const addMessage = useChatStore((s) => s.addMessage)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || sending) return
    let convId = activeId
    if (agentId) {
      const conv = conversations.find((c) => c.agentId === agentId && c.type === 'single')
      if (conv) convId = conv.id
    }
    if (!convId) {
      onBubble && onBubble('请先打开一个对话')
      return
    }

    addMessage(convId, {
      sender: 'user',
      content: { text: trimmed },
      streaming: false,
    })

    // 用 sendTo 保证目标会话已连接，且消息能送达（不会因 disconnect 丢失）
    wsClient.sendTo(convId, {
      type: 'message',
      conversation_id: convId,
      sender: 'user',
      content: { text: trimmed, target_agent: agentId || undefined },
    })
    setSending(true)
    onBubble && onBubble('已发送，等回复中...')
    setText('')
    setTimeout(() => {
      setSending(false)
      onClose && onClose()
    }, 400)
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    } else if (e.key === 'Escape') {
      onClose && onClose()
    }
  }

  return (
    <div className="pet-mini-chat" onPointerDown={(e) => e.stopPropagation()}>
      <div className="pet-mini-chat-header">
        <span>💬 快速对话</span>
        <button className="pet-mini-chat-close" onClick={onClose}>×</button>
      </div>
      <textarea
        ref={inputRef}
        className="pet-mini-chat-input"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKey}
        placeholder="对它说点什么... (Enter 发送)"
        rows={3}
        disabled={sending}
      />
      <div className="pet-mini-chat-actions">
        <span className="pet-mini-chat-hint">→ 发到当前对话</span>
        <button
          className="pet-mini-chat-send"
          onClick={handleSend}
          disabled={!text.trim() || sending}
        >
          {sending ? '...' : '发送 ↩'}
        </button>
      </div>
    </div>
  )
}
