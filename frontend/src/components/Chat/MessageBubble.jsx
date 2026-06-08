import styles from './MessageBubble.module.css'
import React, { useState, useEffect, useRef } from 'react'
import { Copy, RefreshCw, Reply, Pin, Check, Wrench, Settings2, Globe, FileText, CheckCircle2, AlertCircle, ChevronDown, ChevronRight, Trash2, Share2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { useAgentStore } from '../../stores/agentStore'
import { useChatStore } from '../../stores/chatStore'
import { useCanvasStore } from '../../stores/canvasStore'
import MockupCard from './MockupCard'
import ClarificationCard from './ClarificationCard'
import AskUserCard from './AskUserCard'
import FileAttachmentCard from './FileAttachmentCard'
import IconAvatar from '../IconAvatar'
import { PREVIEW_HTML } from '../Canvas/previewHtml'
import { wsClient } from '../../utils/websocket'

const MD_COMPONENTS = {
  p: ({ children }) => <div style={{ margin: '0.2em 0', lineHeight: 1.55 }}>{children}</div>,
  ul: ({ children }) => <ul style={{ margin: '0.3em 0', paddingLeft: 20 }}>{children}</ul>,
  ol: ({ children }) => <ol style={{ margin: '0.3em 0', paddingLeft: 22 }}>{children}</ol>,
  li: ({ children }) => <li style={{ margin: '0.1em 0', lineHeight: 1.5 }}>{children}</li>,
  h1: ({ children }) => <div style={{ fontSize: 16, margin: '0.45em 0 0.25em', fontWeight: 700 }}>{children}</div>,
  h2: ({ children }) => <div style={{ fontSize: 15, margin: '0.45em 0 0.25em', fontWeight: 700 }}>{children}</div>,
  h3: ({ children }) => <div style={{ fontSize: 14, margin: '0.4em 0 0.2em', fontWeight: 600 }}>{children}</div>,
  strong: ({ children }) => <strong style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{children}</strong>,
  em: ({ children }) => <em style={{ fontStyle: 'italic' }}>{children}</em>,
  code: ({ children }) => (
    <code style={{
      background: 'rgba(99,102,241,0.16)', color: 'var(--accent)',
      padding: '1px 6px', borderRadius: 4,
      fontSize: '0.9em', fontFamily: 'Consolas, Monaco, monospace',
    }}>{children}</code>
  ),
  blockquote: ({ children }) => (
    <blockquote style={{
      borderLeft: '3px solid rgba(99,102,241,0.45)',
      paddingLeft: 10, margin: '0.45em 0',
      color: 'var(--text-secondary)',
    }}>{children}</blockquote>
  ),
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)', textDecoration: 'underline' }}>{children}</a>
  ),
  hr: () => <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '0.6em 0' }} />,
}

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
    <div className={styles.toolCallBlock}>
      <div
        onClick={() => hasParams && setExpanded(!expanded)}
        className={`${styles.toolCallHeader} ${!hasParams ? styles.toolCallHeaderNoParams : ''}`}
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        aria-label={`工具调用 ${toolName}`}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); hasParams && setExpanded(!expanded) } }}
      >
        <div className={styles.toolCallIcon}>
          <Icon size={14} style={{ animation: 'spin-slow 4s linear infinite' }} />
        </div>

        <div className={styles.toolCallInfo}>
          <span className={styles.toolCallName}>
            调用工具：{toolName}
          </span>
          <span className={styles.toolCallLabel}>
            System Tool Call
          </span>
        </div>

        <div className={styles.toolCallRight}>
          <span className={styles.toolCallBadge}>
            <span className={styles.toolCallDot} />
            System Call
          </span>
          {hasParams && (
            <span className={styles.toolCallChevron}>
              {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </span>
          )}
        </div>
      </div>

      {expanded && hasParams && (
        <div className={styles.toolCallExpandBody}>
          <div className={styles.toolCallArgLabel}>输入参数 (Arguments):</div>
          <pre className={styles.toolCallArgPre}>
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
    <div className={`${styles.toolResultBlock} ${isError ? styles.toolResultBlockError : styles.toolResultBlockSuccess}`}>
      <div
        onClick={() => setExpanded(!expanded)}
        className={`${styles.toolResultHeader} ${isError ? styles.toolResultHeaderError : styles.toolResultHeaderSuccess}`}
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        aria-label={`${toolName} ${isError ? '执行失败' : '执行成功'}`}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded(!expanded) } }}
      >
        <div className={`${styles.toolResultIcon} ${isError ? styles.toolResultIconError : styles.toolResultIconSuccess}`}>
          <Icon size={14} />
        </div>

        <div className={styles.toolResultInfo}>
          <span className={styles.toolResultName}>
            {toolName} {isError ? '执行失败' : '执行成功'}
          </span>
          <span className={styles.toolResultLabel}>
            Tool Output Received
          </span>
        </div>

        <div className={styles.toolCallRight}>
          <span className={`${styles.toolResultBadge} ${isError ? styles.toolResultBadgeError : styles.toolResultBadgeSuccess}`}>
            {isError ? 'Failed' : 'Success'}
          </span>
          <span className={styles.toolResultChevron}>
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        </div>
      </div>

      <div className={`${styles.toolResultBody} ${isError ? styles.toolResultBodyError : styles.toolResultBodySuccess}`}>
        <pre
          onClick={() => !expanded && setExpanded(true)}
          className={`${styles.toolResultPre} ${isError ? styles.toolResultPreError : styles.toolResultPreSuccess} ${expanded ? styles.toolResultPreExpanded : ''}`}>
          {displayedContent}
        </pre>
      </div>
    </div>
  )
}

