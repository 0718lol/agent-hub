import React, { useRef, useEffect, useState, useCallback } from 'react'
import { MessageSquare, Code2, GitBranch, LayoutList, Menu, X, Search } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { useCanvasStore } from '../../stores/canvasStore'
import { useTabStore } from '../../stores/tabStore'
import MessageBubble from '../Chat/MessageBubble'
import InputBar from '../Chat/InputBar'
import InlineDeployCard from '../Chat/InlineDeployCard'
import ChatPanelHeader from './ChatPanelHeader'
import ChatPanelContent from './ChatPanelContent'
import TabBar from './TabBar'
import TaskBoard from '../Canvas/TaskBoard'
import AgentDAG from '../Canvas/AgentDAG'
import { wsClient } from '../../utils/websocket'
import { PREVIEW_HTML } from '../Canvas/previewHtml'
import IconAvatar from '../IconAvatar'

export default function ChatPanel({ onToggleSidebar }) {
  const openTabs = useTabStore((s) => s.openTabs)
  const activeTabId = useTabStore((s) => s.activeTabId)
  const activeTab = openTabs.find((t) => t.id === activeTabId)
  const activeId = activeTab?.convId || 'conv_pm'

  const conversations = useChatStore((s) => s.conversations)
  const addMessage = useChatStore((s) => s.addMessage)
  const updateLastAgentMessage = useChatStore((s) => s.updateLastAgentMessage)
  const loadMessages = useChatStore((s) => s.loadMessages)
  const clearMessages = useChatStore((s) => s.clearMessages)
  const setAgentStatus = useAgentStore((s) => s.setAgentStatus)
  const setTyping = useChatStore((s) => s.setTyping)
  const setThinking = useChatStore((s) => s.setThinking)
  const setGenerating = useChatStore((s) => s.setGenerating)
  const markRead = useChatStore((s) => s.markRead)
  const typingAgents = useChatStore((s) => s.typingAgents)
  const thinkingAgents = useChatStore((s) => s.thinkingAgents)
  const pinnedMessages = useChatStore((s) => s.pinnedMessages)
  const messagesRef = useRef(null)
  const generationTimeoutRef = useRef(null)

  const slidePanelOpen = useCanvasStore((s) => s.slidePanelOpen)
  const slidePanelContent = useCanvasStore((s) => s.slidePanelContent)
  const toggleSlidePanel = useCanvasStore((s) => s.toggleSlidePanel)
  const [taskPopup, setTaskPopup] = useState(false)
  const [dagPopup, setDagPopup] = useState(false)
  const setGeneratedCode = useCanvasStore((s) => s.setGeneratedCode)
  const setPreviewHtml = useCanvasStore((s) => s.setPreviewHtml)
  const updateTaskByAgent = useCanvasStore((s) => s.updateTaskByAgent)

  const conv = conversations.find((c) => c.id === activeId)
  const agents = useAgentStore((s) => s.agents)
  const typingSet = typingAgents[activeId] || new Set()
  const typingAgentIds = [...typingSet]
  const thinkingMap = thinkingAgents[activeId] || {}
  const thinkingEntries = Object.entries(thinkingMap)
  const generatingConvs = useChatStore((s) => s.generatingConvs)
  const isGenerating = generatingConvs.has(activeId)
  const isGroup = conv?.type === 'group'
  const currentPinned = pinnedMessages[activeId] || []

  useEffect(() => {
    // 如果当前会话正在生成中，延迟加载历史，避免覆盖流式消息
    if (generatingConvs.has(activeId)) return
    loadMessages(activeId)
  }, [activeId])

  // Sync canvas code & preview from messages
  useEffect(() => {
    if (!conv?.messages) return
    let foundCode = false
    let foundPreview = false
    for (let i = conv.messages.length - 1; i >= 0; i--) {
      const msg = conv.messages[i]
      if (msg.streaming) continue
      const text = msg.content?.text || ''
      const previewMatch = text.match(/\[preview:(\w+)\]/)
      if (previewMatch && PREVIEW_HTML[previewMatch[1]]) {
        const code = PREVIEW_HTML[previewMatch[1]]
        if (!foundCode) { setGeneratedCode('html', code); foundCode = true }
        if (!foundPreview) { useCanvasStore.getState().setPreviewHtml(code); foundPreview = true }
      }
      const codeMatch = text.match(/```(\w*)\n([\s\S]*?)```/)
      if (codeMatch) {
        const lang = codeMatch[1] || 'text'
        const code = codeMatch[2]
        if (!foundCode) { setGeneratedCode(lang, code); foundCode = true }
        if (lang === 'html' && !foundPreview) { useCanvasStore.getState().setPreviewHtml(code); foundPreview = true }
      }
      if (foundCode && foundPreview) break
    }
  }, [conv?.messages, activeId])

  // WS connection — 延迟到下一帧，不阻塞 UI 更新
  useEffect(() => {
    markRead(activeId)
    wsClient.send({ type: 'read', conversation_id: activeId, sender: 'user' })
  }, [activeId])

  useEffect(() => {
    // 使用 requestAnimationFrame 延迟 WebSocket 连接，让 UI 先更新
    const rafId = requestAnimationFrame(() => {
      wsClient.connect(activeId)
    })

    const unsub = wsClient.onMessage((data) => {
      if (data.conversation_id !== activeId) return
      if (data.type === 'typing') {
        setTyping(activeId, data.agent_id, data.is_typing)
        // 超时保护：15 秒后自动清除 typing 状态，防止卡死
        if (data.is_typing) {
          setTimeout(() => {
            const convNow = useChatStore.getState().conversations.find((c) => c.id === activeId)
            const stillTyping = convNow?.messages?.some((m) => m.sender === data.agent_id && m.streaming)
            if (!stillTyping) setTyping(activeId, data.agent_id, false)
          }, 15000)
        }
        return
      }
      if (data.type === 'thinking') { setThinking(activeId, data.agent_id, data.text); return }
      if (data.type === 'code') {
        useCanvasStore.getState().setGeneratedCode(data.language, data.code)
        if (data.language === 'html') useCanvasStore.getState().setPreviewHtml(data.code)
        return
      }
      if (data.type === 'preview') { useCanvasStore.getState().setPreviewHtml(data.html); return }
      if (data.type === 'generating') {
        setGenerating(activeId, data.is_generating)
        if (!data.is_generating && generationTimeoutRef.current) {
          clearTimeout(generationTimeoutRef.current)
          generationTimeoutRef.current = null
        }
        return
      }
      if (data.type === 'task_status') {
        useCanvasStore.getState().updateTaskByAgent(data.agent_id, data.status === 'doing' ? 'doing' : data.status)
        useCanvasStore.getState().setNodeStatus(data.agent_id, data.status === 'doing' ? 'working' : data.status)
        return
      }
      if (data.type === 'deploy_status') {
        const { status, log, url } = data
        if (useCanvasStore.getState().deployStatus === 'idle') {
          useCanvasStore.getState().startDeploy()
        }
        if (log) useCanvasStore.getState().appendDeployLog(log)
        if (status === 'success' && url) useCanvasStore.getState().finishDeploy(url)
        if (status === 'failed') useCanvasStore.getState().failDeploy()
        return
      }
      if (data.type === 'agent_created') {
        const agent = data.agent
        if (agent) {
          useChatStore.getState().addConversation({
            id: `conv_${agent.agent_id}`,
            type: 'single',
            agentId: agent.agent_id,
            name: agent.name,
            avatar: null,
            messages: [],
            pinned: false,
            unread: false,
            updatedAt: Date.now(),
          })
        }
        return
      }
      if (data.type === 'agent_deleted') {
        useChatStore.getState().removeConversation(`conv_${data.agent_id}`)
        return
      }
      if (data.type === 'read') { markRead(activeId); return }
      if (data.type === 'message') {
        // 跳过服务器回显的用户消息（handleSend 已本地添加）
        if (data.sender === 'user') return

        // 收到 Agent 消息时自动清除该 Agent 的 typing 状态
        setTyping(activeId, data.sender, false)

        if (data.stream) {
          const convNow = useChatStore.getState().conversations.find((c) => c.id === activeId)
          const hasStreaming = convNow?.messages?.some((m) => m.sender === data.sender && m.streaming)
          if (hasStreaming) {
            updateLastAgentMessage(activeId, data.sender, data.content.text, true)
          } else {
            // 检查是否有同名 agent 的最终消息刚完成（防止创建重复气泡）
            const lastMsg = convNow?.messages?.[convNow.messages.length - 1]
            const isDuplicate = lastMsg && lastMsg.sender === data.sender && !lastMsg.streaming
            if (!isDuplicate) {
              addMessage(activeId, { id: `${data.sender}-stream-${Date.now()}`, sender: data.sender, content: data.content, streaming: true })
            }
          }
          setAgentStatus(data.sender, 'working')
        } else {
          const convNow = useChatStore.getState().conversations.find((c) => c.id === activeId)
          const hasStreaming = convNow?.messages?.some((m) => m.sender === data.sender && m.streaming)
          if (hasStreaming) {
            updateLastAgentMessage(activeId, data.sender, data.content.text, false)
          } else {
            // 检查是否已有该 agent 的非流式消息（避免重复）
            const lastMsg = convNow?.messages?.[convNow.messages.length - 1]
            const isDuplicate = lastMsg && lastMsg.sender === data.sender && !lastMsg.streaming && lastMsg.content?.text === data.content?.text
            if (!isDuplicate) {
              addMessage(activeId, { id: `${data.sender}-final-${Date.now()}`, sender: data.sender, content: data.content, streaming: false })
            }
          }
          setAgentStatus(data.sender, 'done')
          setTimeout(() => setAgentStatus(data.sender, 'idle'), 2000)
        }
      }
    })
    return () => {
      cancelAnimationFrame(rafId)
      unsub(); wsClient.disconnect()
      if (generationTimeoutRef.current) {
        clearTimeout(generationTimeoutRef.current)
        generationTimeoutRef.current = null
      }
    }
  }, [activeId])

  // Auto scroll
  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight
    }
  }, [conv?.messages])

  const handleSend = (text, mentionedAgents, attachments = []) => {
    if (isGenerating) return // 双重保险：生成中禁止发送
    const msgId = `user-${Date.now()}`
    const content = { text }
    if (attachments.length > 0) content.attachments = attachments
    addMessage(activeId, { id: msgId, sender: 'user', content, streaming: false })
    const targetAgent = !isGroup ? conv?.agentId : undefined
    wsClient.send({
      type: 'message',
      conversation_id: activeId,
      sender: 'user',
      content: { text, target_agent: targetAgent, mentioned_agents: mentionedAgents, attachments },
    })
    // 启动超时清理（60 秒无响应则强制解锁生成状态）
    if (generationTimeoutRef.current) clearTimeout(generationTimeoutRef.current)
    generationTimeoutRef.current = setTimeout(() => {
      setGenerating(activeId, false)
      generationTimeoutRef.current = null
    }, 60000)
  }

  const handleStop = () => {
    wsClient.send({ type: 'stop', conversation_id: activeId })
    if (generationTimeoutRef.current) {
      clearTimeout(generationTimeoutRef.current)
      generationTimeoutRef.current = null
    }
  }

  const handleClearHistory = async () => {
    if (!activeId) return
    if (!window.confirm('确定要清空当前会话的全部历史消息吗？此操作不可撤销。')) return
    try {
      await fetch(`/api/conversations/${activeId}/messages`, { method: 'DELETE' })
      clearMessages(activeId)
    } catch (err) {
      console.error('Clear history failed:', err)
      window.alert('清空失败，请稍后再试。')
    }
  }

  if (!conv) return (
    <div className="chat-panel">
      <div className="empty-state">
        <div className="icon"><MessageSquare size={40} /></div>
        <div className="text">选择或新建一个会话</div>
      </div>
    </div>
  )

  return (
    <div className="chat-panel">
      <ChatPanelHeader
        convId={activeId}
        onToggleSidebar={onToggleSidebar}
        onToggleTask={() => setTaskPopup((v) => !v)}
        onToggleDag={() => setDagPopup((v) => !v)}
        taskOpen={taskPopup}
        dagOpen={dagPopup}
        onClearHistory={handleClearHistory}
      />

      <TabBar />

      <div className="chat-panel-tabs-container">
        {openTabs.map((tab) => (
          <div
            key={tab.id}
            className="chat-panel-tab-content"
            style={tab.id !== activeTabId ? { display: 'none' } : undefined}
          >
            <ChatPanelContent convId={tab.convId} isActive={tab.id === activeTabId} />
          </div>
        ))}
      </div>

      {/* 任务看板悬浮窗 */}
      {taskPopup && (
        <>
          <div className="task-popup-backdrop" onClick={() => setTaskPopup(false)} />
          <div className="task-popup">
            <div className="task-popup-header">
              <span>任务看板</span>
              <button className="slide-panel-btn" onClick={() => setTaskPopup(false)}>
                <X size={16} />
              </button>
            </div>
            <div className="task-popup-body">
              <TaskBoard />
            </div>
          </div>
        </>
      )}

      {/* 协作图悬浮窗 */}
      {dagPopup && (
        <>
          <div className="task-popup-backdrop" onClick={() => setDagPopup(false)} />
          <div className="task-popup" style={{ maxWidth: 'min(560px, 90vw)' }}>
            <div className="task-popup-header">
              <span>协作图</span>
              <button className="slide-panel-btn" onClick={() => setDagPopup(false)}>
                <X size={16} />
              </button>
            </div>
            <div className="task-popup-body">
              <AgentDAG />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
