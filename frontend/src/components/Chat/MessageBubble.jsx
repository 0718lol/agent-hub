import React, { useState } from 'react'
import { Copy, RefreshCw, Reply, Pin, Check, Wrench, Settings2, Globe, FileText, CheckCircle2, AlertCircle, ChevronDown, ChevronRight } from 'lucide-react'
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

// Dify-Style Collapsible Tool Call Component
function ToolCallBlock({ toolName, params }) {
  const [expanded, setExpanded] = useState(false)
  const Icon = TOOL_ICONS[toolName] || Wrench
  const hasParams = Object.keys(params).length > 0

  return (
    <div style={{
      margin: '12px 0',
      borderRadius: '8px',
      background: 'rgba(129, 140, 248, 0.03)',
      border: '1px solid rgba(129, 140, 248, 0.12)',
      overflow: 'hidden',
    }}>
      <div 
        onClick={() => hasParams && setExpanded(!expanded)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '10px 14px',
          background: 'rgba(129, 140, 248, 0.05)',
          cursor: hasParams ? 'pointer' : 'default',
          userSelect: 'none',
        }}
      >
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 24,
          height: 24,
          borderRadius: '6px',
          background: 'rgba(129, 140, 248, 0.12)',
          color: '#818cf8',
        }}>
          <Icon size={14} style={{ animation: 'spin-slow 4s linear infinite' }} />
        </div>
        
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span style={{ fontSize: '13px', fontWeight: 600, color: '#c7d2fe' }}>
            调用工具：{toolName}
          </span>
          <span style={{ fontSize: '10px', color: '#818cf8', opacity: 0.8, letterSpacing: '0.5px' }}>
            System Tool Call
          </span>
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            fontSize: '10px',
            background: 'rgba(129, 140, 248, 0.15)',
            border: '1px solid rgba(129, 140, 248, 0.3)',
            color: '#a5b4fc',
            padding: '2px 8px',
            borderRadius: '10px',
            fontWeight: 500,
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
          }}>
            <span style={{
              width: 5, height: 5, borderRadius: '50%', background: '#818cf8',
              boxShadow: '0 0 6px #818cf8',
            }} />
            执行中...
          </span>
          {hasParams && (
            <span style={{ color: '#94a3b8', display: 'flex', alignItems: 'center' }}>
              {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </span>
          )}
        </div>
      </div>

      {expanded && hasParams && (
        <div style={{
          padding: '12px 14px',
          background: 'rgba(0, 0, 0, 0.25)',
          borderTop: '1px solid rgba(129, 140, 248, 0.08)',
        }}>
          <div style={{ fontSize: '11px', color: '#818cf8', fontWeight: 600, marginBottom: 6 }}>输入参数 (Arguments):</div>
          <pre style={{
            margin: 0,
            fontSize: '11px',
            color: '#cbd5e1',
            fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
          }}>
            {JSON.stringify(params, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

// Dify-Style Collapsible Tool Result Component
function ToolResultBlock({ toolName, resultText }) {
  const [expanded, setExpanded] = useState(false)
  let resultObj = {}
  let isError = false
  try {
    resultObj = JSON.parse(resultText.trim())
    isError = !!resultObj.error
  } catch (e) {
    resultObj = { output: resultText.trim() }
  }

  const Icon = isError ? AlertCircle : CheckCircle2
  const color = isError ? '#f87171' : '#34d399'
  const bg = isError ? 'rgba(239, 68, 68, 0.02)' : 'rgba(16, 185, 129, 0.02)'
  const border = isError ? 'rgba(239, 68, 68, 0.12)' : 'rgba(16, 185, 129, 0.12)'
  const badgeBg = isError ? 'rgba(239, 68, 68, 0.12)' : 'rgba(16, 185, 129, 0.12)'

  const contentStr = JSON.stringify(resultObj, null, 2)
  const isTruncated = contentStr.length > 500
  const displayedContent = expanded ? contentStr : (contentStr.slice(0, 500) + (isTruncated ? '\n\n... [数据已折叠，点击展开查看完整输出]' : ''))

  return (
    <div style={{
      margin: '12px 0',
      borderRadius: '8px',
      background: bg,
      border: `1px solid ${border}`,
      overflow: 'hidden',
    }}>
      <div 
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '10px 14px',
          background: isError ? 'rgba(239, 68, 68, 0.04)' : 'rgba(16, 185, 129, 0.04)',
          cursor: 'pointer',
          userSelect: 'none',
        }}
      >
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 24,
          height: 24,
          borderRadius: '6px',
          background: badgeBg,
          color: color,
        }}>
          <Icon size={14} />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {toolName} {isError ? '执行失败' : '执行成功'}
          </span>
          <span style={{ fontSize: '10px', color: 'var(--text-muted)', letterSpacing: '0.5px' }}>
            Tool Output Received
          </span>
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            fontSize: '10px',
            background: badgeBg,
            border: `1px solid ${border}`,
            color: color,
            padding: '2px 8px',
            borderRadius: '10px',
            fontWeight: 500,
          }}>
            {isError ? 'Failed' : 'Success'}
          </span>
          <span style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center' }}>
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        </div>
      </div>

      <div style={{
        padding: '12px 14px',
        background: 'rgba(0, 0, 0, 0.25)',
        borderTop: `1px solid ${border}`,
      }}>
        <pre 
          onClick={() => !expanded && setExpanded(true)}
          style={{
            margin: 0,
            fontSize: '11px',
            color: isError ? '#fca5a5' : '#a7f3d0',
            fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
            maxHeight: expanded ? '400px' : '150px',
            overflow: 'auto',
            cursor: !expanded ? 'pointer' : 'text',
          }}
        >
          {displayedContent}
        </pre>
      </div>
    </div>
  )
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
        return <ToolCallBlock key={i} toolName={toolName} params={params} />
      }

      // Tool Result Match
      const toolResultMatch = part.match(/\[工具结果: ([^\]]+)\]\n([\s\S]*?)\n\n请基于以上工具结果继续回复用户。/)
      if (toolResultMatch) {
        const toolName = toolResultMatch[1]
        const resultText = toolResultMatch[2]
        return <ToolResultBlock key={i} toolName={toolName} resultText={resultText} />
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
