import React, { useState, useEffect } from 'react'
import { useChatStore } from '../../stores/chatStore'

const AVAILABLE_TOOLS = [
  { id: "code_gen", name: "代码生成", icon: "💻", description: "生成代码片段和完整项目文件" },
  { id: "web_preview", name: "网页预览", icon: "🌐", description: "生成可实时预览的 HTML 页面" },
  { id: "data_analysis", name: "数据分析", icon: "📊", description: "分析数据、发现规律、给出可视化建议" },
  { id: "api_design", name: "API 设计", icon: "🔌", description: "设计 RESTful API 接口和数据模型" },
  { id: "testing", name: "测试用例", icon: "🧪", description: "生成测试代码和测试方案" },
  { id: "doc_writing", name: "文档撰写", icon: "📝", description: "撰写技术文档、README、注释" },
  { id: "svg_mockup", name: "SVG 原型图", icon: "🎨", description: "生成 SVG 线框图和 UI 原型设计" },
  { id: "deploy", name: "部署配置", icon: "🚀", description: "生成 Docker、CI/CD、Nginx 配置" },
  { id: "translation", name: "多语言翻译", icon: "🌍", description: "中英日韩等多语言互译" },
  { id: "creative_writing", name: "创意写作", icon: "✍️", description: "文案、故事、营销内容创作" },
]

const PRESET_EMOJIS = ['🤖', '👤', '📋', '🎨', '⚙️', '🧪', '🚀', '🎯', '🌍', '✍️', '📝', '🐱', '🦁', '🦊', '🐯', '🐼', '🦖', '🦄', '💡', '🔥']

