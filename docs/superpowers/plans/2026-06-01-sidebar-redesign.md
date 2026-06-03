# 左侧侧边栏布局重构 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将左侧侧边栏从 200px 对话列表重构为 300px 多分组布局（智能体/资源/搜索+历史），参考 Coze 风格。

**Architecture:** 侧边栏从单一 conversation-list 拆分为 5 个区域：header + 智能体分组 + 资源分组 + 搜索/新对话/历史 + footer。每个区域独立折叠控制，ChatPanelHeader 移除 Search 按钮。

**Tech Stack:** React 18 + Zustand + CSS variables (Coze design tokens)

---

### Task 1: CSS — 侧边栏宽度 + 新分组样式

**Files:**
- Modify: `frontend/src/styles/global.css`

- [ ] **Step 1: 宽度 200→300px**

Replace:
```css
.sidebar {
  width: 200px;
  min-width: 200px;
  ...
}
```
With:
```css
.sidebar {
  width: 300px;
  min-width: 300px;
  ...
}
```

- [ ] **Step 2: 新增分组标题样式**

在 `.sidebar-header` 之前插入：

```css
/* ---- Sidebar Section Groups ---- */
.sidebar-section {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  user-select: none;
  transition: background var(--duration-fast) var(--ease-in-out);
}
.sidebar-section-header:hover {
  background: var(--bg-secondary);
}

.sidebar-section-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.sidebar-section-chevron {
  color: var(--text-muted);
  transition: transform var(--duration-fast) var(--ease-in-out);
}
.sidebar-section-chevron.open {
  transform: rotate(90deg);
}

.sidebar-section-add {
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-fast) var(--ease-in-out);
}
.sidebar-section-add:hover {
  background: var(--bg-secondary);
  color: var(--accent);
}
```

- [ ] **Step 3: 新增 Agent 行样式**

```css
/* Agent item in sidebar */
.sidebar-agent-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  border-radius: var(--radius-md);
  margin: 0 var(--space-1);
  transition: background var(--duration-fast) var(--ease-in-out);
}
.sidebar-agent-item:hover {
  background: var(--bg-secondary);
}
.sidebar-agent-item.active {
  background: var(--accent-bg);
}

.sidebar-agent-info {
  flex: 1;
  min-width: 0;
}
.sidebar-agent-name {
  font-size: var(--text-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sidebar-agent-role {
  font-size: var(--text-xs);
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Online status dot */
.online-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.online-dot.online  { background: var(--green); }
.online-dot.busy   { background: var(--orange); animation: dotPulse 1.5s infinite; }
.online-dot.offline { background: var(--text-muted); }

@keyframes dotPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
```

- [ ] **Step 4: 收起状态适配**

在 `.sidebar.collapsed` 区域追加：

```css
.sidebar.collapsed .sidebar-section-header {
  justify-content: center;
  padding: var(--space-2);
}
.sidebar.collapsed .sidebar-section-title span,
.sidebar.collapsed .sidebar-section-chevron,
.sidebar.collapsed .sidebar-section-add,
.sidebar.collapsed .sidebar-agent-item,
.sidebar.collapsed .sidebar-resource-item,
.sidebar.collapsed .sidebar-search-wrap,
.sidebar.collapsed .sidebar-new-conv,
.sidebar.collapsed .sidebar-history-list {
  display: none;
}
.sidebar.collapsed .sidebar-section-title {
  justify-content: center;
}
```

- [ ] **Step 5: 搜索框 + 历史对话区域样式**

```css
/* Search in sidebar */
.sidebar-search-wrap {
  padding: var(--space-2) var(--space-2);
  flex-shrink: 0;
}
.sidebar-search-wrap input {
  width: 100%;
  height: 32px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--text-xs);
  font-family: var(--font-ui);
  padding: 0 var(--space-3);
  outline: none;
  transition: border-color var(--duration-fast) var(--ease-in-out);
}
.sidebar-search-wrap input:focus { border-color: var(--accent); }
.sidebar-search-wrap input::placeholder { color: var(--text-muted); }

/* History list in sidebar */
.sidebar-history-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 var(--space-2);
  min-height: 0;
}
```

- [ ] **Step 6: Build 验证**

```bash
cd /e/Program/agent-hub/frontend && npm run build
```

---

### Task 2: Sidebar.jsx — 完整重写

**Files:**
- Modify: `frontend/src/components/Layout/Sidebar.jsx`

- [ ] **Step 1: 替换整个 Sidebar.jsx**

写入以下完整代码：

