import React, { lazy, Suspense, useRef, useEffect, useState } from 'react'
import { MessageSquare, X } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { useCanvasStore } from '../../stores/canvasStore'
import { useTabStore } from '../../stores/tabStore'
import ChatPanelHeader from './ChatPanelHeader'
import ChatPanelContent from './ChatPanelContent'
import TabBar from './TabBar'
import TaskBoard from '../Canvas/TaskBoard'
import { wsClient } from '../../utils/websocket'
import { PREVIEW_HTML } from '../Canvas/previewHtml'
import { buildPromoPreviewHtml, extractPromoSubject } from '../Canvas/promoPreview'

const AgentFlow = lazy(() => import('../Canvas/AgentFlow'))

export default function ChatPanel({ onToggleSidebar, readiness }) {
  const openTabs = useTabStore((s) => s.openTabs)
  const activeTabId = useTabStore((s) => s.activeTabId)
  const activeTab = openTabs.find((t) => t.id === activeTabId)
  const activeId = activeTab?.convId || 'conv_pm'

  const conversations = useChatStore((s) => s.conversations)
  const ownerId = useChatStore((s) => s._ownerId)
  const generatingConvs = useChatStore((s) => s.generatingConvs)
  const loadMessages = useChatStore((s) => s.loadMessages)
  const clearMessages = useChatStore((s) => s.clearMessages)
  const setGenerating = useChatStore((s) => s.setGenerating)
  const markRead = useChatStore((s) => s.markRead)

  const deployTimeoutsRef = useRef(new Map())
  const typingTimeoutsRef = useRef(new Map())

  const [taskPopup, setTaskPopup] = useState(false)
  const [dagPopup, setDagPopup] = useState(false)

  const conv = conversations.find((c) => c.id === activeId)

  // Keep canvasStore's active session bucket synchronized with the active tab
  useEffect(() => {
    useCanvasStore.getState().setActiveConversation(activeId)
  }, [activeId])

  useEffect(() => {
    // 如果当前会话正在生成中，延迟加载历史，避免覆盖流式消息
    if (!ownerId || useChatStore.getState().generatingConvs.has(activeId)) return
    loadMessages(activeId)
  }, [activeId, ownerId, loadMessages])

  // Hydrate canvas code & preview from finalized conversation messages into activeId's bucket
  useEffect(() => {
    if (!conv?.messages || conv.messages.length === 0) return
    const session = useCanvasStore.getState().getSession(activeId)
    let foundCode = Boolean(session?.generatedCode)
    let foundPreview = Boolean(session?.previewHtml)
    if (foundCode && foundPreview) return

    for (let i = conv.messages.length - 1; i >= 0; i--) {
      const msg = conv.messages[i]
      if (msg.streaming) continue
      const text = msg.content?.text || ''
      const previewMatch = text.match(/\[preview:(\w+)\]/)
      if (previewMatch && PREVIEW_HTML[previewMatch[1]]) {
        const code = previewMatch[1] === 'promo'
          ? buildPromoPreviewHtml(extractPromoSubject(text))
          : PREVIEW_HTML[previewMatch[1]]
        if (!foundCode) { useCanvasStore.getState().setGeneratedCode('html', code, activeId); foundCode = true }
        if (!foundPreview) { useCanvasStore.getState().setPreviewHtml(code, activeId); foundPreview = true }
      }
      const codeMatch = text.match(/```(\w*)\n([\s\S]*?)```/)
      if (codeMatch) {
        const lang = codeMatch[1] || 'text'
        const code = codeMatch[2]
        if (!foundCode) { useCanvasStore.getState().setGeneratedCode(lang, code, activeId); foundCode = true }
        if (lang === 'html' && !foundPreview) { useCanvasStore.getState().setPreviewHtml(code, activeId); foundPreview = true }
      }
      const mockupMatch = text.match(/\[mockup:(\w+)\]/)
      if (mockupMatch?.[1] === 'promo' && !foundPreview) {
        useCanvasStore.getState().setPreviewHtml(buildPromoPreviewHtml(extractPromoSubject(text)), activeId)
        foundPreview = true
      }
      if (foundCode && foundPreview) break
    }
  }, [conv?.messages, activeId])

  // Multi-tab WebSocket pool: keep connections alive across all open & generating tabs
  useEffect(() => {
    const trackedConvIds = [
      ...new Set([activeId, ...openTabs.map((t) => t.convId), ...generatingConvs].filter(Boolean)),
    ]
    wsClient.syncConnections(trackedConvIds, activeId)
  }, [activeId, openTabs, generatingConvs])

  useEffect(() => {
    markRead(activeId)
    wsClient.send({ type: 'read', conversation_id: activeId, sender: 'user' })
  }, [activeId, markRead])

  // Single multiplexed WS event router: routes events to each conversation's isolated bucket
  useEffect(() => {
    const deployTimeouts = deployTimeoutsRef.current
    const typingTimeouts = typingTimeoutsRef.current

    const clearDeployWatchdog = (convId) => {
      const timer = deployTimeouts.get(convId)
      if (timer) {
        clearTimeout(timer)
        deployTimeouts.delete(convId)
      }
    }

    const unsub = wsClient.onMessage((data) => {
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

      const targetConvId = data.conversation_id || wsClient.currentConvId || 'conv_pm'
      const chatState = useChatStore.getState()
      const canvasState = useCanvasStore.getState()

      if (data.type === 'typing') {
        chatState.setTyping(targetConvId, data.agent_id, data.is_typing)
        const typingKey = `${targetConvId}:${data.agent_id}`
        if (typingTimeouts.has(typingKey)) {
          clearTimeout(typingTimeouts.get(typingKey))
          typingTimeouts.delete(typingKey)
        }
        if (data.is_typing) {
          const timer = setTimeout(() => {
            typingTimeouts.delete(typingKey)
            const convNow = useChatStore.getState().conversations.find((c) => c.id === targetConvId)
            const stillTyping = convNow?.messages?.some((m) => m.sender === data.agent_id && m.streaming)
            if (!stillTyping) useChatStore.getState().setTyping(targetConvId, data.agent_id, false)
          }, 15000)
          typingTimeouts.set(typingKey, timer)
        }
        return
      }

      if (data.type === 'thinking') {
        chatState.setThinking(targetConvId, data.agent_id, data.text)
        return
      }

      if (data.type === 'code') {
        canvasState.setGeneratedCode(data.language, data.code, targetConvId)
        if (data.artifact_id) {
          const current = chatState.conversations.find((item) => item.id === targetConvId)?.goal || {}
          chatState.updateConversation(targetConvId, {
            goal: {
              ...current,
              stage: 'validating',
              latestDeliverable: data.artifact_name || current.latestDeliverable,
              latestArtifactId: data.artifact_id,
              nextAction: '审阅并验证最新产物',
            },
          })
        }
        return
      }

      if (data.type === 'preview') {
        canvasState.setPreviewHtml(data.html, targetConvId)
        return
      }

      if (data.type === 'generating') {
        chatState.setGenerating(targetConvId, data.is_generating)
        return
      }

      if (data.type === 'task_status') {
        canvasState.updateTaskByAgent(
          data.agent_id,
          data.status === 'doing' ? 'doing' : data.status,
          targetConvId
        )
        canvasState.setNodeStatus(
          data.agent_id,
          data.status === 'doing' ? 'working' : data.status,
          targetConvId
        )
        return
      }

      if (data.type === 'deploy_status') {
        const { status, log, url, result_type: resultType, target } = data
        clearDeployWatchdog(targetConvId)
        deployTimeouts.set(
          targetConvId,
          setTimeout(() => {
            useCanvasStore.getState().failDeploy(targetConvId)
            deployTimeouts.delete(targetConvId)
          }, 12 * 60 * 1000)
        )

        const targetSession = canvasState.getSession(targetConvId)
        if (targetSession.deployStatus === 'idle') {
          canvasState.startDeploy(targetConvId)
        }
        if (log) useCanvasStore.getState().appendDeployLog(log, targetConvId)
        if (status === 'success' && url) {
          useCanvasStore.getState().finishDeploy(url, resultType, target, targetConvId)
          clearDeployWatchdog(targetConvId)
        }
        if (status === 'failed') {
          useCanvasStore.getState().failDeploy(targetConvId)
          clearDeployWatchdog(targetConvId)
        }
        if (status === 'cancelled') {
          useCanvasStore.getState().cancelDeploy(targetConvId)
          clearDeployWatchdog(targetConvId)
        }
        return
      }

      if (data.type === 'read') {
        chatState.markRead(targetConvId)
        return
      }

      if (data.type === 'message') {
        if (data.sender === 'user') return

        if (data.sender === 'user_interaction_judge' && data.id) {
          chatState.addMessage(targetConvId, {
            id: data.id,
            sender: data.sender,
            content: data.content,
            streaming: false,
          })
          return
        }

        chatState.setTyping(targetConvId, data.sender, false)
        const setAgentStatus = useAgentStore.getState().setAgentStatus

        if (data.stream) {
          const convNow = useChatStore.getState().conversations.find((c) => c.id === targetConvId)
          const hasStreaming = convNow?.messages?.some((m) => m.sender === data.sender && m.streaming)
          if (hasStreaming) {
            useChatStore.getState().updateLastAgentMessage(targetConvId, data.sender, data.content.text, true)
          } else {
            const lastMsg = convNow?.messages?.at(-1)
            const isDuplicate = lastMsg && lastMsg.sender === data.sender && !lastMsg.streaming
            if (!isDuplicate) {
              useChatStore.getState().addMessage(targetConvId, {
                id: `${data.sender}-stream-${Date.now()}`,
                sender: data.sender,
                content: data.content,
                streaming: true,
              })
            }
          }
          setAgentStatus(data.sender, 'working')
        } else {
          const convNow = useChatStore.getState().conversations.find((c) => c.id === targetConvId)
          const hasStreaming = convNow?.messages?.some((m) => m.sender === data.sender && m.streaming)
          if (hasStreaming) {
            useChatStore.getState().updateLastAgentMessage(targetConvId, data.sender, data.content.text, false)
          } else {
            const lastMsg = convNow?.messages?.at(-1)
            const isDuplicate =
              lastMsg &&
              lastMsg.sender === data.sender &&
              !lastMsg.streaming &&
              lastMsg.content?.text === data.content?.text
            if (!isDuplicate) {
              useChatStore.getState().addMessage(targetConvId, {
                id: `${data.sender}-final-${Date.now()}`,
                sender: data.sender,
                content: data.content,
                streaming: false,
              })
            }
          }
          setAgentStatus(data.sender, 'done')
          setTimeout(() => setAgentStatus(data.sender, 'idle'), 2000)
        }
      }
    })

    return () => {
      unsub()
      wsClient.disconnect()
      for (const timer of deployTimeouts.values()) clearTimeout(timer)
      deployTimeouts.clear()
      for (const timer of typingTimeouts.values()) clearTimeout(timer)
      typingTimeouts.clear()
    }
  }, [])

  const handleClearHistory = async () => {
    if (!activeId) return
    if (!window.confirm('确定要清空当前会话的全部历史消息吗？此操作不可撤销。')) return
    try {
      const response = await fetch(`/api/conversations/${activeId}/messages`, { method: 'DELETE' })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      clearMessages(activeId)
      useCanvasStore.getState().setPreviewHtml(null, activeId)
      useCanvasStore.getState().setGeneratedCode(null, null, activeId)
      setGenerating(activeId, false)
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
        onToggleOffice={() => window.dispatchEvent(new Event('agenthub:toggle-office'))}
        readiness={readiness}
      />

      <TabBar />

      <div className="chat-panel-tabs-container">
        {openTabs.map((tab) => (
          <div
            key={tab.id}
            className="chat-panel-tab-content"
            style={tab.id !== activeTabId ? { display: 'none' } : undefined}
          >
            <ChatPanelContent convId={tab.convId} isActive={tab.id === activeTabId} readiness={readiness} />
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
            <div className="task-popup-body" style={{ padding: 0, minHeight: 0 }}>
              <Suspense fallback={<div style={{ padding: 16, color: 'var(--text-muted)' }}>正在加载协作图...</div>}>
                <AgentFlow />
              </Suspense>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
