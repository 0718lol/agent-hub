import React, { useRef, useEffect, useCallback, memo, useMemo, useState } from 'react'
import { ChevronUp, MessageSquare } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { useCanvasStore } from '../../stores/canvasStore'
import MessageBubble from '../Chat/MessageBubble'
import InputBar from '../Chat/InputBar'
import InlineDeployCard from '../Chat/InlineDeployCard'
import DeployProgressCard from '../Chat/DeployProgressCard'
import IconAvatar from '../IconAvatar'
import { wsClient } from '../../utils/websocket'
import { isInternalNoiseMessage } from '../../utils/internalMessages'
import GoalSnapshot from '../Chat/GoalSnapshot'

// 全局消息加载缓存：已加载过的 convId 不重复请求（上限 200 防止内存膨胀）
const LOADED_CONVS_MAX = 200
const loadedConvs = new Set()

// 全局滚动位置缓存
const scrollPositions = {}

const ChatPanelContent = memo(function ChatPanelContent({ convId, isActive, readiness }) {
  const conv = useChatStore((s) => s.conversations.find((c) => c.id === convId))
  const addMessage = useChatStore((s) => s.addMessage)
  const initializeGoal = useChatStore((s) => s.initializeGoal)
  const loadMessages = useChatStore((s) => s.loadMessages)
  const loadOlderMessages = useChatStore((s) => s.loadOlderMessages)
  const pruneInternalMessages = useChatStore((s) => s.pruneInternalMessages)
  const hasOlderMessages = useChatStore((s) => s.hasOlderMessages[convId])
  const markRead = useChatStore((s) => s.markRead)
  const typingAgents = useChatStore((s) => s.typingAgents)
  const thinkingAgents = useChatStore((s) => s.thinkingAgents)
  const generatingConvs = useChatStore((s) => s.generatingConvs)
  const pinnedMessages = useChatStore((s) => s.pinnedMessages)
  const agents = useAgentStore((s) => s.agents)

  const typingSet = typingAgents[convId] || new Set()
  const typingAgentIds = [...typingSet]
  const thinkingMap = thinkingAgents[convId] || {}
  const thinkingEntries = Object.entries(thinkingMap)
  const isGenerating = generatingConvs.has(convId)
  const isGroup = conv?.type === 'group'
  const currentPinned = pinnedMessages[convId] || []

  const messagesRef = useRef(null)
  const generationTimeoutRef = useRef(null)
  const hasRestoredScroll = useRef(false)
  const [loadingOlder, setLoadingOlder] = useState(false)

  // P4: 消息加载缓存 — 已加载过的不重复请求
  useEffect(() => {
    if (!convId) return
    if (generatingConvs.has(convId)) return
    if (loadedConvs.has(convId) && conv && conv.messages.length > 0) return
    // 防止 Set 无限增长：超出上限时淘汰最早加入的条目
    if (loadedConvs.size >= LOADED_CONVS_MAX) {
      const toDelete = loadedConvs.size - LOADED_CONVS_MAX + 1
      let deleted = 0
      for (const id of loadedConvs) {
        if (deleted >= toDelete) break
        loadedConvs.delete(id)
        deleted++
      }
    }
    loadedConvs.add(convId)
    loadMessages(convId)
  }, [convId])

  // 清理已删除消息的缓存
  useEffect(() => {
    if (conv && conv.messages.length === 0 && loadedConvs.has(convId)) {
      loadedConvs.delete(convId)
    }
  }, [conv?.messages?.length, convId])

  // generationTimeoutRef cleanup
  useEffect(() => {
    return () => {
      if (generationTimeoutRef.current) {
        clearTimeout(generationTimeoutRef.current)
      }
    }
  }, [])

  // 标记已读
  useEffect(() => {
    if (isActive && convId) {
      useChatStore.getState().setActiveConversation(convId)
      markRead(convId)
    }
  }, [isActive, convId])

  useEffect(() => {
    if (convId && conv?.messages?.some((message) => isInternalNoiseMessage(message))) {
      pruneInternalMessages(convId)
    }
  }, [convId, conv?.messages, pruneInternalMessages])

  // P1: 内部滚动位置管理 — 保存非活跃标签的滚动位置
  useEffect(() => {
    if (!isActive && messagesRef.current && convId) {
      // 变为非活跃时保存滚动位置
      scrollPositions[convId] = messagesRef.current.scrollTop
    }
  }, [isActive, convId])

  // P1: 恢复滚动位置（变为活跃时）
  useEffect(() => {
    if (isActive && messagesRef.current) {
      const saved = scrollPositions[convId]
      if (saved != null && !hasRestoredScroll.current) {
        hasRestoredScroll.current = true
        requestAnimationFrame(() => {
          if (messagesRef.current) messagesRef.current.scrollTop = saved
        })
      }
    }
  }, [isActive])

  // 新消息到达时自动滚动（仅活跃标签）
  useEffect(() => {
    if (isActive && messagesRef.current && conv?.messages?.length > 0) {
      const el = messagesRef.current
      // 只有用户已经在底部附近时才自动滚动
      const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 150
      if (isNearBottom) {
        el.scrollTop = el.scrollHeight
      }
    }
  }, [conv?.messages?.length, isActive])

  // 首次加载时滚动到底部
  useEffect(() => {
    if (isActive && messagesRef.current && !hasRestoredScroll.current) {
      hasRestoredScroll.current = true
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight
    }
  }, [isActive])

  const handleSend = useCallback((text, mentionedAgents, attachments = []) => {
    if (isGenerating) return
    initializeGoal(convId, text)
    const msgId = `user-${Date.now()}`
    const content = { text }
    if (attachments.length > 0) content.attachments = attachments
    addMessage(convId, { id: msgId, sender: 'user', content, streaming: false })
    const targetAgent = !isGroup ? conv?.agentId : undefined
    wsClient.send({
      type: 'message',
      conversation_id: convId,
      sender: 'user',
      content: { text, target_agent: targetAgent, mentioned_agents: mentionedAgents, attachments },
    })
    if (generationTimeoutRef.current) clearTimeout(generationTimeoutRef.current)
    generationTimeoutRef.current = setTimeout(() => {
      useChatStore.getState().setGenerating(convId, false)
      generationTimeoutRef.current = null
    }, 60000)
  }, [convId, isGenerating, isGroup, conv?.agentId, addMessage, initializeGoal])

  const handleStop = useCallback(() => {
    wsClient.send({ type: 'stop', conversation_id: convId })
    if (generationTimeoutRef.current) {
      clearTimeout(generationTimeoutRef.current)
      generationTimeoutRef.current = null
    }
  }, [convId])

  if (!conv) {
    return (
      <div className="chat-panel-content">
        <div className="empty-state">
          <div className="icon"><MessageSquare size={40} /></div>
          <div className="text">选择或新建一个会话</div>
        </div>
      </div>
    )
  }

  const visibleMessages = (conv.messages || []).filter((message) => !isInternalNoiseMessage(message))

  // 最后一条 AI 消息的 id（用于控制重新生成按钮只在最新 AI 消息上显示）
  const lastAgentMsgId = useMemo(() => {
    for (let i = visibleMessages.length - 1; i >= 0; i--) {
      if (visibleMessages[i].sender !== 'user') return visibleMessages[i].id
    }
    return null
  }, [visibleMessages])

  const activeTypingAgent = typingAgentIds.length > 0
    ? agents.find((a) => a.agent_id === typingAgentIds[0])
    : null

  return (
    <div className="chat-panel-content">
      <GoalSnapshot conversationId={convId} readiness={readiness} isFirstTask={visibleMessages.length === 0} />
      <div className="chat-messages" ref={messagesRef}>
        {hasOlderMessages && (
          <button
            type="button"
            className="load-older-messages"
            disabled={loadingOlder}
            onClick={async () => {
              const element = messagesRef.current
              const previousHeight = element?.scrollHeight || 0
              setLoadingOlder(true)
              await loadOlderMessages(convId)
              requestAnimationFrame(() => {
                if (element) element.scrollTop += element.scrollHeight - previousHeight
              })
              setLoadingOlder(false)
            }}
          >
            <ChevronUp size={14} />
            {loadingOlder ? '加载中...' : '更早消息'}
          </button>
        )}
        {visibleMessages.length === 0 && (
          <div className="empty-state">
            <div className="text">发送消息开始对话</div>
          </div>
        )}
        {visibleMessages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            conversationId={convId}
            isPinned={currentPinned.includes(msg.id)}
            isLast={msg.id === lastAgentMsgId}
          />
        ))}

        {/* Typing indicator */}
        {typingAgentIds.length > 0 && (
          <div className="message-row">
            <div className="msg-avatar">
              {typingAgentIds.length === 1
                ? <IconAvatar agentId={typingAgentIds[0]} size={16} />
                : <IconAvatar iconKey="group" size={16} />
              }
            </div>
            <div className="message-content">
              <div className="typing-dots">
                <span className="typing-dot" />
                <span className="typing-dot" />
                <span className="typing-dot" />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Thinking bubbles */}
      {thinkingEntries.length > 0 && (
        <div style={{ padding: '4px var(--space-5) 0', display: 'flex', flexDirection: 'column', gap: 6, flexShrink: 0 }}>
          {thinkingEntries.map(([agentId, text]) => {
            const agent = agents.find(a => a.agent_id === agentId)
            return (
              <div key={agentId} style={{
                display: 'flex', alignItems: 'flex-start', gap: 8,
                padding: '8px 12px', borderRadius: 'var(--radius-md)',
                background: 'var(--accent-bg)', border: '1px solid var(--border)',
                fontSize: 'var(--text-xs)',
              }}>
                <IconAvatar agentId={agentId} size={18} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, color: 'var(--accent)', marginBottom: 2 }}>
                    {agent?.name || agentId} 正在思考...
                  </div>
                  <div style={{ color: 'var(--text-secondary)', lineHeight: 1.5, wordBreak: 'break-word' }}>
                    {text}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Deploy progress card */}
      {visibleMessages.length > 0 && <DeployProgressCard />}

      {/* Deploy inline card */}
      {visibleMessages.length > 0 && <InlineDeployCard />}

      {/* Input */}
      <InputBar
        onSend={handleSend}
        isGenerating={isGenerating}
        onStop={handleStop}
        isGroup={isGroup}
      />
    </div>
  )
})

export default ChatPanelContent