export default function MessageBubble({ message, isPinned, isLast }) {
  const agents = useAgentStore((s) => s.agents)
  const activeId = useChatStore((s) => s.activeConversationId)
  const addMessage = useChatStore((s) => s.addMessage)
  const deleteMessage = useChatStore((s) => s.deleteMessage)
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

  const handleDelete = () => {
    if (window.confirm('确定删除这条消息吗？')) {
      deleteMessage(activeId, message.id)
    }
  }

  const handleShare = async () => {
    const shareData = { title: 'AgentHub 消息', text }
    if (navigator.share) {
      try { await navigator.share(shareData) } catch {}
    } else {
      navigator.clipboard.writeText(text)
      alert('消息内容已复制到剪贴板')
    }
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

  // Markdown 渲染组件配置
  const markdownComponents = {
    code({ node, inline, className, children, ...props }) {
      const match = /language-(\w+)/.exec(className || '')
      const codeStr = String(children).replace(/\n$/, '')
      if (!inline && match) {
        return (
          <div className="code-block">
            <div className="code-block-header">
              <span>{match[1]}</span>
              <button onClick={() => navigator.clipboard.writeText(codeStr)} aria-label={`复制 ${match[1]} 代码`}>
                <Copy size={12} />
              </button>
            </div>
            <SyntaxHighlighter
              style={oneDark}
              language={match[1]}
              PreTag="div"
              customStyle={{ margin: 0, borderRadius: '0 0 8px 8px', fontSize: 13, background: 'var(--code-bg)' }}
            >
              {codeStr}
            </SyntaxHighlighter>
          </div>
        )
      }
      return <code className="markdown-inline-code" {...props}>{children}</code>
    },
    table({ children }) {
      return <div className="markdown-table-wrap"><table>{children}</table></div>
    },
    a({ children, href, ...props }) {
      return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>
    },
  }

  const renderMarkdown = (text) => (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
      {text}
    </ReactMarkdown>
  )

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
          <div key={i} className={styles.optionsRow}>
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
              <button onClick={() => navigator.clipboard.writeText(code)} aria-label={`复制 ${lang} 代码`}>
                <Copy size={12} />
              </button>
            </div>
            <pre><code>{code}</code></pre>
          </div>
        )
      }

      return <ReactMarkdown key={i} components={MD_COMPONENTS}>{part}</ReactMarkdown>
    })
  }

  const senderName = isUser ? '你' : (agent?.name || message.sender)

  return (
    <div className={`message-row ${isUser ? 'user' : ''}`} role="article" aria-label={`${senderName}的消息`}>
      {!isUser && (
        <div className="msg-avatar">
          <IconAvatar agentId={message.sender} size={16} />
        </div>
      )}

      <div className="message-content">
        {/* Pin indicator */}
        {isPinned && (
          <div className={styles.pinIndicator}>
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
            <button onClick={handleCopy} title="复制">{copied ? <Check size={14} /> : <Copy size={14} />}</button>
            <button onClick={handleDelete} title="删除"><Trash2 size={14} /></button>
            <button onClick={handleShare} title="分享"><Share2 size={14} /></button>
            {!isUser && !message.streaming && isLast && (
              <button onClick={handleRegenerate} title="重新生成"><RefreshCw size={14} /></button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
