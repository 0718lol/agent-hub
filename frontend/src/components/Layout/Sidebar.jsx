import React, { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import { Plus, Settings, Pin, MoreHorizontal, X, PanelLeftClose, PanelLeftOpen, ChevronRight, Search, Bot, Cpu, Globe, Trash2, Lock, Edit3, Download, Upload } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { useTabStore } from '../../stores/tabStore'
import SettingsPanel from './SettingsPanel'
import IconAvatar from '../IconAvatar'
import AgentSelector from '../Chat/AgentSelector'
import LocalAgentSelector from '../Chat/LocalAgentSelector'
import SidebarAgentSection from './SidebarAgentSection'
import SidebarHistorySection from './SidebarHistorySection'
import SidebarFooter from './SidebarFooter'

export default function Sidebar({ currentUser, mobileOpen = false, onClose = () => {} }) {
  const conversations = useChatStore((s) => s.conversations)
  const agents = useAgentStore((s) => s.agents)
  const adapterStatus = useAgentStore((s) => s.adapterStatus)
  const fetchAdapterStatus = useAgentStore((s) => s.fetchAdapterStatus)
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
  const [settingsTab, setSettingsTab] = useState('llm')
  const [settingsEditAgent, setSettingsEditAgent] = useState(null)
  const [showAgentMenu, setShowAgentMenu] = useState(false)
  const [showSelector, setShowSelector] = useState(false)
  const [showLocalSelector, setShowLocalSelector] = useState(false)
  const addBtnRef = useRef(null)
  const [contextMenu, setContextMenu] = useState(null)
  const [dragIndex, setDragIndex] = useState(null)
  const [confirmDeleteAgentId, setConfirmDeleteAgentId] = useState(null)
  const [renameDialog, setRenameDialog] = useState(null) // { convId, name } or null
  const [renameError, setRenameError] = useState('')
  const [tooltip, setTooltip] = useState(null) // { text, x, y } or null

  // 分组折叠状态
  const [agentsExpanded, setAgentsExpanded] = useState(true)
  const [subExpanded, setSubExpanded] = useState({ self: true, external: true, local: true })
  const [searchQuery, setSearchQuery] = useState('')

  // 新对话计数器，用于生成默认名称 "新对话1", "新对话2" ...
  const convCounterRef = useRef(1)

  // 启动时加载适配器状态
  useEffect(() => { fetchAdapterStatus() }, [])

  // PM 不可删除的 ID
  const PM_ID = 'agent_pm'

  // 智能体列表：PM 常驻第一，其余按 agentStore 顺序，排除 builder，加上已配置的本地 Agent
  const sidebarAgents = useMemo(() => {
    const visible = agents.filter((a) =>
      a.agent_id !== 'agent_builder' &&
      !useAgentStore.getState().deletedPresetIds.includes(a.agent_id)
    )
    // 追加已配置的本地 Agent（不在 preset 列表中的）
    const presetIds = new Set(visible.map((a) => a.agent_id))
    for (const [agentId, status] of Object.entries(adapterStatus)) {
      if (status.adapter_type === 'self_deployed' && status.configured && !presetIds.has(agentId)) {
        visible.push({
          agent_id: agentId,
          name: status.display_name || status.name || agentId,
          role: status.display_desc || status.model || '本地 Agent',
          avatar: status.display_avatar || null,
          status: 'idle',
          agent_type: 'external',
          adapter_type: 'self_deployed',
        })
      }
    }
    // PM 固定第一位
    const pm = visible.find((a) => a.agent_id === PM_ID)
    const rest = visible.filter((a) => a.agent_id !== PM_ID)
    return pm ? [pm, ...rest] : rest
  }, [agents, adapterStatus])

  // 分类：自建 / 外部 / 本地
  const agentGroups = useMemo(() => {
    const selfBuilt = []
    const external = []
    const local = []
    for (const a of sidebarAgents) {
      if (a.agent_type === 'self') {
        selfBuilt.push(a)
      } else if (a.adapter_type === 'self_deployed' || a.agent_id.startsWith('local_agent_')) {
        local.push(a)
      } else {
        external.push(a)
      }
    }
    return { self: selfBuilt, external, local }
  }, [sidebarAgents])

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
      if (a.sortOrder !== b.sortOrder) return (a.sortOrder ?? 0) - (b.sortOrder ?? 0)
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

  const handleExportAgent = async (e, agent) => {
    e.stopPropagation()
    try {
      const resp = await fetch(`/api/agents/custom/${agent.agent_id}/export`)
      if (!resp.ok) throw new Error('Export failed')
      const data = await resp.json()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${agent.name || 'agent'}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Export failed:', err)
    }
  }

  const handleImportAgent = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = async (ev) => {
      try {
        const data = JSON.parse(ev.target.result)
        if (!data.agent?.name) {
          alert('Invalid agent file: missing agent name')
          return
        }
        const resp = await fetch('/api/agents/import', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        })
        if (!resp.ok) {
          const err = await resp.json()
          alert('Import failed: ' + (err.detail || 'Unknown error'))
          return
        }
        const result = await resp.json()
        useAgentStore.getState().loadCustomAgents()
        if (result.duplicate_renamed) {
          alert(`Agent imported as "${result.agent.name}" (renamed to avoid duplicate)`)
        }
      } catch (err) {
        alert('Invalid JSON file')
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  const formatTime = (ts) => {
    if (!ts) return ''
    const d = new Date(ts)
    const now = new Date()
    if (d.toDateString() === now.toDateString())
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  }

  // HTML5 Drag
  const handleDragStart = useCallback((e, conversationId) => {
    setDragIndex(conversationId)
    e.dataTransfer.effectAllowed = 'move'
  }, [])

  const handleDragOver = useCallback((e) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const handleDrop = useCallback((e, dropId) => {
    e.preventDefault()
    if (dragIndex !== null && dragIndex !== dropId) {
      reorderConversations(dragIndex, dropId)
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

          <div style={{ flex: 1 }} />

          <div className="sidebar-footer">
            <div className="sidebar-footer-item" onClick={() => { setSettingsTab('llm'); setShowSettings(true) }} title="设置" style={{ justifyContent: 'center' }}>
              <Settings size={16} />
            </div>
          </div>
        </div>

        {/* Modals */}
        {showSettings && <SettingsPanel onClose={() => { setShowSettings(false); setSettingsEditAgent(null) }} defaultTab={settingsTab} editAgentId={settingsEditAgent} />}
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
        <SidebarAgentSection
          agentsExpanded={agentsExpanded}
          setAgentsExpanded={setAgentsExpanded}
          subExpanded={subExpanded}
          setSubExpanded={setSubExpanded}
          agentGroups={agentGroups}
          activeAgentId={activeAgentId}
          openTabs={openTabs}
          openTab={openTab}
          handleDeleteAgent={handleDeleteAgent}
          handleExportAgent={handleExportAgent}
          handleImportAgent={handleImportAgent}
          addBtnRef={addBtnRef}
          setShowAgentMenu={setShowAgentMenu}
          setTooltip={setTooltip}
        />

        <SidebarHistorySection
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          historyConversations={historyConversations}
          openTabs={openTabs}
          openTab={openTab}
          handleContextMenu={handleContextMenu}
          handleDragStart={handleDragStart}
          handleDragOver={handleDragOver}
          handleDrop={handleDrop}
          formatTime={formatTime}
          activeAgentId={activeAgentId}
          convCounterRef={convCounterRef}
        />
        </div>

        <SidebarFooter
          currentUser={currentUser}
          setSettingsTab={setSettingsTab}
          setShowSettings={setShowSettings}
        />
      </div>

      {/* Context Menu */}
      {contextMenu && (
        <>
          <div style={{ position: 'fixed', inset: 0, zIndex: 999 }} onClick={closeContextMenu} />
          <div className="context-menu" style={{ left: contextMenu.x, top: contextMenu.y, zIndex: 1000 }}>
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
            <button className="context-menu-item danger" onClick={() => {
              archiveConversation(contextMenu.convId)
              // 关闭对应的标签页
              const tab = openTabs.find((t) => t.convId === contextMenu.convId)
              if (tab) useTabStore.getState().closeTab(tab.id)
              closeContextMenu()
            }}>
              <X size={14} />
              删除
            </button>
          </div>
        </>
      )}

      {/* 创建 Agent 下拉浮窗 */}
      {showAgentMenu && (
        <>
          <div style={{ position: 'fixed', inset: 0, zIndex: 998 }} onClick={() => setShowAgentMenu(false)} />
          <div
            className="agent-create-menu"
            style={{
              position: 'fixed',
              top: addBtnRef.current ? addBtnRef.current.getBoundingClientRect().bottom + 4 : 0,
              left: addBtnRef.current ? addBtnRef.current.getBoundingClientRect().right : 0,
              zIndex: 999,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="agent-create-menu-item"
              onClick={() => {
                setShowAgentMenu(false)
                setShowSelector(true)
              }}
            >
              <Bot size={16} />
              <div>
                <div className="menu-item-title">选择职业模板</div>
                <div className="menu-item-desc">从预设或自定义 Agent 中选择</div>
              </div>
            </button>
            <button
              className="agent-create-menu-item"
              onClick={() => {
                setShowAgentMenu(false)
                setShowLocalSelector(true)
              }}
            >
              <Cpu size={16} />
              <div>
                <div className="menu-item-title">接入本地 Agent</div>
                <div className="menu-item-desc">OpenCode / 自定义 HTTP 服务</div>
              </div>
            </button>
          </div>
        </>
      )}

      {/* Agent 选择弹窗 */}
      {showSelector && (
        <AgentSelector
          onSelect={(agentId) => {
            const convId = `conv_${agentId}_${Date.now()}`
            const agentConvs = useChatStore.getState().conversations.filter(
              (c) => c.agentId === agentId && !c.archived
            )
            const n = agentConvs.length + 1
            const convName = `新对话${n}`
            useChatStore.getState().addConversation({
              id: convId, type: 'single', agentId, name: convName,
              messages: [], pinned: false, unread: false, updatedAt: Date.now(),
            })
            fetch('/api/conversations', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ id: convId, type: 'single', name: convName, agent_id: agentId }),
            }).catch(() => {})
            openTab(convId, convName, agentId)
            setShowSelector(false)
          }}
          onClose={() => setShowSelector(false)}
        />
      )}

      {/* 本地 Agent 选择弹窗 */}
      {showLocalSelector && (
        <LocalAgentSelector
          onSelect={() => setShowLocalSelector(false)}
          onClose={() => setShowLocalSelector(false)}
          onOpenSettings={(agentId) => {
            setSettingsTab('adapters')
            setSettingsEditAgent(agentId || null)
            setShowSettings(true)
          }}
        />
      )}

      {showSettings && <SettingsPanel onClose={() => { setShowSettings(false); setSettingsEditAgent(null) }} defaultTab={settingsTab} editAgentId={settingsEditAgent} />}

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