```jsx
import React, { useState, useMemo, useCallback } from 'react'
import { Plus, Settings, Pin, MoreHorizontal, X, PanelLeftClose, PanelLeftOpen, ChevronRight, Search, Users, Bot, Wrench, BookOpen, Cpu } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { useTabStore } from '../../stores/tabStore'
import SettingsPanel from './SettingsPanel'
import IconAvatar from '../IconAvatar'
import AgentSelector from '../Chat/AgentSelector'
import AgentCreator from '../Chat/AgentCreator'

/* 资源子类定义 */
const RESOURCE_CATEGORIES = [
  { key: 'skills', label: '技能', icon: Wrench },
  { key: 'tools', label: '工具', icon: Bot },
  { key: 'knowledge', label: '知识库', icon: BookOpen },
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
  const [showNewDialog, setShowNewDialog] = useState(false)
  const [showCreator, setShowCreator] = useState(false)
  const [contextMenu, setContextMenu] = useState(null)
  const [dragIndex, setDragIndex] = useState(null)

  // 分组折叠状态
  const [agentsExpanded, setAgentsExpanded] = useState(true)
  const [resourcesExpanded, setResourcesExpanded] = useState(true)
  const [resourceExpanded, setResourceExpanded] = useState({})
  const [searchQuery, setSearchQuery] = useState('')

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

  const formatTime = (ts) => {
    if (!ts) return ''
    const d = new Date(ts)
    const now = new Date()
    if (d.toDateString() === now.toDateString())
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  }

  const getStatusClass = (status) => {
    if (status === 'working') return 'busy'
    return status || 'offline'
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
              <Users size={20} style={{ color: 'var(--text-secondary)' }} />
            </div>
          </div>

          <div className="sidebar-section">
            <div className="sidebar-section-header" style={{ justifyContent: 'center' }} title="资源">
              <Bot size={20} style={{ color: 'var(--text-secondary)' }} />
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
        {showNewDialog && (
          <AgentSelector
            onSelect={(agentId) => {
              setShowNewDialog(false)
              const convId = `conv_${agentId}_${Date.now()}`
              const agent = useAgentStore.getState().agents.find((a) => a.agent_id === agentId)
              useChatStore.getState().addConversation({
                id: convId, type: 'single', agentId,
                name: agent?.name || '新对话', avatar: null,
                messages: [], pinned: false, unread: false, updatedAt: Date.now(),
              })
              openTab(convId, agent?.name || '新对话', agentId)
            }}
            onClose={() => setShowNewDialog(false)}
          />
        )}
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

        {/* ===== 智能体分组 ===== */}
        <div className="sidebar-section">
          <div className="sidebar-section-header" onClick={() => setAgentsExpanded(!agentsExpanded)}>
            <div className="sidebar-section-title">
              <ChevronRight size={14} className={`sidebar-section-chevron ${agentsExpanded ? 'open' : ''}`} />
              <Users size={14} />
              <span>智能体</span>
            </div>
            <button
              className="sidebar-section-add"
              onClick={(e) => { e.stopPropagation(); setShowCreator(true) }}
              title="新建Agent"
            >
              <Plus size={14} />
            </button>
          </div>

          {agentsExpanded && (
            <div style={{ paddingBottom: 'var(--space-1)' }}>
              {sidebarAgents.map((agent) => {
                const isActive = activeAgentId === agent.agent_id
                const statusClass = getStatusClass(agent.status)
                return (
                  <div
                    key={agent.agent_id}
                    className={`sidebar-agent-item ${isActive ? 'active' : ''}`}
                    onClick={() => {
                      const convId = `conv_${agent.agent_id}`
                      openTab(convId, agent.name, agent.agent_id)
                    }}
                  >
                    <div className="conv-avatar" style={{ width: 32, height: 32 }}>
                      <IconAvatar agentId={agent.agent_id} size={18} />
                    </div>
                    <div className="sidebar-agent-info">
                      <div className="sidebar-agent-name">{agent.name}</div>
                      <div className="sidebar-agent-role">{agent.role}</div>
                    </div>
                    <span className={`online-dot ${statusClass}`} />
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* ===== 资源分组 ===== */}
        <div className="sidebar-section">
          <div className="sidebar-section-header" onClick={() => setResourcesExpanded(!resourcesExpanded)}>
            <div className="sidebar-section-title">
              <ChevronRight size={14} className={`sidebar-section-chevron ${resourcesExpanded ? 'open' : ''}`} />
              <Bot size={14} />
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
                return (
                  <div key={cat.key}>
                    <div
                      className="sidebar-section-header"
                      onClick={() => toggleResource(cat.key)}
                      style={{ paddingLeft: 'var(--space-5)' }}
                    >
                      <div className="sidebar-section-title">
                        <ChevronRight size={12} className={`sidebar-section-chevron ${isOpen ? 'open' : ''}`} />
                        <CatIcon size={14} />
                        <span style={{ textTransform: 'none', letterSpacing: 0 }}>{cat.label}</span>
                      </div>
                      <button className="sidebar-section-add" onClick={(e) => e.stopPropagation()} title={cat.label}>
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

        {/* ===== 搜索 + 新对话 + 历史对话 ===== */}
        <div className="sidebar-search-wrap">
          <input
            type="text"
            placeholder="搜索对话..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div
          className="conversation-item sidebar-new-conv"
          onClick={() => setShowNewDialog(true)}
        >
          <div className="conv-avatar" style={{ background: 'var(--accent-bg)', color: 'var(--accent)' }}>
            <Plus size={18} />
          </div>
          <div className="conv-info">
            <div className="conv-name" style={{ color: 'var(--accent)' }}>新对话</div>
          </div>
        </div>

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
                  onClick={() => openTab(conv.id, conv.name, conv.agentId)}
                  onContextMenu={(e) => handleContextMenu(e, conv.id)}
                  draggable
                  onDragStart={(e) => handleDragStart(e, i)}
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDrop(e, i)}
                >
                  {conv.pinned && <span className="pin-indicator"><Pin size={10} /></span>}
                  <div className="conv-avatar">
                    <IconAvatar
                      agentId={conv.type === 'single' ? conv.agentId : undefined}
                      iconKey={conv.type === 'group' ? 'group' : undefined}
                      size={20}
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
            <button className="context-menu-item danger" onClick={() => { archiveConversation(contextMenu.convId); closeContextMenu() }}>
              <X size={14} />
              归档
            </button>
          </div>
        </>
      )}

      {/* Modals */}
      {showNewDialog && (
        <AgentSelector
          onSelect={(agentId) => {
            setShowNewDialog(false)
            const convId = `conv_${agentId}_${Date.now()}`
            const agent = useAgentStore.getState().agents.find((a) => a.agent_id === agentId)
            useChatStore.getState().addConversation({
              id: convId, type: 'single', agentId,
              name: agent?.name || '新对话', avatar: null,
              messages: [], pinned: false, unread: false, updatedAt: Date.now(),
            })
            openTab(convId, agent?.name || '新对话', agentId)
          }}
          onClose={() => setShowNewDialog(false)}
        />
      )}
      {showCreator && <AgentCreator onClose={() => setShowCreator(false)} onBack={() => setShowCreator(false)} />}
      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} />}
    </>
  )
}
```

