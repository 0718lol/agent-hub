import React, { useState, useEffect } from 'react'
import { Check, X, Plus, Trash2, ExternalLink, Key } from 'lucide-react'
import { useAgentStore } from '../../stores/agentStore'
import IconAvatar from '../IconAvatar'
import AgentCreator from './AgentCreator'

const CONFIG_PROMPTS = {
  claude_code: {
    title: 'Claude Code 需要配置 API Key',
    icon: '🟣',
    description: 'Claude Code 由 Anthropic 提供，需要有效的 API Key 才能使用。',
    steps: [
      '前往 console.anthropic.com 注册账号',
      '在 API Keys 页面创建新的 Key',
      '在设置中填入 Anthropic API Key',
    ],
    action: '配置 Anthropic API Key',
  },
  codex: {
    title: 'Codex 需要连接本机 CLI',
    icon: '🟢',
    description: 'Agent Hub 会调用这台电脑上已登录的 Codex，并为每个对话保持独立会话。',
    steps: [
      '确认本机 Codex CLI 已安装并登录',
      '在设置中选择项目目录和工作区权限',
      '连接后即可从对话中调用 Codex',
    ],
    action: '连接 Codex 本机 CLI',
  },
}

export default function AgentSelector({ onSelect, onClose, multiSelect = false, selected = [], onToggle }) {
  const agents = useAgentStore((s) => s.agents)
  const deletedPresetIds = useAgentStore((s) => s.deletedPresetIds)
  const loadCustomAgents = useAgentStore((s) => s.loadCustomAgents)
  const removeAgent = useAgentStore((s) => s.removeAgent)
  const adapterStatus = useAgentStore((s) => s.adapterStatus)
  const fetchAdapterStatus = useAgentStore((s) => s.fetchAdapterStatus)

  const [showCreator, setShowCreator] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)
  const [configPromptAgent, setConfigPromptAgent] = useState(null)

  // Exclude builder and deleted presets
  const visibleAgents = agents.filter(
    (a) => a.agent_id !== 'agent_builder'
      && a.agent_id !== 'agent_pm'
      && !deletedPresetIds.includes(a.agent_id)
  )

  useEffect(() => {
    loadCustomAgents()
    fetchAdapterStatus()
  }, [])

  const isExternalConfigured = (agent) => {
    if (agent.agent_type !== 'external') return true
    const status = adapterStatus[agent.agent_id]
    return status?.configured ?? false
  }

  const handleDelete = async (agentId) => {
    await removeAgent(agentId)
    setConfirmDeleteId(null)
  }

  const handleCreateClick = () => {
    setShowCreator(true)
  }

  return (
    <>
      {/* 选择 Agent 弹窗 */}
      {!showCreator && (
        <div className="agent-selector-overlay" onClick={onClose}>
          <div className="agent-selector" onClick={(e) => e.stopPropagation()}>
            <div className="agent-selector-header">
              <span className="agent-selector-title">
                {multiSelect ? '选择 Agent' : '选择 Agent 开始对话'}
              </span>
              <button className="agent-selector-close" onClick={onClose}>
                <X size={18} />
              </button>
            </div>

            <div className="agent-selector-list">
              {visibleAgents.map((agent) => {
                const isSelected = selected.includes(agent.agent_id)
                const isConfirming = confirmDeleteId === agent.agent_id

                if (isConfirming) {
                  return (
                    <div key={agent.agent_id} className="agent-delete-confirm">
                      <span>确定删除「{agent.name}」？</span>
                      <div className="agent-delete-confirm-actions">
                        <button
                          className="agent-delete-btn danger"
                          onClick={() => handleDelete(agent.agent_id)}
                        >
                          删除
                        </button>
                        <button
                          className="agent-delete-btn"
                          onClick={() => setConfirmDeleteId(null)}
                        >
                          取消
                        </button>
                      </div>
                    </div>
                  )
                }

                return (
                  <button
                    key={agent.agent_id}
                    className={`agent-selector-item ${isSelected ? 'selected' : ''}`}
                    onClick={() => {
                      if (!isExternalConfigured(agent)) {
                        setConfigPromptAgent(agent)
                        return
                      }
                      if (multiSelect && onToggle) {
                        onToggle(agent.agent_id)
                      } else {
                        onSelect(agent.agent_id)
                      }
                    }}
                  >
                    <div className="agent-selector-avatar">
                      <IconAvatar agentId={agent.agent_id} size={22} />
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="agent-selector-name">
                        {agent.name}
                        {agent.agent_type === 'external' && !isExternalConfigured(agent) && (
                          <span style={{ fontSize: 11, color: 'var(--orange)', marginLeft: 6 }}>🔒 需配置</span>
                        )}
                      </div>
                      <div className="agent-selector-role">{agent.role}</div>
                    </div>
                    {isSelected && (
                      <div className="agent-selector-check"><Check size={16} /></div>
                    )}
                    <button
                      className="agent-selector-delete"
                      onClick={(e) => {
                        e.stopPropagation()
                        setConfirmDeleteId(agent.agent_id)
                      }}
                      title="删除此 Agent"
                    >
                      <Trash2 size={14} />
                    </button>
                  </button>
                )
              })}

              {visibleAgents.length === 0 && (
                <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 'var(--text-sm)', padding: 'var(--space-5) 0' }}>
                  暂无可选 Agent
                </div>
              )}
            </div>

            <button className="agent-create-entry" onClick={handleCreateClick}>
              <Plus size={16} />
              <span>自定义 Agent</span>
            </button>
          </div>
        </div>
      )}

      {/* 未配置 API Key 提示浮窗 */}
      {configPromptAgent && (() => {
        const prompt = CONFIG_PROMPTS[configPromptAgent.agent_id] || CONFIG_PROMPTS.claude_code
        return (
          <div
            style={{
              position: 'fixed', inset: 0, zIndex: 1100,
              background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
            onClick={() => setConfigPromptAgent(null)}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                background: 'var(--bg-primary)', borderRadius: 16,
                border: '1px solid var(--border)',
                boxShadow: '0 20px 60px rgba(0,0,0,0.2)',
                width: 420, maxWidth: '90vw', padding: 28,
                animation: 'scaleUp 0.2s ease-out',
              }}
            >
              {/* 头部 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                <div style={{
                  width: 48, height: 48, borderRadius: 12,
                  background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 24,
                }}>
                  <IconAvatar agentId={configPromptAgent.agent_id} size={28} />
                </div>
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)' }}>
                    {prompt.title}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                    {configPromptAgent.name}
                  </div>
                </div>
                <button
                  onClick={() => setConfigPromptAgent(null)}
                  style={{
                    marginLeft: 'auto', background: 'none', border: 'none',
                    color: 'var(--text-muted)', cursor: 'pointer', padding: 4,
                  }}
                >
                  <X size={18} />
                </button>
              </div>

              {/* 说明 */}
              <div style={{
                fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6,
                marginBottom: 16,
              }}>
                {prompt.description}
              </div>

              {/* 步骤 */}
              <div style={{
                background: 'var(--bg-secondary)', borderRadius: 10,
                border: '1px solid var(--border)', padding: 16, marginBottom: 20,
              }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 10 }}>
                  配置步骤：
                </div>
                {prompt.steps.map((step, i) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'flex-start', gap: 8,
                    fontSize: 12, color: 'var(--text-secondary)', marginBottom: i < prompt.steps.length - 1 ? 8 : 0,
                  }}>
                    <span style={{
                      width: 18, height: 18, borderRadius: '50%',
                      background: 'var(--accent)', color: 'white',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 10, fontWeight: 600, flexShrink: 0, marginTop: 1,
                    }}>
                      {i + 1}
                    </span>
                    <span>{step}</span>
                  </div>
                ))}
              </div>

              {/* 操作按钮 */}
              <div style={{ display: 'flex', gap: 10 }}>
                <button
                  onClick={() => setConfigPromptAgent(null)}
                  style={{
                    flex: 1, padding: '10px 16px', borderRadius: 8,
                    background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                    color: 'var(--text-secondary)', fontSize: 13, fontWeight: 500,
                    cursor: 'pointer',
                  }}
                >
                  稍后配置
                </button>
                <button
                  onClick={() => {
                    setConfigPromptAgent(null)
                    // 打开设置面板（通过触发全局事件）
                    window.dispatchEvent(new CustomEvent('open-settings', { detail: { tab: 'llm' } }))
                  }}
                  style={{
                    flex: 1, padding: '10px 16px', borderRadius: 8,
                    background: 'var(--accent)', border: 'none',
                    color: 'white', fontSize: 13, fontWeight: 600,
                    cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                  }}
                >
                  <Key size={14} />
                  {prompt.action}
                </button>
              </div>
            </div>
          </div>
        )
      })()}

      {/* 创建 Agent 弹窗（独立层级，更高 z-index） */}
      {showCreator && (
        <AgentCreator
          onClose={() => { setShowCreator(false); onClose() }}
          onBack={() => setShowCreator(false)}
        />
      )}
    </>
  )
}