export default function AgentBuilderModal({ onClose, editingAgentId }) {
  const addConversation = useChatStore((s) => s.addConversation)
  const updateConversation = useChatStore((s) => s.updateConversation)
  const setActiveConversation = useChatStore((s) => s.setActiveConversation)

  const [name, setName] = useState('')
  const [avatar, setAvatar] = useState('🤖')
  const [role, setRole] = useState('')
  const [style, setStyle] = useState('友好专业')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [selectedTools, setSelectedTools] = useState([])
  
  const [loading, setLoading] = useState(false)
  const [fetching, setFetching] = useState(false)
  const [error, setError] = useState('')

  // If in Edit Mode, fetch current settings
  useEffect(() => {
    if (editingAgentId) {
      setFetching(true)
      fetch('/api/agents/custom')
        .then((res) => res.json())
        .then((data) => {
          const agent = data.find((a) => a.agent_id === editingAgentId)
          if (agent) {
            setName(agent.name || '')
            setAvatar(agent.avatar || '🤖')
            setRole(agent.role || '')
            setStyle(agent.style || '')
            setSystemPrompt(agent.system_prompt || '')
            setSelectedTools(agent.tools || [])
          }
        })
        .catch((err) => console.error('Failed to load custom agent:', err))
        .finally(() => setFetching(false))
    }
  }, [editingAgentId])

  const toggleTool = (toolId) => {
    setSelectedTools((prev) =>
      prev.includes(toolId) ? prev.filter((id) => id !== toolId) : [...prev, toolId]
    )
  }

  const handleSave = async (e) => {
    e.preventDefault()
    if (!name.trim()) {
      setError('请输入智能体名称')
      return
    }
    if (!systemPrompt.trim()) {
      setError('请输入人物设定（系统提示词）')
      return
    }

    setLoading(true)
    setError('')

    const payload = {
      name: name.trim(),
      avatar,
      role: role.trim() || '自定义智能体',
      style: style.trim() || '友好专业',
      system_prompt: systemPrompt.trim(),
      tools: selectedTools,
    }

    try {
      const url = editingAgentId
        ? `/api/agents/custom/${editingAgentId}`
        : '/api/agents/custom'
      const method = editingAgentId ? 'PUT' : 'POST'

      const resp = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!resp.ok) {
        throw new Error('网络请求出错')
      }

      const resData = await resp.json()
      
      if (editingAgentId) {
        // Edit Mode: sync changes inside ChatStore dynamically
        updateConversation(`conv_${editingAgentId}`, {
          name: payload.name,
          avatar: payload.avatar,
          preview: payload.role,
        })
      } else {
        // Create Mode: append new conversation row
        const newAgent = resData.agent
        if (newAgent) {
          const convId = `conv_${newAgent.agent_id}`
          addConversation({
            id: convId,
            type: 'single',
            agentId: newAgent.agent_id,
            name: newAgent.name,
            avatar: newAgent.avatar,
            messages: [],
            preview: newAgent.role,
          })
          setActiveConversation(convId)
        }
      }

      onClose()
    } catch (err) {
      setError(editingAgentId ? '更新智能体失败，请重试。' : '创建智能体失败，请重试。')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="agent-creator-overlay">
      <div className="agent-creator-modal">
        <div className="agent-creator-header">
          <h2>{editingAgentId ? '✏️ 编辑自定义 Agent' : '🔧 创造新智能体'}</h2>
          <button className="agent-creator-close" onClick={onClose}>✕</button>
        </div>

        {fetching ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '300px', gap: 12, color: 'var(--text-muted)' }}>
            <div className="thinking-spinner" style={{ width: 24, height: 24, borderWidth: 3 }}></div>
            <span>加载智能体配置中...</span>
          </div>
        ) : (
          <form className="agent-creator-form" onSubmit={handleSave}>
            {error && <div className="agent-creator-error">⚠️ {error}</div>}

            <div className="form-row-group">
              <div className="form-group" style={{ flex: 1 }}>
                <label>智能体名称 <span style={{ color: 'var(--accent)' }}>*</span></label>
                <input
                  type="text"
                  placeholder="例如：翻译助手、Python代码审查员"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  maxLength={15}
                  required
                />
              </div>

              <div className="form-group" style={{ width: '100px' }}>
                <label>头像 Emoji</label>
                <input
                  type="text"
                  value={avatar}
                  onChange={(e) => setAvatar(e.target.value)}
                  maxLength={4}
                  style={{ textAlign: 'center', fontSize: 18 }}
                />
              </div>
            </div>

            {/* Presets picker */}
            <div className="form-group">
              <label style={{ fontSize: 11, color: 'var(--text-muted)' }}>预设头像快捷选：</label>
              <div className="preset-emoji-grid">
                {PRESET_EMOJIS.map((emoji) => (
                  <button
                    key={emoji}
                    type="button"
                    className={`preset-emoji-btn ${avatar === emoji ? 'active' : ''}`}
                    onClick={() => setAvatar(emoji)}
                  >
                    {emoji}
                  </button>
                ))}
              </div>
            </div>

            <div className="form-row-group">
              <div className="form-group" style={{ flex: 1 }}>
                <label>角色定位</label>
                <input
                  type="text"
                  placeholder="例如：专注于高级中英翻译"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  maxLength={25}
                />
              </div>

              <div className="form-group" style={{ flex: 1 }}>
                <label>性格风格</label>
                <input
                  type="text"
                  placeholder="例如：幽默、学术严谨"
                  value={style}
                  onChange={(e) => setStyle(e.target.value)}
                  maxLength={20}
                />
              </div>
            </div>

            <div className="form-group">
              <label>人物设定与核心提示词 (System Instructions) <span style={{ color: 'var(--accent)' }}>*</span></label>
              <textarea
                placeholder="请输入智能体的人物画像、行为指南、输出规范和限制条件。它的所有回答都将牢牢遵循这里的设定。"
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                rows={5}
                required
              />
            </div>

            <div className="form-group">
              <label>赋能工具能力（可选）</label>
              <div className="tool-checklist-grid">
                {AVAILABLE_TOOLS.map((tool) => {
                  const isChecked = selectedTools.includes(tool.id)
                  return (
                    <div
                      key={tool.id}
                      className={`tool-check-card ${isChecked ? 'active' : ''}`}
                      onClick={() => toggleTool(tool.id)}
                    >
                      <div className="tool-check-header">
                        <span className="tool-check-icon">{tool.icon}</span>
                        <span className="tool-check-title">{tool.name}</span>
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => {}} // handled by card onClick
                          onClick={(e) => e.stopPropagation()}
                        />
                      </div>
                      <div className="tool-check-desc">{tool.description}</div>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="agent-creator-actions">
              <button type="button" className="creator-cancel-btn" onClick={onClose}>
                取消
              </button>
              <button type="submit" className="creator-submit-btn" disabled={loading}>
                {loading ? '💾 正在保存...' : '💾 确认保存'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
