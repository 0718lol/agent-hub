import React, { useState, useMemo, useCallback, useRef } from 'react'
import { Plus, Settings, Pin, MoreHorizontal, X, PanelLeftClose, PanelLeftOpen, ChevronRight, Search, Bot, Wrench, BookOpen, Cpu, FolderOpen, Hammer, Trash2, Lock, Edit3 } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { useTabStore } from '../../stores/tabStore'
import SettingsPanel from './SettingsPanel'
import IconAvatar from '../IconAvatar'
import AgentCreator from '../Chat/AgentCreator'

/* 资源子类定义 */
const RESOURCE_CATEGORIES = [
  { key: 'skills', label: '技能', icon: Wrench },
  { key: 'models', label: '模型', icon: Cpu },
]

export default function Sidebar({ mobileOpen = false, onClose = () => {} }) {
  const conversations = useChatStore((s) => s.conversations)
  const agents = useAgentStore((s) => s.agents)
  const togglePin = useChatStore((s) => s.togglePin)
  const archiveConversation = useChatStore((s) => s.archiveConversation)
  const reorderConversations = useChatStore((s) => s.reorderConversations)
  const typingAgents = useChatStore((s) => s.typingAgents)

  const openTab = useTabStore((s) => s.openTab)
  const activeTabId = useTabStore((s) => s.activeTabId)
  const openTabs = useTabStore((s) => s.openTabs)
  const activeTab = openTabs.find((t) => t.id === activeTabId)
  const activeAgentId = activeTab?.agentId

  const [collapsed, setCollapsed] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [showCreator, setShowCreator] = useState(false)
  const [contextMenu, setContextMenu] = useState(null)
  const [dragIndex, setDragIndex] = useState(null)
  const [confirmDeleteAgentId, setConfirmDeleteAgentId] = useState(null)
  const [renameDialog, setRenameDialog] = useState(null) // { convId, name } or null
  const [renameError, setRenameError] = useState('')
  const [tooltip, setTooltip] = useState(null) // { text, x, y } or null

  // 分组折叠状态
  const [agentsExpanded, setAgentsExpanded] = useState(true)
  const [resourcesExpanded, setResourcesExpanded] = useState(true)
  const [resourceExpanded, setResourceExpanded] = useState({})
  const [searchQuery, setSearchQuery] = useState('')

  // 新对话计数器，用于生成默认名称 "新对话1", "新对话2" ...
  const convCounterRef = useRef(1)

  // PM 不可删除的 ID
  const PM_ID = 'agent_pm'

  // 智能体列表：PM 常驻第一，其余按 agentStore 顺序，排除 builder
  const sidebarAgents = useMemo(() => {
    const visible = agents.filter((a) =>
      a.agent_id !== 'agent_builder' &&
      !useAgentStore.getState().deletedPresetIds.includes(a.agent_id)
    )
    // PM 固定第一位
    const pm = visible.find((a) => a.agent_id === PM_ID)
    const rest = visible.filter((a) => a.agent_id !== PM_ID)
    return pm ? [pm, ...rest] : rest
  }, [agents])

  // 当前激活 agent 的历史对话（过滤 + 搜索）
  const historyConversations = useMemo(() => {
    let filtered = conversations
      .filter((c) => !c.archived)

    // 按当前 agent 过滤：single 类型按 agentId 匹配
    if (activeAgentId) {
      filtered = filtered.filter((c) =>
        c.type === 'single' ? c.agentId === activeAgentId : false
      )
    }

    // 搜索过滤
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      filtered = filtered.filter((c) =>
        c.name.toLowerCase().includes(q) ||
        (c.messages || []).some((m) => (m.content?.text || '').toLowerCase().includes(q))
      )
    }

    return filtered.sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
      return (b.updatedAt || 0) - (a.updatedAt || 0)
    })
  }, [conversations, activeAgentId, searchQuery])

  const handleContextMenu = useCallback((e, convId) => {
    e.preventDefault()
    setContextMenu({ convId, x: e.clientX, y: e.clientY })
  }, [])

  const closeContextMenu = () => setContextMenu(null)

  // 检查同一 agent 下是否存在重名对话
  const checkDuplicateName = useCallback((convId, newName) => {
    const conv = useChatStore.getState().conversations.find((c) => c.id === convId)
    if (!conv) return false
    const agentId = conv.agentId
    return useChatStore.getState().conversations.some(
      (c) => c.id !== convId && c.agentId === agentId && c.name === newName
    )
  }, [])

  const handleDeleteAgent = async (e, agentId) => {
    e.stopPropagation()
    if (window.confirm('确定要删除该 Agent 吗？此操作不可撤销。')) {
      await useAgentStore.getState().removeAgent(agentId)
      setConfirmDeleteAgentId(null)
    }
  }

  const formatTime = (ts) => {
    if (!ts) return ''
    const d = new Date(ts)
    const now = new Date()
    if (d.toDateString() === now.toDateString())
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  }

  const toggleResource = (key) => {
    setResourceExpanded((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  // HTML5 Drag
  const handleDragStart = useCallback((e, index) => {
    setDragIndex(index)
    e.dataTransfer.effectAllowed = 'move'
  }, [])

  const handleDragOver = useCallback((e) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const handleDrop = useCallback((e, dropIndex) => {
    e.preventDefault()
    if (dragIndex !== null && dragIndex !== dropIndex) {
      reorderConversations(dragIndex, dropIndex)
    }
    setDragIndex(null)
  }, [dragIndex, reorderConversations])

  // Collapsed mode: only show section icons
  if (collapsed) {
    return (
      <>
        <div className={`sidebar ${mobileOpen ? 'mobile-open' : ''} collapsed`}>
          <div className="sidebar-header" style={{ justifyContent: 'center', padding: 'var(--space-3) var(--space-1)' }}>
            <button className="sidebar-collapse-btn" onClick={() => setCollapsed(false)} title="展开侧边栏">
              <PanelLeftOpen size={18} />
            </button>
          </div>

          <div className="sidebar-section">
            <div className="sidebar-section-header" style={{ justifyContent: 'center' }} title="智能体">
              <Bot size={20} style={{ color: 'var(--text-secondary)' }} />
            </div>
          </div>

          <div className="sidebar-section">
            <div className="sidebar-section-header" style={{ justifyContent: 'center' }} title="资源">
              <FolderOpen size={20} style={{ color: 'var(--text-secondary)' }} />
            </div>
          </div>

          <div style={{ flex: 1 }} />

          <div className="sidebar-footer">
            <div className="sidebar-footer-item" onClick={() => setShowSettings(true)} title="设置" style={{ justifyContent: 'center' }}>
              <Settings size={16} />
            </div>
          </div>
        </div>

        {/* Modals */}
        {showCreator && <AgentCreator onClose={() => setShowCreator(false)} onBack={() => setShowCreator(false)} />}
        {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} />}
      </>
    )
  }

  // 展开状态
  return (
    <>
      <div className={`sidebar ${mobileOpen ? 'mobile-open' : ''}`}>
        {/* Header */}
        <div className="sidebar-header">
          <span className="sidebar-logo">AgentHub</span>
          <button className="sidebar-collapse-btn" onClick={() => setCollapsed(true)} title="收起侧边栏">
            <PanelLeftClose size={18} />
          </button>
          <button className="hamburger-btn" onClick={onClose} title="关闭菜单">
            <X size={18} />
          </button>
        </div>

        <div className="sidebar-scroll">
        {/* ===== 智能体分组 ===== */}
        <div className="sidebar-section">
          <div className="sidebar-section-header" onClick={() => setAgentsExpanded(!agentsExpanded)}>
            <div className="sidebar-section-title" style={{ fontSize: 'var(--text-sm)', textTransform: 'none', letterSpacing: 0 }}>
              <ChevronRight size={14} className={`sidebar-section-chevron ${agentsExpanded ? 'open' : ''}`} />
              <Bot size={16} />
              <span>智能体</span>
            </div>
            <button
              className="sidebar-section-add"
              onClick={(e) => { e.stopPropagation(); setShowCreator(true) }}
              title="新建Agent"
              onMouseEnter={(e) => {
                const rect = e.currentTarget.getBoundingClientRect()
                setTooltip({ text: '新建Agent', x: rect.left + rect.width / 2, y: rect.top - 8 })
              }}
              onMouseLeave={() => setTooltip(null)}
            >
              <Plus size={14} />
            </button>
          </div>

          {agentsExpanded && (
            <div style={{ paddingBottom: 'var(--space-1)' }}>
              {sidebarAgents.map((agent) => {
                const isActive = activeAgentId === agent.agent_id
                const isAgentRunning = openTabs.some((t) => t.agentId === agent.agent_id)
                return (
                  <div
                    key={agent.agent_id}
                    className={`conversation-item ${isActive ? 'active' : ''}`}
                    style={{ paddingLeft: 'var(--space-5)' }}
                    onClick={() => {
                      // 生成唯一对话 ID
                      const convId = `conv_${agent.agent_id}_${Date.now()}`
                      // 计算 "新对话N" 名称（不与该 agent 已有对话重名）
                      const agentConvs = useChatStore.getState().conversations.filter(
                        (c) => c.agentId === agent.agent_id && !c.archived
                      )
                      const usedNames = new Set(agentConvs.map((c) => c.name))
                      let n = agentConvs.length + 1
                      let convName = `新对话${n}`
                      while (usedNames.has(convName)) {
                        n++
                        convName = `新对话${n}`
                      }
                      // 创建本地对话
                      useChatStore.getState().addConversation({
                        id: convId,
                        type: 'single',
                        agentId: agent.agent_id,
                        name: convName,
                        avatar: null,
                        messages: [],
                        pinned: false,
                        unread: false,
                        updatedAt: Date.now(),
                      })
                      // 同步到后端
                      fetch('/api/conversations', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                          id: convId,
                          type: 'single',
                          name: convName,
                          agent_id: agent.agent_id,
                        }),
                      }).catch(() => {})
                      openTab(convId, convName, agent.agent_id)
                    }}
                  >
                    <div className="conv-avatar" style={{ width: 32, height: 32 }}>
                      <IconAvatar agentId={agent.agent_id} size={18} />
                    </div>
                    <div className="conv-info">
                      <div className="conv-name">{agent.name}</div>
                      <div className="conv-status conv-status-idle">{agent.role}</div>
                    </div>
                    <span className="online-dot" style={{ background: isAgentRunning ? 'var(--green)' : 'var(--red, #ef4444)' }} title={isAgentRunning ? '运行中' : '已停止'} />
                    {agent.agent_id.startsWith('agent_custom_') ? (
                      <button
                        className="agent-row-delete"
                        onClick={(e) => handleDeleteAgent(e, agent.agent_id)}
                        title="删除"
                      >
                        <Trash2 size={14} />
                      </button>
                    ) : (
                      <span className="agent-row-lock" title="默认agent不允许删除">
                        <Lock size={14} />
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* ===== 资源分组 ===== */}
        <div className="sidebar-section">
          <div className="sidebar-section-header" onClick={() => setResourcesExpanded(!resourcesExpanded)}>
            <div className="sidebar-section-title" style={{ fontSize: 'var(--text-sm)', textTransform: 'none', letterSpacing: 0 }}>
              <ChevronRight size={14} className={`sidebar-section-chevron ${resourcesExpanded ? 'open' : ''}`} />
              <FolderOpen size={16} />
              <span>资源</span>
            </div>
            <button className="sidebar-section-add" onClick={(e) => e.stopPropagation()} title="资源" style={{ visibility: 'hidden' }}>
              <Plus size={14} />
            </button>
          </div>

          {resourcesExpanded && (
            <div style={{ paddingBottom: 'var(--space-1)' }}>
              {RESOURCE_CATEGORIES.map((cat) => {
                const isOpen = resourceExpanded[cat.key] || false
                const CatIcon = cat.icon
                const addTitle = `新建${cat.label}`
                return (
                  <div key={cat.key}>
                    <div
                      className="sidebar-section-header"
                      onClick={() => toggleResource(cat.key)}
                      style={{ paddingLeft: 'var(--space-5)' }}
                    >
                      <div className="sidebar-section-title" style={{ fontSize: 'var(--text-xs)' }}>
                        <ChevronRight size={12} className={`sidebar-section-chevron ${isOpen ? 'open' : ''}`} />
                        <CatIcon size={14} />
                        <span style={{ textTransform: 'none', letterSpacing: 0 }}>{cat.label}</span>
                      </div>
                      <button
                        className="sidebar-section-add"
                        onClick={(e) => e.stopPropagation()}
                        title={addTitle}
                        onMouseEnter={(e) => {
                          const rect = e.currentTarget.getBoundingClientRect()
                          setTooltip({ text: addTitle, x: rect.left + rect.width / 2, y: rect.top - 8 })
                        }}
                        onMouseLeave={() => setTooltip(null)}
                      >
                        <Plus size={14} />
                      </button>
                    </div>
                    {isOpen && (
                      <div style={{ padding: '0 var(--space-4) var(--space-1)', fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                        {/* 子类内容预留 */}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* ===== 新对话 + 搜索 + 历史对话 ===== */}
        <div className="sidebar-new-conv-wrap">
          <div className="sidebar-new-conv-btn" onClick={() => {
            if (!activeAgentId) return
            const convId = `conv_${activeAgentId}_${Date.now()}`
            const defaultName = `新对话${convCounterRef.current}`
            convCounterRef.current += 1
            useChatStore.getState().addConversation({
              id: convId, type: 'single', agentId: activeAgentId,
              name: defaultName, avatar: null,
              messages: [], pinned: false, unread: false, updatedAt: Date.now(),
            })
            openTab(convId, defaultName, activeAgentId)
          }}>
            <Plus size={16} />
            <span>新对话</span>
          </div>
        </div>

        <div className="sidebar-search-wrap" style={{ position: 'relative' }}>
          <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input
            type="text"
            placeholder="搜索对话..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ paddingLeft: 30 }}
          />
        </div>

        <div className="sidebar-history-label">历史对话</div>

        <div className="sidebar-history-list">
          {historyConversations.length === 0 && !searchQuery.trim() ? null : historyConversations.length === 0 ? (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 'var(--text-xs)', padding: 'var(--space-3)' }}>
              无匹配对话
            </div>
          ) : (
            historyConversations.map((conv, i) => {
              const openConvIds = new Set(openTabs.map((t) => t.convId))
              return (
                <div
                  key={conv.id}
                  className={`conversation-item ${openConvIds.has(conv.id) ? 'active' : ''}`}
                  style={{ paddingLeft: 'var(--space-5)' }}
                  onClick={() => {
                    const existingTab = openTabs.find((t) => t.convId === conv.id)
                    if (existingTab) {
                      // 标签页已存在 → 直接切换到该标签
                      useTabStore.getState().setActiveTab(existingTab.id)
                    } else {
                      // 标签页不存在 → 新建标签并打开该对话
                      openTab(conv.id, conv.name, conv.agentId)
                    }
                  }}
                  onContextMenu={(e) => handleContextMenu(e, conv.id)}
                  draggable
                  onDragStart={(e) => handleDragStart(e, i)}
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDrop(e, i)}
                >
                  {conv.pinned && <span className="pin-indicator"><Pin size={10} /></span>}
                  <div className="conv-avatar" style={{ width: 32, height: 32 }}>
                    <IconAvatar
                      agentId={conv.type === 'single' ? conv.agentId : undefined}
                      iconKey={conv.type === 'group' ? 'group' : undefined}
                      size={18}
                    />
                  </div>
                  <div className="conv-info">
                    <div className={`conv-name ${conv.unread ? 'unread' : ''}`}>{conv.name}</div>
                  </div>
                  <span className="conv-time">{formatTime(conv.updatedAt)}</span>
                  {conv.unread && <span className="unread-dot" />}
                  <button
                    className="conv-menu-btn"
                    onClick={(e) => { e.stopPropagation(); handleContextMenu(e, conv.id) }}
                  >
                    <MoreHorizontal size={14} />
                  </button>
                </div>
              )
            })
          )}
        </div>
        </div>

        {/* Footer */}
        <div className="sidebar-footer">
          <div className="sidebar-footer-item" onClick={() => setShowSettings(true)}>
            <Settings size={16} />
            <span>设置</span>
          </div>
        </div>
      </div>

      {/* Context Menu */}
      {contextMenu && (
        <>
          <div style={{ position: 'fixed', inset: 0, zIndex: 999 }} onClick={closeContextMenu} />
          <div className="context-menu" style={{ left: contextMenu.x, top: contextMenu.y }}>
            <button className="context-menu-item" onClick={() => { togglePin(contextMenu.convId); closeContextMenu() }}>
              <Pin size={14} />
              {conversations.find((c) => c.id === contextMenu.convId)?.pinned ? '取消置顶' : '置顶'}
            </button>
            <button className="context-menu-item" onClick={() => {
              const conv = conversations.find((c) => c.id === contextMenu.convId)
              setRenameDialog({ convId: contextMenu.convId, name: conv?.name || '' })
              closeContextMenu()
            }}>
              <Edit3 size={14} />
              重命名
            </button>
            <button className="context-menu-item danger" onClick={() => { archiveConversation(contextMenu.convId); closeContextMenu() }}>
              <X size={14} />
              归档
            </button>
          </div>
        </>
      )}

      {/* Modals */}
      {showCreator && <AgentCreator onClose={() => setShowCreator(false)} onBack={() => setShowCreator(false)} />}
      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} />}

      {/* 重命名弹窗 */}
      {renameDialog && (
        <div style={{
          position: 'fixed', inset: 0,
          background: 'rgba(0,0,0,0.3)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 9999,
        }} onClick={() => setRenameDialog(null)}>
          <div style={{
            background: 'var(--bg-primary)',
            borderRadius: 'var(--radius-xl)',
            border: '1px solid var(--border)',
            padding: 'var(--space-6)',
            width: 360,
            boxShadow: 'var(--shadow-lg)',
            animation: 'scaleUp 0.15s var(--ease-out)',
          }} onClick={(e) => e.stopPropagation()}>
            <div style={{
              fontSize: 'var(--text-base)', fontWeight: 600,
              color: 'var(--text-primary)', marginBottom: 'var(--space-4)',
            }}>
              重命名
            </div>
            <input
              autoFocus
              value={renameDialog.name}
              onChange={(e) => { setRenameDialog({ ...renameDialog, name: e.target.value }); setRenameError('') }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && renameDialog.name.trim()) {
                  if (checkDuplicateName(renameDialog.convId, renameDialog.name.trim())) {
                    setRenameError('该 Agent 下已存在同名对话，请换一个名称')
                    return
                  }
                  useChatStore.getState().renameConversation(renameDialog.convId, renameDialog.name.trim())
                  setRenameDialog(null)
                  setRenameError('')
                }
              }}
              style={{
                width: '100%', padding: '10px 14px',
                background: 'var(--bg-secondary)',
                border: renameError ? '1px solid var(--red, #ef4444)' : '1px solid var(--border)',
                borderRadius: 'var(--radius-md)', color: 'var(--text-primary)',
                fontSize: 'var(--text-sm)', fontFamily: 'var(--font-ui)', outline: 'none',
              }}
              placeholder="输入对话名称"
            />
            {renameError && (
              <div style={{ fontSize: 12, color: 'var(--red, #ef4444)', marginTop: 6, marginBottom: 'var(--space-2)' }}>
                {renameError}
              </div>
            )}
            <div style={{ display: 'flex', gap: 'var(--space-2)', justifyContent: 'flex-end', marginTop: 'var(--space-4)' }}>
              <button
                onClick={() => { setRenameDialog(null); setRenameError('') }}
                style={{
                  padding: '8px 20px', borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border)', background: 'var(--bg-secondary)',
                  color: 'var(--text-primary)', fontSize: 'var(--text-sm)',
                  cursor: 'pointer', fontFamily: 'var(--font-ui)',
                }}
              >
                取消
              </button>
              <button
                onClick={() => {
                  if (renameDialog.name.trim()) {
                    if (checkDuplicateName(renameDialog.convId, renameDialog.name.trim())) {
                      setRenameError('该 Agent 下已存在同名对话，请换一个名称')
                      return
                    }
                    useChatStore.getState().renameConversation(renameDialog.convId, renameDialog.name.trim())
                  }
                  setRenameDialog(null)
                  setRenameError('')
                }}
                disabled={!renameDialog.name.trim()}
                style={{
                  padding: '8px 20px', borderRadius: 'var(--radius-md)',
                  border: 'none', background: !renameDialog.name.trim() ? 'var(--bg-tertiary)' : 'var(--accent)',
                  color: !renameDialog.name.trim() ? 'var(--text-muted)' : '#fff',
                  fontSize: 'var(--text-sm)', fontWeight: 500,
                  cursor: renameDialog.name.trim() ? 'pointer' : 'default',
                  fontFamily: 'var(--font-ui)',
                }}
              >
                确定
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Fixed-position tooltip (outside scroll container to avoid clipping) */}
      {tooltip && (
        <div style={{
          position: 'fixed',
          top: tooltip.y,
          left: tooltip.x,
          transform: 'translate(-50%, -100%)',
          background: '#1D2129',
          color: '#FFFFFF',
          fontSize: '12px',
          fontWeight: 500,
          whiteSpace: 'nowrap',
          padding: '6px 10px',
          borderRadius: '6px',
          pointerEvents: 'none',
          zIndex: 9999,
        }}>
          {tooltip.text}
          <div style={{
            position: 'absolute',
            top: '100%',
            left: '50%',
            transform: 'translateX(-50%)',
            border: '5px solid transparent',
            borderTopColor: '#1D2129',
          }} />
        </div>
      )}
    </>
  )
}
