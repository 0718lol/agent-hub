import React, { useState } from 'react'
import { Copy, RefreshCw, Reply, Pin, Check, Wrench, Settings2, Globe, FileText, CheckCircle2, AlertCircle } from 'lucide-react'
import { useAgentStore } from '../../stores/agentStore'
import { useChatStore } from '../../stores/chatStore'
import { useCanvasStore } from '../../stores/canvasStore'
import CodeCard from './CodeCard'
import MockupCard from './MockupCard'
import ClarificationCard from './ClarificationCard'
import AskUserCard from './AskUserCard'
import FileAttachmentCard from './FileAttachmentCard'
import { PREVIEW_HTML } from '../Canvas/previewHtml'
import { wsClient } from '../../utils/websocket'
import IconAvatar from '../IconAvatar'

const TOOL_ICONS = {
  web_search: Globe,
  http_request: Globe,
  file_read: FileText,
  file_write: FileText,
  file_list: FileText,
  file_edit_line: Settings2,
  file_patch_block: Settings2,
  safe_python_executor: Wrench,
  run_stateful_command: Wrench,
  browser_action: Globe,
}

export default function MessageBubble({ message, isPinned }) {
  const agents = useAgentStore((s) => s.agents)
  const activeId = useChatStore((s) => s.activeConversationId)
  const addMessage = useChatStore((s) => s.addMessage)
  const allRead = useChatStore((s) => s.allRead)
  const togglePinMessage = useChatStore((s) => s.togglePinMessage)
  const setPreviewHtml = useCanvasStore((s) => s.setPreviewHtml)
  const setGeneratedCode = useCanvasStore((s) => s.setGeneratedCode)

  const isUser = message.sender === 'user'
  const agent = agents.find((a) => a.agent_id === message.sender)
  const text = message.content?.text || ''
  const attachments = message.content?.attachments || []
  const isRead = allRead[activeId]
  const [copied, setCopied] = useState(false)

  const timeStr = message.timestamp
    ? new Date(message.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    : ''

  const handleCopy = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleRegenerate = () => {
    wsClient.send({
      type: 'message',
      conversation_id: activeId,
      sender: 'user',
      content: { text: '请重新生成', regenerate: true, original_message_id: message.id },
    })
  }

  const handleReply = () => {
    addMessage(activeId, {
      sender: 'user',
      content: { text: `> ${text.slice(0, 80)}${text.length > 80 ? '...' : ''}\n\n` },
      streaming: false,
    })
  }

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
      content: { text: `[clarified] ${answerText}`, target_agent: 'agent_pm' },
    })
  }

  const handleOptionClick = (option) => {
    addMessage(activeId, {
      sender: 'user',
      content: { text: option },
      streaming: false,
    })
    wsClient.send({
      type: 'message',
      conversation_id: activeId,
      sender: 'user',
      content: { text: option },
    })
  }

  const handleAskUserReply = (answer) => {
    addMessage(activeId, {
      sender: 'user',
      content: { text: answer },
      streaming: false,
    })
    wsClient.send({
      type: 'message',
      conversation_id: activeId,
      sender: 'user',
      content: {
        text: `[ask_user_reply] ${answer}`,
        target_agent: message.sender,
      },
    })
  }

  const renderText = (t) => {
    let clean = t.replace(/\[thinking\][\s\S]*?\[\/thinking\]/g, '')
    clean = clean.replace(/\[assign:\w+\]/g, '')
    clean = clean.trim()

    if (!clean) return null

    const parts = clean.split(/(\[mockup:\w+\]|\[preview:\w+\]|\[clarify:[^\]]+\]|\[ask_user:[^\]]+\]|\[options:[^\]]+\]|\[tool_call:[^\]]+\][\s\S]*?\[\/tool_call\]|\[工具结果: [^\]]+\][\s\S]*?请基于以上工具结果继续回复用户。|```[\s\S]*?```)/g)
    return parts.map((part, i) => {
      if (!part) return null

      // Tool Call Match
      const toolCallMatch = part.match(/\[tool_call:([^\]]+)\]([\s\S]*?)\[\/tool_call\]/)
      if (toolCallMatch) {
        const toolName = toolCallMatch[1]
        let params = {}
        try {
          params = JSON.parse(toolCallMatch[2].trim())
        } catch(e) {}
        
        const Icon = TOOL_ICONS[toolName] || Wrench
        return (
          <div key={i} style={{
            margin: '8px 0', padding: '10px 14px', borderRadius: '8px',
            background: 'rgba(255, 255, 255, 0.03)', border: '1px solid rgba(255,255,255,0.08)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: Object.keys(params).length ? 6 : 0 }}>
              <Icon size={14} color="#818cf8" />
              <span style={{ fontSize: 13, fontWeight: 600, color: '#c7d2fe' }}>调用工具：{toolName}</span>
              <span style={{ fontSize: 11, background: 'rgba(99,102,241,0.2)', color: '#a5b4fc', padding: '2px 6px', borderRadius: 4, marginLeft: 'auto' }}>
                执行中...
              </span>
            </div>
            {Object.keys(params).length > 0 && (
              <pre style={{ margin: 0, fontSize: 11, color: '#94a3b8', background: 'rgba(0,0,0,0.2)', padding: '6px', borderRadius: 4, whiteSpace: 'pre-wrap', maxHeight: 60, overflow: 'hidden' }}>
                {JSON.stringify(params, null, 2)}
              </pre>
            )}
          </div>
        )
      }

      // Tool Result Match
      const toolResultMatch = part.match(/\[工具结果: ([^\]]+)\]\n([\s\S]*?)\n\n请基于以上工具结果继续回复用户。/)
      if (toolResultMatch) {
        const toolName = toolResultMatch[1]
        let resultObj = {}
        let isError = false
        try {
          resultObj = JSON.parse(toolResultMatch[2].trim())
          isError = !!resultObj.error
        } catch(e) {
          resultObj = { data: toolResultMatch[2].trim() }
        }

        const Icon = isError ? AlertCircle : CheckCircle2
        const color = isError ? '#ef4444' : '#10b981'
        
        return (
          <div key={i} style={{
            margin: '8px 0', padding: '10px 14px', borderRadius: '8px',
            background: 'rgba(255, 255, 255, 0.02)', border: `1px solid rgba(255,255,255,0.05)`,
            borderLeft: `3px solid ${color}`
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
              <Icon size={14} color={color} />
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{toolName} 执行完毕</span>
            </div>
            <pre style={{ margin: 0, fontSize: 11, color: '#94a3b8', background: 'rgba(0,0,0,0.2)', padding: '6px', borderRadius: 4, whiteSpace: 'pre-wrap', maxHeight: 120, overflow: 'auto' }}>
              {JSON.stringify(resultObj, null, 2).slice(0, 500) + (JSON.stringify(resultObj).length > 500 ? '\n...[已折叠]' : '')}
            </pre>
          </div>
        )
      }

      const mockupMatch = part.match(/\[mockup:(\w+)\]/)
      if (mockupMatch) return <MockupCard key={i} type={mockupMatch[1]} />

      const previewMatch = part.match(/\[preview:(\w+)\]/)
      if (previewMatch) {
        return (
          <div key={i} style={{
            margin: '8px 0', padding: '8px 12px',
            background: 'var(--accent-bg)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)', fontSize: 'var(--text-xs)', color: 'var(--accent)',
            display: 'flex', alignItems: 'center', gap: 6, opacity: 0.8,
          }}>
            预览已更新到右侧面板
          </div>
        )
      }

      const clarifyMatch = part.match(/\[clarify:([^\]]+)\]/)
      if (clarifyMatch) {
        const questions = clarifyMatch[1].split('|')
        return <ClarificationCard key={i} questions={questions} onSubmit={handleClarifySubmit} />
      }

      const askUserMatch = part.match(/\[ask_user:([^\]]+)\]/)
      if (askUserMatch) {
        const raw = askUserMatch[1]
        const segments = raw.split('|').map((s) => s.trim()).filter(Boolean)
        const question = segments[0] || ''
        const options = segments.slice(1, 5).map((seg) => {
          const [labelRaw, ...descParts] = seg.split('::')
          let label = labelRaw.trim()
          let recommended = false
          if (label.startsWith('*')) {
            recommended = true
            label = label.slice(1).trim()
          }
          const description = descParts.join('::').trim()
          return { label, description, recommended }
        })
        return (
          <AskUserCard
            key={i}
            question={question}
            options={options}
            onAnswer={handleAskUserReply}
          />
        )
      }

      const optionsMatch = part.match(/\[options:([^\]]+)\]/)
      if (optionsMatch) {
        const options = optionsMatch[1].split('|')
        return (
          <div key={i} style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '8px 0' }}>
            {options.map((opt, j) => (
              <button key={j} onClick={() => handleOptionClick(opt)} style={{
                padding: '6px 14px', borderRadius: 'var(--radius-full)',
                background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                color: 'var(--text-primary)', fontSize: 'var(--text-xs)', cursor: 'pointer',
              }}>
                {opt}
              </button>
            ))}
          </div>
        )
      }

      const codeMatch = part.match(/```(\w*)\n([\s\S]*?)```/)
      if (codeMatch) {
        const lang = codeMatch[1] || 'text'
        const code = codeMatch[2]
        return (
          <div key={i} className="code-block">
            <div className="code-block-header">
              <span>{lang}</span>
              <button onClick={() => navigator.clipboard.writeText(code)}>
                <Copy size={12} />
              </button>
            </div>
            <pre><code>{code}</code></pre>
          </div>
        )
      }

      return <span key={i}>{part}</span>
    })
  }

  return (
    <div className={`message-row ${isUser ? 'user' : ''}`}>
      {!isUser && (
        <div className="msg-avatar">
          <IconAvatar agentId={message.sender} size={16} />
        </div>
      )}

      <div className="message-content">
        {/* Pin indicator */}
        {isPinned && (
          <div style={{ fontSize: 11, color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 4, marginBottom: 2 }}>
            <Pin size={10} /> 已固定
          </div>
        )}

        {/* 附件预览 */}
        {attachments.length > 0 && (
          <div style={{
            display: 'flex', flexDirection: 'column', gap: 6,
            marginBottom: text ? 8 : 0,
          }}>
            {attachments.map((att, i) => (
              <FileAttachmentCard key={i} attachment={att} />
            ))}
          </div>
        )}

        {isUser ? (
          <div className="message-bubble-user">{renderText(text)}</div>
        ) : (
          <div className="message-bubble-agent">
            {renderText(text)}
            {message.streaming && <span className="streaming-cursor" />}
          </div>
        )}

        {/* Meta + Actions */}
        <div className="message-meta">
          <span className="time">{timeStr}</span>
          {isUser && !message.streaming && (
            <span className={`read-check ${isRead ? 'read' : ''}`}>
              <Check size={10} strokeWidth={3} />
            </span>
          )}
          <div className="message-actions">
            <button onClick={handleReply} title="回复"><Reply size={14} /></button>
            <button onClick={handleCopy} title="复制">{copied ? <Check size={14} /> : <Copy size={14} />}</button>
            {!isUser && !message.streaming && (
              <button onClick={handleRegenerate} title="重新生成"><RefreshCw size={14} /></button>
            )}
            <button onClick={() => togglePinMessage(activeId, message.id)} title="固定消息">
              <Pin size={14} color={isPinned ? 'var(--accent)' : undefined} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