- [ ] **Step 2: Build 验证**

```bash
cd /e/Program/agent-hub/frontend && npm run build
```

---

### Task 3: ChatPanelHeader — 移除 Search 按钮

**Files:**
- Modify: `frontend/src/components/Layout/ChatPanelHeader.jsx:74-81`

- [ ] **Step 1: 移除 Search 图标按钮**

删除 lines 74-81:
```jsx
        <button
          className="header-icon-btn"
          onClick={() => toggleSlidePanel('search')}
          style={slidePanelOpen && slidePanelContent === 'search' ? { color: 'var(--accent)' } : undefined}
        >
          <Search size={20} />
          <span className="icon-tooltip">搜索对话</span>
        </button>
```

- [ ] **Step 2: 移除 Search 导入**

Line 2: 从 `lucide-react` 导入中移除 `Search`:
```jsx
import { Code2, GitBranch, LayoutList, Menu, PanelRightClose, MoreHorizontal, Share2 } from 'lucide-react'
```

- [ ] **Step 3: Build 验证**

```bash
cd /e/Program/agent-hub/frontend && npm run build
```

---

### Task 4: SlidePanel — 移除 search 内容渲染

**Files:**
- Modify: `frontend/src/components/Layout/SlidePanel.jsx`

- [ ] **Step 1: 移除 search 相关代码**

1. 移除 `SearchPanel` import
2. 移除 `useChatStore` import（如果仅用于 search）
3. 移除 `content === 'search'` 标题行
4. 移除 `content === 'search'` 内容渲染块
5. 移除 `setActiveConversation` 使用

- [ ] **Step 2: Build 验证**

```bash
cd /e/Program/agent-hub/frontend && npm run build
```

---

### Task 5: AgentSelector — 排除 PM

**Files:**
- Modify: `frontend/src/components/Chat/AgentSelector.jsx`

- [ ] **Step 1: 过滤 PM agent**

在 `visibleAgents` 过滤中添加 PM 排除:

```jsx
const visibleAgents = agents.filter(
  (a) => a.agent_id !== 'agent_builder'
    && a.agent_id !== 'agent_pm'
    && !deletedPresetIds.includes(a.agent_id)
)
```

- [ ] **Step 2: Build 验证**

```bash
cd /e/Program/agent-hub/frontend && npm run build
```

---

### Task 6: 最终验证

- [ ] **Step 1: Build**

```bash
cd /e/Program/agent-hub/frontend && npm run build
```

Expected: 1800+ modules transformed, build succeeded.

- [ ] **Step 2: 检查关键行为**
  - [ ] PM 小助手在智能体列表第一位，不可删除
  - [ ] 点击智能体 → 打开/切换到独立标签页
  - [ ] 历史对话按当前 agent 过滤
  - [ ] 无历史对话时列表为空（不显示占位符）
  - [ ] 搜索框过滤对话
  - [ ] 「＋ 新对话」打开 AgentSelector（PM 不在其中）
  - [ ] 「智能体 ＋」打开 AgentCreator
  - [ ] 资源分组可折叠，子类可展开/折叠
  - [ ] 收起状态仅显示图标
  - [ ] 侧边栏 300px → 收起 60px，聊天区自适应
  - [ ] ChatPanel header 不再有 Search 按钮
