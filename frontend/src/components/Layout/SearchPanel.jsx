import React, { useState, useMemo } from 'react'
import { Search } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import IconAvatar from '../IconAvatar'

export default function SearchPanel({ onSelect }) {
  const conversations = useChatStore((s) => s.conversations)
  const agents = useAgentStore((s) => s.agents)
  const [query, setQuery] = useState('')

  const results = useMemo(() => {
    if (!query.trim()) return []
    const q = query.toLowerCase()
    const matches = []

    for (const conv of conversations) {
      let convMatch = false
      const msgMatches = []

      // 匹配会话名称
      if (conv.name?.toLowerCase().includes(q)) {
        convMatch = true
      }

      // 匹配消息内容
      for (const msg of conv.messages || []) {
        const text = msg.content?.text || ''
        if (text.toLowerCase().includes(q)) {
          msgMatches.push({ ...msg, convId: conv.id, convName: conv.name })
        }
      }

      if (convMatch || msgMatches.length > 0) {
        matches.push({
          id: conv.id,
          name: conv.name,
          type: conv.type,
          agentId: conv.agentId,
          convMatch,
          msgCount: msgMatches.length,
          previews: msgMatches.slice(0, 3).map((m) => ({
            text: m.content?.text?.substring(0, 80) + (m.content?.text?.length > 80 ? '...' : ''),
            timestamp: m.timestamp,
          })),
        })
      }
    }

    return matches.sort((a, b) => b.msgCount - a.msgCount)
  }, [query, conversations])

  return (
    <div className="search-panel">
      {/* 搜索输入框 */}
      <div className="search-panel-input-wrap">
        <Search size={16} className="search-panel-input-icon" />
        <input
          className="search-panel-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索对话记录..."
          autoFocus
        />
      </div>

      {/* 搜索结果 */}
      <div className="search-panel-results">
        {!query.trim() && (
          <div className="search-panel-empty">
            <Search size={32} style={{ opacity: 0.3 }} />
            <span>输入关键词搜索对话记录</span>
          </div>
        )}

        {query.trim() && results.length === 0 && (
          <div className="search-panel-empty">
            <span>未找到匹配的对话</span>
          </div>
        )}

        {results.map((item) => {
          const agent = agents.find((a) => a.agent_id === item.agentId)
          return (
            <button
              key={item.id}
              className="search-result-item"
              onClick={() => onSelect(item.id)}
            >
              <div className="search-result-avatar">
                {item.type === 'group' ? (
                  <IconAvatar iconKey="group" size={18} />
                ) : (
                  <IconAvatar agentId={item.agentId} size={18} />
                )}
              </div>
              <div className="search-result-info">
                <div className="search-result-name">
                  {item.name}
                  {item.type === 'group' && (
                    <span className="search-result-badge">群聊</span>
                  )}
                </div>
                {item.previews.length > 0 && (
                  <div className="search-result-previews">
                    {item.previews.map((p, i) => (
                      <div key={i} className="search-result-preview">
                        {p.text}
                      </div>
                    ))}
                  </div>
                )}
                {item.convMatch && item.previews.length === 0 && (
                  <div className="search-result-preview" style={{ color: 'var(--text-muted)' }}>
                    {agent?.role || '会话名称匹配'}
                  </div>
                )}
              </div>
              {item.msgCount > 1 && (
                <span className="search-result-count">{item.msgCount} 条</span>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
