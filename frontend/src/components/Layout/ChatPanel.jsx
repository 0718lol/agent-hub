import React, { useRef, useEffect, useState } from 'react'
import { MessageSquare, Code2, GitBranch, LayoutList, Menu, X } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { useCanvasStore } from '../../stores/canvasStore'
import MessageBubble from '../Chat/MessageBubble'
import InputBar from '../Chat/InputBar'
import InlineDeployCard from '../Chat/InlineDeployCard'
import AgentDAG from '../Canvas/AgentDAG'
import TaskBoard from '../Canvas/TaskBoard'
import { wsClient } from '../../utils/websocket'
import { PREVIEW_HTML } from '../Canvas/previewHtml'
import IconAvatar from '../IconAvatar'

export default function ChatPanel({ onToggleSidebar }) {
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
  const pinnedMessages = useChatStore((s) => s.pinnedMessages)
  const messagesRef = useRef(null)

  const slidePanelOpen = useCanvasStore((s) => s.slidePanelOpen)
  const toggleSlidePanel = useCanvasStore((s) => s.toggleSlidePanel)
  const setGeneratedCode = useCanvasStore((s) => s.setGeneratedCode)
  const setPreviewHtml = useCanvasStore((s) => s.setPreviewHtml)
  const updateTaskByAgent = useCanvasStore((s) => s.updateTaskByAgent)

  const conv = conversations.find((c) => c.id === activeId)
  const agents = useAgentStore((s) => s.agents)
  const typingSet = typingAgents[activeId] || new Set()
  const typingAgentIds = [...typingSet]
  const thinkingMap = thinkingAgents[activeId] || {}
  const thinkingEntries = Object.entries(thinkingMap)
  const isGenerating = generatingConvs.has(activeId)
  const isGroup = conv?.type === 'group'
  const currentPinned = pinnedMessages[activeId] || []

  const [dagPopup, setDagPopup] = useState(false)
  const [taskPopup, setTaskPopup] = useState(false)

  useEffect(() => {
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

  // WS connection
  useEffect(() => {
    markRead(activeId)
    wsClient.send({ type: 'read', conversation_id: activeId, sender: 'user' })
  }, [activeId])

  useEffect(() => {
    wsClient.connect(activeId)
    const unsub = wsClient.onMessage((data) => {
      if (data.conversation_id !== activeId) return
      if (data.type === 'typing') { setTyping(activeId, data.agent_id, data.is_typing); return }
      if (data.type === 'thinking') { setThinking(activeId, data.agent_id, data.text); return }
      if (data.type === 'code') {
        useCanvasStore.getState().setGeneratedCode(data.language, data.code)
        if (data.language === 'html') useCanvasStore.getState().setPreviewHtml(data.code)
        return
      }
      if (data.type === 'preview') { useCanvasStore.getState().setPreviewHtml(data.html); return }
      if (data.type === 'generating') { setGenerating(activeId, data.is_generating); return }
      if (data.type === 'task_status') {
        useCanvasStore.getState().updateTaskByAgent(data.agent_id, data.status === 'doing' ? 'doing' : data.status)
        useCanvasStore.getState().setNodeStatus(data.agent_id, data.status === 'doing' ? 'working' : data.status)
        return
      }
      if (data.type === 'deploy_status') {
        const { status, log, url } = data
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
        if (data.stream) {
          const convNow = useChatStore.getState().conversations.find((c) => c.id === activeId)
          const hasStreaming = convNow?.messages?.some((m) => m.sender === data.sender && m.streaming)
          if (hasStreaming) { updateLastAgentMessage(activeId, data.sender, data.content.text, true) }
          else { addMessage(activeId, { sender: data.sender, content: data.content, streaming: true }) }
          setAgentStatus(data.sender, 'working')
        } else {
          const convNow = useChatStore.getState().conversations.find((c) => c.id === activeId)
          const hasStreaming = convNow?.messages?.some((m) => m.sender === data.sender && m.streaming)
          if (hasStreaming) { updateLastAgentMessage(activeId, data.sender, data.content.text, false) }
          else { addMessage(activeId, { sender: data.sender, content: data.content, streaming: false }) }
          setAgentStatus(data.sender, 'done')
          setTimeout(() => setAgentStatus(data.sender, 'idle'), 2000)
        }
      }
    })
    return () => { unsub(); wsClient.disconnect() }
  }, [activeId])

  // Auto scroll
  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight
    }
  }, [conv?.messages])

  const handleSend = (text, mentionedAgents) => {
    addMessage(activeId, { sender: 'user', content: { text }, streaming: false })
    const targetAgent = !isGroup ? conv?.agentId : undefined
    wsClient.send({
      type: 'message',
      conversation_id: activeId,
      sender: 'user',
      content: { text, target_agent: targetAgent, mentioned_agents: mentionedAgents },
    })
  }

  const handleStop = () => { wsClient.send({ type: 'stop', conversation_id: activeId }) }

  // Active typing agent for group indicator
  const activeTypingAgent = typingAgentIds.length > 0
    ? agents.find((a) => a.agent_id === typingAgentIds[0])
    : null

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
      <div className="chat-panel-inner">
        {/* Header */}
        <div className="chat-header">
          <button className="hamburger-btn" onClick={onToggleSidebar} title="菜单">
            <Menu size={18} />
          </button>
          {isGroup ? (
            <>
              <div className="group-avatar-stack">
                {(conv.agents || []).slice(0, 4).map((agentId) => (
                  <div key={agentId} className="mini-avatar">
                    <IconAvatar agentId={agentId} size={10} />
                  </div>
                ))}
              </div>
              <div className="chat-header-info">
                <div className="chat-header-name">{conv.name}</div>
                <div className="chat-header-desc">
                  {conv.agents?.length || 0} 人
                  {activeTypingAgent && (
                    <span style={{ color: 'var(--accent)', marginLeft: 8 }}>
                      · {activeTypingAgent.name} 正在回复...
                    </span>
                  )}
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="chat-header-avatar">
                <IconAvatar agentId={conv.agentId} size={20} />
              </div>
              <div className="chat-header-info">
                <div className="chat-header-name">{conv.name}</div>
                <div className="chat-header-desc">
                  {agents.find((a) => a.agent_id === conv.agentId)?.role || ''}
                </div>
              </div>
              <span className={`online-dot ${agents.find((a) => a.agent_id === conv.agentId)?.status === 'working' ? 'busy' : 'online'}`} />
            </>
          )}
          <div className="chat-header-actions">
            {typingAgentIds.length > 0 && !activeTypingAgent && (
              <span className="chat-header-badge">{typingAgentIds.length} 人输入中</span>
            )}
            <button className="header-icon-btn" onClick={() => setTaskPopup(!taskPopup)}>
              <LayoutList size={20} />
              <span className="icon-tooltip">任务看板</span>
            </button>
            <button className="header-icon-btn" onClick={() => setDagPopup(!dagPopup)}>
              <GitBranch size={20} />
              <span className="icon-tooltip">协作图</span>
            </button>
            <button className="header-icon-btn" onClick={toggleSlidePanel} style={slidePanelOpen ? { color: 'var(--accent)' } : undefined}>
              <Code2 size={20} />
              <span className="icon-tooltip">代码/文档预览</span>
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="chat-messages" ref={messagesRef}>
          {conv.messages.length === 0 && (
            <div className="empty-state">
              <div className="text">发送消息开始对话</div>
            </div>
          )}
          {conv.messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              isPinned={currentPinned.includes(msg.id)}
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

        {/* Deploy inline card */}
        {conv.messages.length > 0 && <InlineDeployCard />}

        {/* DAG popup */}
        {dagPopup && (
          <>
            <div className="feature-popup-backdrop" onClick={() => setDagPopup(false)} />
            <div className="feature-popup">
              <div className="feature-popup-header">
                <span>协作图</span>
                <button className="slide-panel-btn" onClick={() => setDagPopup(false)}>
                  <X />
                </button>
              </div>
              <div className="feature-popup-body">
                <AgentDAG compact />
              </div>
            </div>
          </>
        )}

        {/* Task popup */}
        {taskPopup && (
          <>
            <div className="feature-popup-backdrop" onClick={() => setTaskPopup(false)} />
            <div className="feature-popup">
              <div className="feature-popup-header">
                <span>任务看板</span>
                <button className="slide-panel-btn" onClick={() => setTaskPopup(false)}>
                  <X />
                </button>
              </div>
              <div className="feature-popup-body">
                <TaskBoard compact />
              </div>
            </div>
          </>
        )}

        {/* Input */}
        <InputBar
          onSend={handleSend}
          isGenerating={isGenerating}
          onStop={handleStop}
          isGroup={isGroup}
        />
      </div>
    </div>
  )
}
