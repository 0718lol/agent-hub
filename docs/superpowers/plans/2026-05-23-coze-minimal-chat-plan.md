# Coze 极简聊天界面改造 — 实施计划

> **For agentic workers:** 使用 superpowers:subagent-driven-development 或 superpowers:executing-plans 来逐步实施本计划。步骤使用 `- [ ]` checkbox 语法追踪。

**目标：** 将 AgentHub 从三栏布局改造为 Coze 风格的极简 IM 聊天界面

**架构：** 侧边栏（200px）+ 居中聊天区（最大 700px）+ 滑出面板（380px）。浅色极简默认主题，CSS 变量方案双主题切换。实现 Coze 扁平消息气泡、单行输入 + @ 指派、内联 DAG/任务/部署卡片、响应式三档断点。

**技术栈：** React 18 + Vite + Zustand + CSS 变量 + Lucide React（无新增依赖，拖拽排序使用原生 HTML5 Drag API）

---

## 文件结构总览

```
frontend/src/
├── main.jsx                          # [修改] 加载新主题 CSS，初始化新 data-theme
├── App.jsx                           # [重写] 新布局：侧边栏 + 居中聊天 + 滑出面板
├── styles/
│   ├── global.css                    # [重写] 新设计 token + 布局 + 组件样式
│   ├── theme-coze-light.css          # [新建] Coze 浅色主题变量
│   ├── theme-coze-dark.css           # [新建] Coze 深色主题变量
│   ├── theme-tech-dark.css           # [删除]
│   └── theme-vibrant.css             # [删除]
├── stores/
│   ├── themeStore.js                 # [修改] 切换 light/dark
│   ├── chatStore.js                  # [修改] 添加 pin/reorder/search/avatar 字段
│   ├── canvasStore.js                # [修改] 精简，添加 slidePanelOpen/pinMode
│   └── agentStore.js                 # [修改] avatar 改为图标名而非 emoji
├── utils/
│   └── iconMap.js                    # [重写] 纯 Lucide 图标映射，去掉 emoji fallback
├── components/
│   ├── IconAvatar.jsx                # [重写] 仅渲染 Lucide 图标，emoji 模式移除
│   ├── ThemeToggle.jsx               # [修改] 适配浅/深色切换
│   ├── Layout/
│   │   ├── Sidebar.jsx               # [重写] ~200px，搜索/置顶/拖拽排序
│   │   ├── ChatPanel.jsx             # [重写] 居中窄版 + 单/群聊顶栏 + 内联卡片
│   │   ├── CanvasPanel.jsx           # [删除]
│   │   ├── SettingsPanel.jsx         # [修改] 更新主题切换为新 light/dark
│   │   └── SlidePanel.jsx            # [新建] 右侧滑出面板（代码+预览）
│   ├── Chat/
│   │   ├── MessageBubble.jsx         # [重写] Coze 扁平风格，自适应宽度
│   │   ├── InputBar.jsx              # [重写] 单行+展开，群聊@按钮
│   │   ├── AgentSelector.jsx         # [新建] @ 选择器 / 新建对话选择面板
│   │   ├── CodeCard.jsx              # [保留，微调样式]
│   │   ├── MockupCard.jsx            # [保留]
│   │   ├── ClarificationCard.jsx     # [保留]
│   │   ├── InlineDAGCard.jsx         # [新建] 聊天区 DAG 内联卡片
│   │   ├── InlineTaskCard.jsx        # [新建] 聊天区任务看板内联卡片
│   │   └── InlineDeployCard.jsx      # [新建] 聊天区部署状态内联卡片
│   └── Canvas/
│       ├── WebPreview.jsx            # [保留，移入 SlidePanel]
│       ├── DiffViewer.jsx            # [保留，移入 SlidePanel]
│       ├── AgentDAG.jsx              # [保留，改为被 InlineDAGCard 引用]
│       ├── TaskBoard.jsx             # [保留，改为被 InlineTaskCard 引用]
│       ├── DeployPanel.jsx           # [保留，改为被 InlineDeployCard 引用]
│       └── previewHtml.js            # [保留]
```

---

### Task 1: 新主题系统 CSS

**文件:**
- 创建: `frontend/src/styles/theme-coze-light.css`
- 创建: `frontend/src/styles/theme-coze-dark.css`

- [ ] **Step 1: 创建 Coze 浅色主题 CSS 变量**

```css
/* ================================================================
   Theme: Coze Light — 极简浅色
   ================================================================ */
[data-theme="light"] {
  /* Typography */
  --font-ui: 'Inter', -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;

  /* Colors */
  --bg-primary: #FFFFFF;
  --bg-secondary: #F7F8FA;
  --bg-tertiary: #F0F1F3;
  --bg-card: #F7F8FA;
  --bg-card-hover: #F0F1F3;
  --input-bg: #F7F8FA;
  --text-primary: #1D2129;
  --text-secondary: #6B7280;
  --text-muted: #9CA3AF;
  --accent: #165DFF;
  --accent-glow: rgba(22, 93, 255, 0.1);
  --accent-bg: #E8F3FF;
  --cyan: #165DFF;
  --green: #00B42A;
  --orange: #FF7D00;
  --red: #F53F3F;
  --border: #E5E6EB;
  --border-light: #F0F1F3;

  /* Shadows (minimal — no glow) */
  --shadow-color: rgba(0, 0, 0, 0.06);
  --shadow-xs: 0 1px 2px var(--shadow-color);
  --shadow-sm: 0 1px 3px var(--shadow-color);
  --shadow-md: 0 4px 12px var(--shadow-color);
  --shadow-lg: 0 8px 24px var(--shadow-color);
  --shadow-xl: none;

  /* Code / Diff */
  --code-bg: #F7F8FA;
  --code-text: #1D2129;
  --diff-bg: #F7F8FA;
  --diff-add-bg: rgba(0, 180, 42, 0.08);
  --diff-remove-bg: rgba(245, 63, 63, 0.08);

  /* Glass (disabled — flat design) */
  --glass-bg: transparent;
  --glass-border: var(--border);
  --glass-blur: 0px;
}
```

- [ ] **Step 2: 创建 Coze 深色主题 CSS 变量**

```css
/* ================================================================
   Theme: Coze Dark — 极简深色
   ================================================================ */
[data-theme="dark"] {
  --font-ui: 'Inter', -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;

  --bg-primary: #1A1A1B;
  --bg-secondary: #262627;
  --bg-tertiary: #2D2D2E;
  --bg-card: #262627;
  --bg-card-hover: #2D2D2E;
  --input-bg: #262627;
  --text-primary: #E8E9EB;
  --text-secondary: #9CA3AF;
  --text-muted: #787B82;
  --accent: #3C7CFF;
  --accent-glow: rgba(60, 124, 255, 0.12);
  --accent-bg: #1A2D4A;
  --cyan: #3C7CFF;
  --green: #27C24A;
  --orange: #FF8F33;
  --red: #F76560;
  --border: #383839;
  --border-light: #2D2D2E;

  --shadow-color: rgba(0, 0, 0, 0.3);
  --shadow-xs: 0 1px 2px var(--shadow-color);
  --shadow-sm: 0 1px 3px var(--shadow-color);
  --shadow-md: 0 4px 12px var(--shadow-color);
  --shadow-lg: 0 8px 24px var(--shadow-color);
  --shadow-xl: none;

  --code-bg: #1E1E1F;
  --code-text: #E8E9EB;
  --diff-bg: #1E1E1F;
  --diff-add-bg: rgba(39, 194, 74, 0.1);
  --diff-remove-bg: rgba(247, 101, 96, 0.1);

  --glass-bg: transparent;
  --glass-border: var(--border);
  --glass-blur: 0px;
}
```

- [ ] **Step 3: 在 main.jsx 中切换主题导入**

修改 `frontend/src/main.jsx`：

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './styles/global.css'

// 替换旧主题为新 Coze 主题
import './styles/theme-coze-light.css'
import './styles/theme-coze-dark.css'

import { useThemeStore } from './stores/themeStore'
const initialTheme = useThemeStore.getState().theme
document.documentElement.setAttribute('data-theme', initialTheme)

useThemeStore.subscribe((state) => {
  document.documentElement.setAttribute('data-theme', state.theme)
})

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

- [ ] **Step 4: 修改 themeStore 适配 light/dark**

修改 `frontend/src/stores/themeStore.js`：

```js
import { create } from 'zustand'

const STORAGE_KEY = 'agent-hub-theme'

function getInitialTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch {}
  return 'light'
}

export const useThemeStore = create((set) => ({
  theme: getInitialTheme(),
  toggleTheme: () =>
    set((state) => {
      const next = state.theme === 'light' ? 'dark' : 'light'
      try {
        localStorage.setItem(STORAGE_KEY, next)
      } catch {}
      return { theme: next }
    }),
}))
```

- [ ] **Step 5: 修改 ThemeToggle 适配 light/dark**

修改 `frontend/src/components/ThemeToggle.jsx`：

```jsx
import React from 'react'
import { Moon, Sun } from 'lucide-react'
import { useThemeStore } from '../stores/themeStore'

export default function ThemeToggle() {
  const theme = useThemeStore((s) => s.theme)
  const toggleTheme = useThemeStore((s) => s.toggleTheme)
  const isDark = theme === 'dark'

  return (
    <button
      className="theme-toggle"
      onClick={toggleTheme}
      title={isDark ? '切换到浅色模式' : '切换到深色模式'}
      aria-label={isDark ? '切换到浅色模式' : '切换到深色模式'}
    >
      {isDark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  )
}
```

- [ ] **Step 6: 验证** — 启动前端，确认 `data-theme="light"` 在 `<html>` 上，页面白底黑字无报错。点击主题切换按钮确认切换到深色。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/styles/theme-coze-light.css frontend/src/styles/theme-coze-dark.css frontend/src/styles/theme-tech-dark.css frontend/src/styles/theme-vibrant.css frontend/src/main.jsx frontend/src/stores/themeStore.js frontend/src/components/ThemeToggle.jsx
git commit -m "feat: replace old themes with Coze light/dark theme system"
```

---

### Task 2: 设计 Token 与全局样式重写

**文件:**
- 重写: `frontend/src/styles/global.css`

- [ ] **Step 1: 重写 global.css — 设计 Token 层**

完整替换 `global.css` 内容：

```css
/* ================================================================
   AgentHub — Coze Minimal Design System
   CSS 变量、重置、布局、组件基础样式
   颜色值由 theme-coze-*.css 提供
   ================================================================ */

/* ---- Google Fonts ---- */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

/* ================================================================
   DESIGN TOKENS (fallback — overridden by theme files)
   ================================================================ */
:root {
  /* Typography */
  --font-ui: 'Inter', -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  --text-xs: 0.75rem;
  --text-sm: 0.875rem;
  --text-base: 1rem;
  --text-md: 1rem;
  --text-lg: 1.125rem;
  --text-xl: 1.5rem;
  --leading-tight: 1.25;
  --leading-normal: 1.5;
  --leading-relaxed: 1.6;
  --font-weight-normal: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;

  /* Spacing */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;

  /* Border Radius */
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-full: 9999px;

  /* Animation */
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);
  --duration-fast: 150ms;
  --duration-normal: 200ms;
  --duration-slow: 300ms;

  /* Z-Index */
  --z-base: 0;
  --z-dropdown: 10;
  --z-sticky: 20;
  --z-overlay: 30;
  --z-modal: 40;
  --z-toast: 100;

  /* Icon */
  --icon-sm: 14px;
  --icon-md: 16px;
  --icon-lg: 20px;
  --icon-xl: 24px;
}

/* ================================================================
   RESET & BASE
   ================================================================ */
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

html { font-size: 16px; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }

body {
  font-family: var(--font-ui);
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
  font-weight: var(--font-weight-normal);
  background: var(--bg-primary);
  color: var(--text-primary);
  overflow: hidden;
  height: 100vh;
}

#root { height: 100vh; }

/* Scrollbar */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: var(--text-muted);
  opacity: 0.3;
  border-radius: var(--radius-full);
}

/* Selection */
::selection { background: var(--accent); color: #fff; }

:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

- [ ] **Step 2: 重写 global.css — 布局层**

追加到 `global.css`：

```css
/* ================================================================
   APP LAYOUT
   ================================================================ */
.app-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
  position: relative;
}

/* ================================================================
   SIDEBAR
   ================================================================ */
.sidebar {
  width: 200px;
  min-width: 200px;
  flex-shrink: 0;
  background: var(--bg-primary);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.sidebar-header {
  padding: var(--space-4);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.sidebar-logo {
  font-size: var(--text-base);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.sidebar-new-btn {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-fast) var(--ease-in-out);
  margin-left: auto;
}

.sidebar-new-btn:hover {
  background: var(--bg-card-hover);
  color: var(--accent);
  border-color: var(--accent);
}

.sidebar-search {
  padding: 0 var(--space-3) var(--space-3);
}

.sidebar-search input {
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

.sidebar-search input:focus {
  border-color: var(--accent);
}

.sidebar-search input::placeholder {
  color: var(--text-muted);
}

.conversation-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 var(--space-2);
}

.conversation-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-2);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-in-out);
  position: relative;
}

.conversation-item:hover {
  background: var(--bg-card-hover);
}

.conversation-item.active {
  background: var(--accent-bg);
}

.conversation-item .conv-avatar {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  overflow: hidden;
}

.conversation-item .conv-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.conversation-item .conv-info {
  flex: 1;
  min-width: 0;
}

.conversation-item .conv-name {
  font-size: var(--text-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conversation-item .conv-name.unread {
  font-weight: var(--font-weight-semibold);
}

.conversation-item .conv-time {
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.conversation-item .conv-menu-btn {
  display: none;
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  align-items: center;
  justify-content: center;
  position: absolute;
  right: var(--space-2);
  top: 50%;
  transform: translateY(-50%);
}

.conversation-item:hover .conv-menu-btn {
  display: flex;
}

.conversation-item .conv-menu-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.conversation-item .pin-indicator {
  color: var(--accent);
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.unread-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
  margin-left: 2px;
}

.sidebar-footer {
  padding: var(--space-3) var(--space-3);
  border-top: 1px solid var(--border);
}

.sidebar-footer-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2);
  border-radius: var(--radius-md);
  cursor: pointer;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  transition: background var(--duration-fast) var(--ease-in-out);
}

.sidebar-footer-item:hover {
  background: var(--bg-card-hover);
}

/* ================================================================
   CHAT PANEL
   ================================================================ */
.chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--bg-primary);
  position: relative;
}

.chat-panel-inner {
  flex: 1;
  display: flex;
  flex-direction: column;
  max-width: 700px;
  width: 100%;
  margin: 0 auto;
}

@media (max-width: 1279px) {
  .chat-panel-inner { max-width: 600px; }
}

@media (max-width: 767px) {
  .chat-panel-inner { max-width: none; padding: 0; }
}

/* Chat Header */
.chat-header {
  padding: var(--space-3) var(--space-5);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-shrink: 0;
  height: 52px;
}

.chat-header-avatar {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  overflow: hidden;
}

.chat-header-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.chat-header-info {
  flex: 1;
  min-width: 0;
}

.chat-header-name {
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.chat-header-desc {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.chat-header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.chat-header-badge {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  background: var(--bg-secondary);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  border: 1px solid var(--border);
}

.online-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.online-dot.online { background: var(--green); }
.online-dot.busy { background: var(--orange); animation: dotPulse 1.5s infinite; }
.online-dot.offline { background: var(--text-muted); }

@keyframes dotPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Group avatar stack */
.group-avatar-stack {
  display: grid;
  grid-template-columns: 17px 17px;
  grid-template-rows: 17px 17px;
  gap: 1px;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  overflow: hidden;
  flex-shrink: 0;
  position: relative;
}

.group-avatar-stack .mini-avatar {
  width: 17px;
  height: 17px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-secondary);
  font-size: 8px;
  color: var(--text-secondary);
  overflow: hidden;
}

.group-avatar-stack .mini-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* ================================================================
   MESSAGES AREA
   ================================================================ */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-5) 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* Message Row */
.message-row {
  display: flex;
  gap: var(--space-3);
  padding: 0 var(--space-5);
  animation: msgEnter 0.2s var(--ease-out);
}

@keyframes msgEnter {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

.message-row.user {
  justify-content: flex-end;
}

/* Agent message: no background */
.message-row:not(.user) {
  align-items: flex-start;
}

.message-row .msg-avatar {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  overflow: hidden;
}

.message-row .msg-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* Message content wrapper */
.message-content {
  flex: 0 1 auto;
  min-width: 0;
  max-width: 85%;
}

.message-row.user .message-content {
  max-width: 75%;
}

/* Agent bubble: no background, just text */
.message-bubble-agent {
  font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
  color: var(--text-primary);
  word-break: break-word;
}

/* User bubble: light gray background */
.message-bubble-user {
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-lg);
  word-break: break-word;
  display: inline-block;
  max-width: 100%;
}

/* Code block in messages */
.message-bubble-agent .code-block,
.message-bubble-user .code-block {
  background: var(--code-bg);
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  overflow: hidden;
  margin: var(--space-2) 0;
}

.code-block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-1) var(--space-3);
  background: var(--bg-tertiary);
  font-size: var(--text-xs);
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
}

.code-block-header button {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 2px;
  border-radius: 4px;
  transition: color var(--duration-fast);
}

.code-block-header button:hover {
  color: var(--text-primary);
}

.code-block pre {
  padding: var(--space-3);
  margin: 0;
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  line-height: 1.6;
  color: var(--code-text);
}

/* Streaming cursor */
.streaming-cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  background: var(--accent);
  margin-left: 2px;
  animation: blink 0.8s infinite;
  vertical-align: text-bottom;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* Message meta (timestamp + read status + actions) */
.message-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: 4px;
}

.message-meta .time {
  font-size: 11px;
  color: var(--text-muted);
}

.message-meta .read-check {
  font-size: 11px;
  color: var(--text-muted);
}

.message-meta .read-check.read {
  color: var(--accent);
}

.message-actions {
  display: none;
  align-items: center;
  gap: 2px;
}

.message-row:hover .message-actions {
  display: flex;
}

.message-actions button {
  width: 28px;
  height: 28px;
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

.message-actions button:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

/* Inline cards */
.inline-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  margin: var(--space-2) 0;
}

.inline-card-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-medium);
  color: var(--text-primary);
}

.inline-card-header .icon {
  display: flex;
  align-items: center;
  color: var(--accent);
}

/* ================================================================
   INPUT BAR
   ================================================================ */
.input-bar {
  padding: var(--space-4) var(--space-5);
  flex-shrink: 0;
}

.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: var(--space-2);
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-2) var(--space-3);
  transition: border-color var(--duration-fast) var(--ease-in-out);
}

.input-wrapper:focus-within {
  border-color: var(--accent);
}

.input-wrapper textarea {
  flex: 1;
  background: none;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-family: var(--font-ui);
  resize: none;
  min-height: 22px;
  max-height: 100px;
  line-height: var(--leading-normal);
}

.input-wrapper textarea::placeholder {
  color: var(--text-muted);
}

.at-tag {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  background: var(--accent-bg);
  color: var(--accent);
  font-size: var(--text-xs);
  padding: 1px 6px 1px 8px;
  border-radius: 4px;
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
}

.at-tag button {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 0;
  margin-left: 2px;
}

.at-tag button:hover {
  opacity: 0.7;
}

.input-actions {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  flex-shrink: 0;
}

.input-btn {
  width: 32px;
  height: 32px;
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

.input-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.send-btn {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  border: none;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-fast) var(--ease-in-out);
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  filter: brightness(1.1);
}

.send-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.stop-btn {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  border: none;
  background: var(--red);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ================================================================
   SLIDE PANEL
   ================================================================ */
.slide-panel-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-overlay);
  pointer-events: none;
}

.slide-panel-overlay.visible {
  pointer-events: auto;
}

.slide-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 380px;
  height: 100vh;
  background: var(--bg-primary);
  border-left: 1px solid var(--border);
  z-index: var(--z-modal);
  display: flex;
  flex-direction: column;
  transform: translateX(100%);
  transition: transform var(--duration-slow) var(--ease-out);
  box-shadow: var(--shadow-lg);
}

.slide-panel.open {
  transform: translateX(0);
}

@media (max-width: 1279px) {
  .slide-panel { width: 320px; }
}

@media (max-width: 767px) {
  .slide-panel { display: none; }
}

.slide-panel-header {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.slide-panel-tabs {
  display: flex;
  gap: 0;
  flex: 1;
}

.slide-panel-tab {
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-sm);
  color: var(--text-muted);
  cursor: pointer;
  border: none;
  background: none;
  border-bottom: 2px solid transparent;
  transition: all var(--duration-fast) var(--ease-in-out);
  font-family: var(--font-ui);
}

.slide-panel-tab:hover {
  color: var(--text-secondary);
}

.slide-panel-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.slide-panel-actions {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.slide-panel-btn {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.slide-panel-btn:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.slide-panel-btn.pinned {
  color: var(--accent);
}

.slide-panel-content {
  flex: 1;
  overflow: auto;
}

/* ================================================================
   AGENT SELECTOR MODAL
   ================================================================ */
.agent-selector-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: var(--z-modal);
  display: flex;
  align-items: center;
  justify-content: center;
}

.agent-selector {
  background: var(--bg-primary);
  border-radius: var(--radius-xl);
  border: 1px solid var(--border);
  padding: var(--space-6);
  width: 360px;
  max-height: 480px;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
  animation: scaleUp 0.2s var(--ease-out);
}

@keyframes scaleUp {
  from { transform: scale(0.95); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}

.agent-selector-title {
  font-size: var(--text-base);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  margin-bottom: var(--space-4);
}

.agent-selector-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  overflow-y: auto;
}

.agent-selector-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-in-out);
  border: none;
  background: none;
  text-align: left;
  font-family: var(--font-ui);
  color: var(--text-primary);
}

.agent-selector-item:hover {
  background: var(--bg-secondary);
}

.agent-selector-item.selected {
  background: var(--accent-bg);
}

.agent-selector-item .agent-selector-avatar {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  overflow: hidden;
}

.agent-selector-item .agent-selector-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.agent-selector-item .agent-selector-name {
  font-size: var(--text-sm);
  font-weight: var(--font-weight-medium);
}

.agent-selector-item .agent-selector-role {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.agent-selector-check {
  margin-left: auto;
  color: var(--accent);
  display: flex;
  align-items: center;
}

/* ================================================================
   SETTINGS PANEL (overlay modal)
   ================================================================ */
.settings-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: var(--z-modal);
  display: flex;
  align-items: center;
  justify-content: center;
}

.settings-panel {
  background: var(--bg-primary);
  border-radius: var(--radius-xl);
  border: 1px solid var(--border);
  width: 480px;
  max-height: 70vh;
  overflow-y: auto;
  box-shadow: var(--shadow-lg);
}

/* ================================================================
   THEME TOGGLE
   ================================================================ */
.theme-toggle {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--duration-fast) var(--ease-in-out);
}

.theme-toggle:hover {
  border-color: var(--accent);
  color: var(--accent);
}

/* ================================================================
   CONTEXT MENU (floating)
   ================================================================ */
.context-menu {
  position: fixed;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-1);
  box-shadow: var(--shadow-md);
  z-index: var(--z-tooltip);
  min-width: 140px;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  color: var(--text-primary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: background var(--duration-fast) var(--ease-in-out);
  border: none;
  background: none;
  width: 100%;
  text-align: left;
  font-family: var(--font-ui);
}

.context-menu-item:hover {
  background: var(--bg-secondary);
}

.context-menu-item.danger {
  color: var(--red);
}

/* ================================================================
   PINNED MESSAGES BAR
   ================================================================ */
.pinned-bar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-5);
  background: var(--accent-bg);
  border-bottom: 1px solid var(--border);
  font-size: var(--text-xs);
  color: var(--accent);
}

.pinned-bar-text {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pinned-bar button {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 2px;
  border-radius: 4px;
}

.pinned-bar button:hover {
  opacity: 0.7;
}

/* ================================================================
   RESPONSIVE — 汉堡菜单
   ================================================================ */
.hamburger-btn {
  display: none;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  align-items: center;
  justify-content: center;
}

@media (max-width: 1279px) {
  .hamburger-btn { display: flex; }
  .sidebar { display: none; }
}

.sidebar-overlay {
  display: none;
}

@media (max-width: 1279px) {
  .sidebar-overlay.visible {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.3);
    z-index: var(--z-overlay);
  }

  .sidebar.mobile-open {
    display: flex;
    position: fixed;
    top: 0;
    left: 0;
    height: 100vh;
    z-index: var(--z-modal);
    box-shadow: var(--shadow-lg);
  }
}

/* ================================================================
   EMPTY STATE
   ================================================================ */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  gap: var(--space-3);
}

.empty-state .icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  opacity: 0.4;
}

.empty-state .text {
  font-size: var(--text-sm);
}

/* ================================================================
   UTILITY
   ================================================================ */
.flex-center {
  display: flex;
  align-items: center;
  justify-content: center;
}
```

- [ ] **Step 2: 验证** — 启动前端，确认无样式冲突，全局样式正常加载。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/styles/global.css
git commit -m "style: rewrite global CSS for Coze minimal design system"
```

---

### Task 3: 图标系统重写（去 Emoji）

**文件:**
- 重写: `frontend/src/utils/iconMap.js`
- 重写: `frontend/src/components/IconAvatar.jsx`

- [ ] **Step 1: 重写 iconMap.js — 纯 Lucide 图标名映射**

```js
/**
 * Agent icon key → Lucide icon component mapping.
 * No emoji rendering. All icons are Lucide linear outline.
 */
import {
  Bot, ClipboardList, Palette, Code, Settings,
  FlaskConical, Rocket, Target, Wrench, Terminal,
  FileText, Sparkles, Zap, User, Users,
  MessageSquare, Globe, Cpu, Brain, PenTool,
  Shield, Search, Eye, Layout
} from 'lucide-react'

const iconMap = {
  'agent_pm':       { icon: ClipboardList, color: '#f59e0b' },
  'agent_frontend': { icon: Code,           color: '#22d3ee' },
  'agent_backend':  { icon: Terminal,       color: '#6366f1' },
  'agent_tester':   { icon: FlaskConical,   color: '#8b5cf6' },
  'agent_devops':   { icon: Rocket,         color: '#f59e0b' },
  'agent_designer': { icon: Palette,        color: '#ec4899' },
  'agent_builder':  { icon: Wrench,         color: '#64748b' },
  'default':        { icon: Bot,            color: '#6366f1' },
  'group':          { icon: Users,          color: '#10b981' },
  'user':           { icon: User,           color: '#64748b' },
}

/**
 * @param {string} agentId - e.g. 'agent_frontend'
 * @returns {{ icon: React.Component, color: string }}
 */
export function getIconForAgent(agentId) {
  return iconMap[agentId] || iconMap['default']
}

/**
 * @param {string} iconKey - direct icon key
 * @returns {{ icon: React.Component, color: string }}
 */
export function getIconByKey(iconKey) {
  return iconMap[iconKey] || iconMap['default']
}

export default iconMap
```

- [ ] **Step 2: 重写 IconAvatar.jsx — 仅渲染 Lucide 图标**

```jsx
import React from 'react'
import { getIconForAgent } from '../utils/iconMap'
import { Bot } from 'lucide-react'

/**
 * Agent 头像组件 — 纯 Lucide 线性图标渲染。
 * @param {{ agentId?: string, iconKey?: string, size?: number, className?: string, style?: object }} props
 */
export default function IconAvatar({ agentId, iconKey, size = 20, className = '', style = {} }) {
  const { icon: IconComponent, color } = 
    agentId ? getIconForAgent(agentId) :
    iconKey ? getIconForAgent(iconKey) :
    { icon: Bot, color: '#6366f1' }

  return (
    <IconComponent
      size={size}
      color={color}
      className={className}
      style={{ flexShrink: 0, ...style }}
      strokeWidth={1.8}
    />
  )
}
```

- [ ] **Step 3: 验证** — 检查所有引用 IconAvatar 的组件，确保调用方式兼容新 API（groupId -> iconKey='group'，agentId 保持不变）。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/utils/iconMap.js frontend/src/components/IconAvatar.jsx
git commit -m "refactor: replace emoji icon system with pure Lucide linear icons"
```

---

### Task 4: 数据层更新（Stores）

**文件:**
- 修改: `frontend/src/stores/chatStore.js`
- 修改: `frontend/src/stores/agentStore.js`
- 修改: `frontend/src/stores/canvasStore.js`

- [ ] **Step 1: 更新 chatStore — 添加 pin/reorder/avatar 字段**

```js
import { create } from 'zustand'

const INITIAL_CONVERSATIONS = [
  { id: 'conv_pm', type: 'single', agentId: 'agent_pm', name: 'PM 小助手', avatar: null, role: '需求分析与任务拆解', messages: [], pinned: false, unread: false, updatedAt: Date.now() },
  { id: 'conv_frontend', type: 'single', agentId: 'agent_frontend', name: '前端工程师', avatar: null, role: 'React 组件与样式开发', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 1000 },
  { id: 'conv_backend', type: 'single', agentId: 'agent_backend', name: '后端工程师', avatar: null, role: 'API 接口与数据模型', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 2000 },
  { id: 'conv_tester', type: 'single', agentId: 'agent_tester', name: '测试工程师', avatar: null, role: '测试用例与 Bug 分析', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 3000 },
  { id: 'conv_devops', type: 'single', agentId: 'agent_devops', name: '运维工程师', avatar: null, role: 'Docker 部署与 CI/CD', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 4000 },
  { id: 'conv_designer', type: 'single', agentId: 'agent_designer', name: '设计顾问', avatar: null, role: 'UI/UX 设计建议', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 5000 },
  { id: 'conv_agent_builder', type: 'single', agentId: 'agent_builder', name: 'Agent 工坊', avatar: null, role: '对话式创建自定义 Agent', messages: [], pinned: false, unread: false, updatedAt: Date.now() - 6000 },
  { id: 'conv_group_demo', type: 'group', name: 'Demo 项目群', avatar: null, agents: ['agent_pm', 'agent_frontend', 'agent_backend', 'agent_tester', 'agent_devops', 'agent_designer'], messages: [], pinned: false, unread: false, updatedAt: Date.now() - 7000 },
]

export const useChatStore = create((set, get) => ({
  conversations: INITIAL_CONVERSATIONS,
  activeConversationId: 'conv_pm',
  typingAgents: {},
  thinkingAgents: {},
  generatingConvs: new Set(),
  allRead: {},
  pinnedMessages: {},  // { conversationId: [messageId, ...] }

  setActiveConversation: (id) => set({ activeConversationId: id }),

  // Pin/unpin conversation
  togglePin: (conversationId) =>
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === conversationId ? { ...c, pinned: !c.pinned } : c
      ),
    })),

  // Archive conversation (remove from list, keep data)
  archiveConversation: (conversationId) =>
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === conversationId ? { ...c, archived: true } : c
      ),
    })),

  // Reorder conversations (drag sort)
  reorderConversations: (fromIndex, toIndex) =>
    set((state) => {
      const list = [...state.conversations]
      const [moved] = list.splice(fromIndex, 1)
      list.splice(toIndex, 0, moved)
      return { conversations: list }
    }),

  // Pin/unpin message
  togglePinMessage: (conversationId, messageId) =>
    set((state) => {
      const current = state.pinnedMessages[conversationId] || []
      const next = current.includes(messageId)
        ? current.filter((id) => id !== messageId)
        : [...current, messageId]
      return { pinnedMessages: { ...state.pinnedMessages, [conversationId]: next } }
    }),

  setTyping: (conversationId, agentId, isTyping) =>
    set((state) => {
      const current = new Set(state.typingAgents[conversationId] || [])
      if (isTyping) current.add(agentId)
      else current.delete(agentId)
      return { typingAgents: { ...state.typingAgents, [conversationId]: current } }
    }),

  setThinking: (conversationId, agentId, text) =>
    set((state) => {
      const convThinking = { ...(state.thinkingAgents[conversationId] || {}) }
      if (text) { convThinking[agentId] = text }
      else { delete convThinking[agentId] }
      return { thinkingAgents: { ...state.thinkingAgents, [conversationId]: convThinking } }
    }),

  setGenerating: (conversationId, isGenerating) =>
    set((state) => {
      const next = new Set(state.generatingConvs)
      if (isGenerating) next.add(conversationId)
      else next.delete(conversationId)
      return { generatingConvs: next }
    }),

  markRead: (conversationId) =>
    set((state) => ({
      allRead: { ...state.allRead, [conversationId]: true },
      conversations: state.conversations.map((c) =>
        c.id === conversationId ? { ...c, unread: false } : c
      ),
    })),

  markSent: (conversationId) =>
    set((state) => ({
      allRead: { ...state.allRead, [conversationId]: false },
    })),

  loadMessages: async (conversationId) => {
    try {
      const resp = await fetch(`/api/conversations/${conversationId}/messages`)
      const messages = await resp.json()
      set((state) => ({
        conversations: state.conversations.map((conv) =>
          conv.id === conversationId
            ? { ...conv, messages, updatedAt: Date.now() }
            : conv
        ),
      }))
    } catch (e) {
      console.error('Failed to load messages:', e)
    }
  },

  addMessage: (conversationId, message) =>
    set((state) => ({
      conversations: state.conversations.map((conv) =>
        conv.id === conversationId
          ? {
              ...conv,
              messages: [...conv.messages, { ...message, id: Date.now() + Math.random(), timestamp: new Date().toISOString() }],
              updatedAt: Date.now(),
              unread: message.sender !== 'user' && conversationId !== state.activeConversationId,
            }
          : conv
      ),
    })),

  updateLastAgentMessage: (conversationId, senderId, text, streaming) =>
    set((state) => ({
      conversations: state.conversations.map((conv) => {
        if (conv.id !== conversationId) return conv
        const messages = [...conv.messages]
        let targetIdx = -1
        for (let i = messages.length - 1; i >= 0; i--) {
          if (messages[i].sender === senderId && messages[i].streaming) {
            targetIdx = i
            break
          }
        }
        if (targetIdx >= 0) {
          messages[targetIdx] = { ...messages[targetIdx], content: { text }, streaming }
        }
        return { ...conv, messages }
      }),
    })),

  addConversation: (conv) =>
    set((state) => {
      if (state.conversations.find((c) => c.id === conv.id)) return state
      return { conversations: [...state.conversations, { ...conv, updatedAt: Date.now(), unread: false, pinned: false }] }
    }),

  removeConversation: (convId) =>
    set((state) => ({
      conversations: state.conversations.filter((c) => c.id !== convId),
      activeConversationId: state.activeConversationId === convId ? 'conv_pm' : state.activeConversationId,
    })),

  getActiveConversation: () => {
    const state = get()
    return state.conversations.find((c) => c.id === state.activeConversationId)
  },
}))
```

- [ ] **Step 2: 更新 agentStore — avatar 改为 null（使用 agentId 自动映射）**

```js
import { create } from 'zustand'

const AGENTS = [
  { agent_id: 'agent_pm', name: 'PM 小助手', role: '产品经理 · 需求分析与任务拆解', status: 'idle' },
  { agent_id: 'agent_frontend', name: '前端工程师', role: '前端开发 · React/TypeScript', status: 'idle' },
  { agent_id: 'agent_backend', name: '后端工程师', role: '后端开发 · API/数据库', status: 'idle' },
  { agent_id: 'agent_tester', name: '测试工程师', role: '测试 · 用例设计/Bug追踪', status: 'idle' },
  { agent_id: 'agent_devops', name: '运维工程师', role: '运维部署 · Docker/CI/CD', status: 'idle' },
  { agent_id: 'agent_designer', name: '设计顾问', role: 'UI/UX 设计 · 交互体验', status: 'idle' },
]

export const useAgentStore = create((set, get) => ({
  agents: AGENTS,
  setAgentStatus: (agentId, status) =>
    set((state) => ({
      agents: state.agents.map((a) =>
        a.agent_id === agentId ? { ...a, status } : a
      ),
    })),
  getAgent: (agentId) => AGENTS.find((a) => a.agent_id === agentId),
}))
```

- [ ] **Step 3: 更新 canvasStore — 添加面板状态**

```js
import { create } from 'zustand'

export const useCanvasStore = create((set) => ({
  activeTab: 'dag',
  setActiveTab: (tab) => set({ activeTab: tab }),

  // Slide panel
  slidePanelOpen: false,
  slidePanelPinned: false,
  slidePanelTab: 'code', // 'code' | 'preview'
  toggleSlidePanel: () => set((s) => ({ slidePanelOpen: !s.slidePanelOpen, slidePanelPinned: false })),
  setSlidePanelTab: (tab) => set({ slidePanelTab: tab }),
  toggleSlidePanelPin: () => set((s) => ({ slidePanelPinned: !s.slidePanelPinned })),

  previewHtml: null,
  setPreviewHtml: (html) => set({ previewHtml: html }),

  generatedCode: null,
  previousCode: '',
  setGeneratedCode: (language, code) =>
    set((state) => ({
      previousCode: state.generatedCode?.code || '',
      generatedCode: { language, code },
    })),

  isDeploying: false,
  deployLogs: [],
  deployedUrl: '',
  deployStatus: 'idle',

  startDeploy: () =>
    set({ isDeploying: true, deployStatus: 'running', deployLogs: [], deployedUrl: '' }),
  appendDeployLog: (log) =>
    set((state) => ({ deployLogs: [...state.deployLogs, log] })),
  finishDeploy: (url) =>
    set({ isDeploying: false, deployStatus: 'success', deployedUrl: url }),
  failDeploy: () =>
    set({ isDeploying: false, deployStatus: 'failed' }),

  tasks: [
    { id: 1, title: '设计页面 UI', assignee: 'agent_designer', status: 'todo' },
    { id: 2, title: '实现前端组件', assignee: 'agent_frontend', status: 'todo' },
    { id: 3, title: '实现后端 API', assignee: 'agent_backend', status: 'todo' },
    { id: 4, title: '编写测试用例', assignee: 'agent_tester', status: 'todo' },
    { id: 5, title: '配置部署方案', assignee: 'agent_devops', status: 'todo' },
  ],
  moveTask: (taskId, newStatus) =>
    set((state) => ({ tasks: state.tasks.map((t) => t.id === taskId ? { ...t, status: newStatus } : t) })),
  addTask: (task) =>
    set((state) => ({ tasks: [...state.tasks, { ...task, id: Date.now() }] })),
  updateTaskByAgent: (agentId, status) =>
    set((state) => ({ tasks: state.tasks.map((t) => t.assignee === agentId ? { ...t, status } : t) })),

  dagNodes: [
    { id: 'user', label: '用户', iconKey: 'user', x: 200, y: 30, status: 'idle' },
    { id: 'agent_pm', label: 'PM', iconKey: 'agent_pm', x: 200, y: 130, status: 'idle' },
    { id: 'agent_designer', label: '设计', iconKey: 'agent_designer', x: 60, y: 250, status: 'idle' },
    { id: 'agent_frontend', label: '前端', iconKey: 'agent_frontend', x: 160, y: 250, status: 'idle' },
    { id: 'agent_backend', label: '后端', iconKey: 'agent_backend', x: 260, y: 250, status: 'idle' },
    { id: 'agent_tester', label: '测试', iconKey: 'agent_tester', x: 360, y: 250, status: 'idle' },
    { id: 'agent_devops', label: '运维', iconKey: 'agent_devops', x: 340, y: 130, status: 'idle' },
  ],
  dagEdges: [
    { from: 'user', to: 'agent_pm' },
    { from: 'agent_pm', to: 'agent_designer' },
    { from: 'agent_pm', to: 'agent_frontend' },
    { from: 'agent_pm', to: 'agent_backend' },
    { from: 'agent_pm', to: 'agent_tester' },
    { from: 'agent_pm', to: 'agent_devops' },
  ],
  setNodeStatus: (nodeId, status) =>
    set((state) => ({ dagNodes: state.dagNodes.map((n) => n.id === nodeId ? { ...n, status } : n) })),
}))
```

- [ ] **Step 4: 验证** — 启动前端，确认 stores 无运行时错误。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/stores/chatStore.js frontend/src/stores/agentStore.js frontend/src/stores/canvasStore.js
git commit -m "feat: update stores for Coze design — pin/reorder/pinned-messages/panel state/icons"
```

---

### Task 5: 侧边栏重写

**文件:**
- 重写: `frontend/src/components/Layout/Sidebar.jsx`

- [ ] **Step 1: 实现新 Sidebar 组件**

```jsx
import React, { useState, useMemo, useCallback } from 'react'
import { Plus, Search, Settings, Pin, MoreHorizontal, X } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import SettingsPanel from './SettingsPanel'
import IconAvatar from '../IconAvatar'
import AgentSelector from '../Chat/AgentSelector'

export default function Sidebar() {
  const conversations = useChatStore((s) => s.conversations)
  const activeId = useChatStore((s) => s.activeConversationId)
  const setActive = useChatStore((s) => s.setActiveConversation)
  const togglePin = useChatStore((s) => s.togglePin)
  const archiveConversation = useChatStore((s) => s.archiveConversation)
  const reorderConversations = useChatStore((s) => s.reorderConversations)

  const [showSettings, setShowSettings] = useState(false)
  const [showNewDialog, setShowNewDialog] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [contextMenu, setContextMenu] = useState(null) // { convId, x, y }
  const [dragIndex, setDragIndex] = useState(null)

  // Sort: pinned first, then by updatedAt desc. Filter archived.
  const sorted = useMemo(() => {
    const active = conversations.filter((c) => !c.archived)
    const filtered = searchQuery
      ? active.filter((c) => c.name.toLowerCase().includes(searchQuery.toLowerCase()))
      : active
    return [...filtered].sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
      return (b.updatedAt || 0) - (a.updatedAt || 0)
    })
  }, [conversations, searchQuery])

  const handleContextMenu = useCallback((e, convId) => {
    e.preventDefault()
    setContextMenu({ convId, x: e.clientX, y: e.clientY })
  }, [])

  const closeContextMenu = () => setContextMenu(null)

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

  const formatTime = (ts) => {
    if (!ts) return ''
    const d = new Date(ts)
    const now = new Date()
    const isToday = d.toDateString() === now.toDateString()
    if (isToday) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  }

  return (
    <>
      <div className="sidebar">
        <div className="sidebar-header">
          <span className="sidebar-logo">AgentHub</span>
          <button className="sidebar-new-btn" onClick={() => setShowNewDialog(true)} title="新建对话">
            <Plus size={18} />
          </button>
        </div>

        <div className="sidebar-search">
          <input
            type="text"
            placeholder="搜索会话..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="conversation-list">
          {sorted.map((conv, i) => (
            <div
              key={conv.id}
              className={`conversation-item ${activeId === conv.id ? 'active' : ''}`}
              onClick={() => setActive(conv.id)}
              onContextMenu={(e) => handleContextMenu(e, conv.id)}
              draggable
              onDragStart={(e) => handleDragStart(e, i)}
              onDragOver={handleDragOver}
              onDrop={(e) => handleDrop(e, i)}
            >
              {conv.pinned && (
                <span className="pin-indicator"><Pin size={10} /></span>
              )}
              <div className="conv-avatar">
                <IconAvatar
                  agentId={conv.type === 'group' ? undefined : conv.agentId}
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
          ))}
        </div>

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
            <button className="context-menu-item" onClick={() => {
              togglePin(contextMenu.convId)
              closeContextMenu()
            }}>
              <Pin size={14} />
              {conversations.find((c) => c.id === contextMenu.convId)?.pinned ? '取消置顶' : '置顶'}
            </button>
            <button className="context-menu-item danger" onClick={() => {
              archiveConversation(contextMenu.convId)
              closeContextMenu()
            }}>
              <X size={14} />
              归档
            </button>
          </div>
        </>
      )}

      {/* New Conversation Dialog */}
      {showNewDialog && (
        <AgentSelector
          onSelect={(agentId) => {
            setShowNewDialog(false)
            const convId = `conv_${agentId}`
            const existing = conversations.find((c) => c.id === convId)
            if (existing) {
              setActive(convId)
            } else {
              useChatStore.getState().addConversation({
                id: `conv_${agentId}_${Date.now()}`,
                type: 'single',
                agentId,
                name: useAgentStore.getState().agents.find((a) => a.agent_id === agentId)?.name || '新对话',
                avatar: null,
                messages: [],
                pinned: false,
                unread: false,
                updatedAt: Date.now(),
              })
              setActive(convId)
            }
          }}
          onClose={() => setShowNewDialog(false)}
        />
      )}

      {/* Settings */}
      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} />}
    </>
  )
}
```

- [ ] **Step 2: 验证** — 启动前端，验证侧边栏渲染正常、搜索过滤可用、右键菜单出现、拖拽排序生效。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/Layout/Sidebar.jsx
git commit -m "feat: rewrite Sidebar — search, pin, drag-sort, context menu"
```

---

### Task 6: AgentSelector 组件

**文件:**
- 创建: `frontend/src/components/Chat/AgentSelector.jsx`

- [ ] **Step 1: 实现 AgentSelector（用于新建对话 + @ 指派）**

```jsx
import React from 'react'
import { Check, X } from 'lucide-react'
import { useAgentStore } from '../../stores/agentStore'
import IconAvatar from '../IconAvatar'

export default function AgentSelector({ onSelect, onClose, multiSelect = false, selected = [], onToggle }) {
  const agents = useAgentStore((s) => s.agents)
  // Exclude builder from quick select
  const selectable = agents.filter((a) => a.agent_id !== 'agent_builder')

  return (
    <div className="agent-selector-overlay" onClick={onClose}>
      <div className="agent-selector" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
          <span className="agent-selector-title">
            {multiSelect ? '选择 Agent' : '选择 Agent 开始对话'}
          </span>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 4, borderRadius: 4 }}
          >
            <X size={18} />
          </button>
        </div>
        <div className="agent-selector-list">
          {selectable.map((agent) => {
            const isSelected = selected.includes(agent.agent_id)
            return (
              <button
                key={agent.agent_id}
                className={`agent-selector-item ${isSelected ? 'selected' : ''}`}
                onClick={() => {
                  if (multiSelect && onToggle) {
                    onToggle(agent.agent_id)
                  } else {
                    onSelect(agent.agent_id)
                    onClose?.()
                  }
                }}
              >
                <div className="agent-selector-avatar">
                  <IconAvatar agentId={agent.agent_id} size={22} />
                </div>
                <div style={{ flex: 1 }}>
                  <div className="agent-selector-name">{agent.name}</div>
                  <div className="agent-selector-role">{agent.role}</div>
                </div>
                {isSelected && (
                  <div className="agent-selector-check"><Check size={16} /></div>
                )}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 验证** — 确保在侧边栏点击 + 按钮弹出选择器，点击 Agent 创建对话。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/Chat/AgentSelector.jsx
git commit -m "feat: add AgentSelector modal for new conversation and @mention"
```

---

### Task 7: ChatPanel 重写（核心）

**文件:**
- 重写: `frontend/src/components/Layout/ChatPanel.jsx`
- 重写: `frontend/src/App.jsx`

- [ ] **Step 1: 重写 App.jsx — 新布局**

```jsx
import React from 'react'
import Sidebar from './components/Layout/Sidebar'
import ChatPanel from './components/Layout/ChatPanel'
import SlidePanel from './components/Layout/SlidePanel'

export default function App() {
  return (
    <div className="app-layout">
      <Sidebar />
      <ChatPanel />
      <SlidePanel />
    </div>
  )
}
```

- [ ] **Step 2: 重写 ChatPanel.jsx**

核心逻辑保留 WebSocket 消息处理（不变），重写 UI 渲染层。由于文件较长，要点：

- 引用 `useThemeStore` 获取 `theme`
- 聊天区包裹在 `chat-panel-inner` 中实现居中窄版
- 顶栏区分单聊/群聊
- 消息渲染用 Coze 扁平风格
- 内联卡片区（DAG/Task/Deploy）
- 输入区传递 `conversationType`

```jsx
import React, { useRef, useEffect } from 'react'
import { MessageSquare, PanelRightOpen, PanelRightClose } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { useAgentStore } from '../../stores/agentStore'
import { useCanvasStore } from '../../stores/canvasStore'
import { useThemeStore } from '../../stores/themeStore'
import MessageBubble from '../Chat/MessageBubble'
import InputBar from '../Chat/InputBar'
import InlineDAGCard from '../Chat/InlineDAGCard'
import InlineTaskCard from '../Chat/InlineTaskCard'
import InlineDeployCard from '../Chat/InlineDeployCard'
import { wsClient } from '../../utils/websocket'
import IconAvatar from '../IconAvatar'
import ThemeToggle from '../ThemeToggle'

export default function ChatPanel() {
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
  const slidePanelPinned = useCanvasStore((s) => s.slidePanelPinned)
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

  useEffect(() => { loadMessages(activeId) }, [activeId])

  // WS message handling (same as current, unchanged)
  useEffect(() => {
    wsClient.connect(activeId)
    const unsub = wsClient.onMessage((data) => {
      if (data.conversation_id !== activeId) return
      if (data.type === 'typing') { setTyping(activeId, data.agent_id, data.is_typing); return }
      if (data.type === 'thinking') { setThinking(activeId, data.agent_id, data.text); return }
      if (data.type === 'code') { setGeneratedCode(data.language, data.code); if (data.language === 'html') setPreviewHtml(data.code); return }
      if (data.type === 'preview') { setPreviewHtml(data.html); return }
      if (data.type === 'generating') { setGenerating(activeId, data.is_generating); return }
      if (data.type === 'task_status') { updateTaskByAgent(data.agent_id, data.status === 'doing' ? 'doing' : data.status); useCanvasStore.getState().setNodeStatus(data.agent_id, data.status === 'doing' ? 'working' : data.status); return }
      if (data.type === 'deploy_status') {
        const { status, log, url } = data
        if (log) useCanvasStore.getState().appendDeployLog(log)
        if (status === 'success' && url) useCanvasStore.getState().finishDeploy(url)
        if (status === 'failed') useCanvasStore.getState().failDeploy()
        return
      }
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

  useEffect(() => {
    markRead(activeId)
    wsClient.send({ type: 'read', conversation_id: activeId, sender: 'user' })
  }, [activeId])

  useEffect(() => {
    if (messagesRef.current) messagesRef.current.scrollTop = messagesRef.current.scrollHeight
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
          {isGroup ? (
            <>
              {/* Group avatar stack */}
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
            <ThemeToggle />
            <button
              className="input-btn"
              onClick={toggleSlidePanel}
              title={slidePanelOpen ? '关闭面板' : '打开面板'}
              style={{ color: slidePanelOpen ? 'var(--accent)' : undefined }}
            >
              {slidePanelOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
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

        {/* Inline cards: DAG + Tasks + Deploy */}
        {conv.messages.length > 0 && (
          <div style={{ padding: '0 var(--space-5) var(--space-3)', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            <InlineDAGCard />
            <InlineTaskCard />
            <InlineDeployCard />
          </div>
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
```

- [ ] **Step 2: 验证** — 启动前端，确认聊天区居中、顶栏正常、消息列表滚动、输入发送正常。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/App.jsx frontend/src/components/Layout/ChatPanel.jsx
git commit -m "feat: rewrite App layout and ChatPanel for Coze centered chat with single/group header"
```

---

### Task 8: MessageBubble 重写（Coze 扁平风格）

**文件:**
- 重写: `frontend/src/components/Chat/MessageBubble.jsx`
- 创建: `frontend/src/styles/typing.css`（或内联在 MessageBubble 中）

由于消息气泡逻辑复杂（特殊标签解析保留），此任务专注于样式重写。关键变更：

- Agent 消息：无背景色，左对齐
- 用户消息：浅灰底右对齐
- 宽度自适应内容
- Code block 用卡片包裹
- 消息操作栏 hover 出现
- Pin 标识用 Lucide Pin 图标替代 emoji

```jsx
import React, { useState } from 'react'
import { User, Copy, RefreshCw, Reply, Pin, MoreHorizontal, Check } from 'lucide-react'
import { useAgentStore } from '../../stores/agentStore'
import { useChatStore } from '../../stores/chatStore'
import { useCanvasStore } from '../../stores/canvasStore'
import CodeCard from './CodeCard'
import MockupCard from './MockupCard'
import ClarificationCard from './ClarificationCard'
import { wsClient } from '../../utils/websocket'
import IconAvatar from '../IconAvatar'

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
    // Set quoted reply mode (simplified: prepend quote)
    addMessage(activeId, {
      sender: 'user',
      content: { text: `> ${text.slice(0, 80)}...\n\n` },
      streaming: false,
    })
  }

  const renderText = (t) => {
    let clean = t.replace(/\[thinking\][\s\S]*?\[\/thinking\]/g, '')
    if (clean.match(/```[\s\S]*?```/)) {
      clean = clean.replace(/```[\s\S]*?```/g, '\n[code_generated]\n')
    }
    clean = clean.replace(/\[assign:\w+\]/g, '')
    clean = clean.trim()
    if (!clean) return null

    const parts = clean.split(/(\[mockup:\w+\]|\[preview:\w+\]|\[clarify:[^\]]+\]|\[options:[^\]]+\]|\[code_generated\])/g)
    return parts.map((part, i) => {
      if (!part) return null
      const mockupMatch = part.match(/\[mockup:(\w+)\]/)
      if (mockupMatch) return <MockupCard key={i} type={mockupMatch[1]} />
      const previewMatch = part.match(/\[preview:(\w+)\]/)
      if (previewMatch) {
        return (
          <div key={i} style={{
            margin: '8px 0', padding: '8px 12px',
            background: 'var(--accent-bg)', border: '1px solid var(--accent)', borderColor: 'var(--accent)',
            borderRadius: 'var(--radius-md)', fontSize: 'var(--text-xs)', color: 'var(--accent)',
            display: 'flex', alignItems: 'center', gap: 6, opacity: 0.8,
          }}>
            预览已更新到右侧面板
          </div>
        )
      }
      if (part === '[code_generated]') {
        return (
          <div key={i} style={{
            margin: '8px 0', padding: '8px 12px',
            background: 'var(--accent-bg)', border: '1px solid var(--accent)',
            borderRadius: 'var(--radius-md)', fontSize: 'var(--text-xs)', color: 'var(--accent)',
            display: 'flex', alignItems: 'center', gap: 6, opacity: 0.8,
          }}>
            代码已更新到右侧面板
          </div>
        )
      }
      const clarifyMatch = part.match(/\[clarify:([^\]]+)\]/)
      if (clarifyMatch) {
        const questions = clarifyMatch[1].split('|')
        return <ClarificationCard key={i} questions={questions} onSubmit={(qaList) => {
          const answerText = qaList.map((qa) => `**${qa.question}**\n${qa.answer}`).join('\n\n')
          addMessage(activeId, { sender: 'user', content: { text: `需求澄清回答：\n\n${answerText}` }, streaming: false })
          wsClient.send({ type: 'message', conversation_id: activeId, sender: 'user', content: { text: `[clarified] ${answerText}`, target_agent: 'agent_pm' } })
        }} />
      }
      const optionsMatch = part.match(/\[options:([^\]]+)\]/)
      if (optionsMatch) {
        const options = optionsMatch[1].split('|')
        return (
          <div key={i} style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '8px 0' }}>
            {options.map((opt, j) => (
              <button key={j} onClick={() => {
                addMessage(activeId, { sender: 'user', content: { text: opt }, streaming: false })
                wsClient.send({ type: 'message', conversation_id: activeId, sender: 'user', content: { text: opt } })
              }} style={{
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
      // Parse code blocks in text for inline rendering
      const codeBlockMatch = part.match(/```(\w*)\n([\s\S]*?)```/)
      if (codeBlockMatch) {
        const lang = codeBlockMatch[1] || 'text'
        const code = codeBlockMatch[2]
        return (
          <div key={i} className="code-block">
            <div className="code-block-header">
              <span>{lang}</span>
              <button onClick={() => { navigator.clipboard.writeText(code) }}>
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
```

- [ ] **Step 2: 验证** — 检查消息气泡样式：Agent 无背景、用户浅灰底、宽度自适应、操作按钮 hover 出现。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/Chat/MessageBubble.jsx
git commit -m "feat: rewrite MessageBubble with Coze flat style, adaptive width, inline code blocks"
```

---

### Task 9: InputBar 重写

**文件:**
- 重写: `frontend/src/components/Chat/InputBar.jsx`

- [ ] **Step 1: 实现新 InputBar**

```jsx
import React, { useState, useRef } from 'react'
import { Send, Square, AtSign, Maximize2 } from 'lucide-react'
import AgentSelector from './AgentSelector'

export default function InputBar({ onSend, isGenerating, onStop, isGroup }) {
  const [text, setText] = useState('')
  const [mentionedAgents, setMentionedAgents] = useState([])
  const [showSelector, setShowSelector] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const textareaRef = useRef(null)

  const handleSend = () => {
    if (!text.trim() || isGenerating) return
    onSend(text.trim(), mentionedAgents)
    setText('')
    setMentionedAgents([])
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
    // @ key triggers selector in group mode
    if (e.key === '@' && isGroup && !text.includes('@')) {
      // Will be handled via onChange detection
    }
  }

  const handleChange = (e) => {
    const val = e.target.value
    setText(val)
    // Detect @ trigger in group mode
    if (isGroup && val.endsWith('@')) {
      setShowSelector(true)
    }
  }

  const handleToggleAgent = (agentId) => {
    setMentionedAgents((prev) =>
      prev.includes(agentId) ? prev.filter((id) => id !== agentId) : [...prev, agentId]
    )
  }

  const removeMention = (agentId) => {
    setMentionedAgents((prev) => prev.filter((id) => id !== agentId))
  }

  if (isGenerating) {
    return (
      <div className="input-bar">
        <div className="input-wrapper" style={{ borderColor: 'var(--red)', opacity: 0.6 }}>
          <textarea value="" readOnly placeholder="Agent 正在回复..." rows={1} style={{ opacity: 0.5, cursor: 'not-allowed' }} />
          <button className="stop-btn" onClick={onStop} title="停止生成">
            <Square size={14} fill="currentColor" />
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="input-bar">
      <div className="input-wrapper">
        {isGroup && (
          <button
            className="input-btn"
            onClick={() => setShowSelector(!showSelector)}
            title="@ 指定 Agent"
            style={{ color: mentionedAgents.length > 0 ? 'var(--accent)' : undefined }}
          >
            <AtSign size={18} />
          </button>
        )}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={isGroup ? '@ 指定 Agent 或输入消息...' : '输入消息...'}
          rows={expanded ? 4 : 1}
        />
        <div className="input-actions">
          <button className="input-btn" onClick={() => setExpanded(!expanded)} title={expanded ? '收起' : '展开'}>
            <Maximize2 size={16} />
          </button>
          <button className="send-btn" onClick={handleSend} disabled={!text.trim()}>
            <Send size={16} />
          </button>
        </div>
      </div>

      {/* Mentioned tags */}
      {mentionedAgents.length > 0 && (
        <div style={{ display: 'flex', gap: 4, marginTop: 6, flexWrap: 'wrap' }}>
          {mentionedAgents.map((id) => {
            const agent = useAgentStore.getState().agents.find((a) => a.agent_id === id)
            return (
              <span key={id} className="at-tag">
                @{agent?.name || id}
                <button onClick={() => removeMention(id)}>×</button>
              </span>
            )
          })}
        </div>
      )}

      {/* Agent Selector for @mention */}
      {showSelector && (
        <AgentSelector
          multiSelect
          selected={mentionedAgents}
          onToggle={handleToggleAgent}
          onClose={() => setShowSelector(false)}
          onSelect={() => {}}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 2: 验证** — 单聊模式：单行输入 + 发送。群聊模式：@ 按钮出现，点击弹出选择器，选中显示蓝色标签。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/Chat/InputBar.jsx
git commit -m "feat: rewrite InputBar — single-line with expand, @mention in group mode"
```

---

### Task 10: SlidePanel + InlineCards

**文件:**
- 创建: `frontend/src/components/Layout/SlidePanel.jsx`
- 创建: `frontend/src/components/Chat/InlineDAGCard.jsx`
- 创建: `frontend/src/components/Chat/InlineTaskCard.jsx`
- 创建: `frontend/src/components/Chat/InlineDeployCard.jsx`

- [ ] **Step 1: 实现 SlidePanel**

```jsx
import React from 'react'
import { X, Pin, Copy } from 'lucide-react'
import { useCanvasStore } from '../../stores/canvasStore'
import DiffViewer from '../Canvas/DiffViewer'
import WebPreview from '../Canvas/WebPreview'

export default function SlidePanel() {
  const open = useCanvasStore((s) => s.slidePanelOpen)
  const pinned = useCanvasStore((s) => s.slidePanelPinned)
  const tab = useCanvasStore((s) => s.slidePanelTab)
  const toggleSlidePanel = useCanvasStore((s) => s.toggleSlidePanel)
  const togglePin = useCanvasStore((s) => s.toggleSlidePanelPin)
  const setTab = useCanvasStore((s) => s.setSlidePanelTab)

  const handleOverlayClick = () => {
    if (!pinned) toggleSlidePanel()
  }

  return (
    <>
      <div
        className={`slide-panel-overlay ${open ? 'visible' : ''}`}
        onClick={handleOverlayClick}
      />
      <div className={`slide-panel ${open ? 'open' : ''}`}>
        <div className="slide-panel-header">
          <div className="slide-panel-tabs">
            <button
              className={`slide-panel-tab ${tab === 'code' ? 'active' : ''}`}
              onClick={() => setTab('code')}
            >
              代码
            </button>
            <button
              className={`slide-panel-tab ${tab === 'preview' ? 'active' : ''}`}
              onClick={() => setTab('preview')}
            >
              预览
            </button>
          </div>
          <div className="slide-panel-actions">
            <button
              className={`slide-panel-btn ${pinned ? 'pinned' : ''}`}
              onClick={togglePin}
              title={pinned ? '取消常驻' : '常驻面板'}
            >
              <Pin size={16} />
            </button>
            <button className="slide-panel-btn" onClick={toggleSlidePanel} title="关闭面板">
              <X size={16} />
            </button>
          </div>
        </div>
        <div className="slide-panel-content">
          {tab === 'code' && <DiffViewer />}
          {tab === 'preview' && <WebPreview />}
        </div>
      </div>
    </>
  )
}
```

- [ ] **Step 2: 实现 InlineDAGCard**

```jsx
import React from 'react'
import { GitGraph, ChevronRight } from 'lucide-react'
import { useCanvasStore } from '../../stores/canvasStore'
import AgentDAG from '../Canvas/AgentDAG'

export default function InlineDAGCard() {
  const nodes = useCanvasStore((s) => s.dagNodes)
  const activeCount = nodes.filter((n) => n.status === 'working').length
  const doneCount = nodes.filter((n) => n.status === 'done').length

  if (nodes.length === 0) return null

  return (
    <details className="inline-card">
      <summary className="inline-card-header" style={{ cursor: 'pointer', listStyle: 'none' }}>
        <span className="icon"><GitGraph size={16} /></span>
        <span>协作图</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto', marginRight: 8 }}>
          {doneCount}/{nodes.length} 完成
          {activeCount > 0 && <span style={{ color: 'var(--accent)' }}> · 工作中</span>}
        </span>
        <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
      </summary>
      <div style={{ height: 240, marginTop: 8 }}>
        <AgentDAG compact />
      </div>
    </details>
  )
}
```

- [ ] **Step 3: 实现 InlineTaskCard**

```jsx
import React from 'react'
import { ListTodo, ChevronRight } from 'lucide-react'
import { useCanvasStore } from '../../stores/canvasStore'
import TaskBoard from '../Canvas/TaskBoard'

export default function InlineTaskCard() {
  const tasks = useCanvasStore((s) => s.tasks)
  const doneCount = tasks.filter((t) => t.status === 'done').length
  const doingCount = tasks.filter((t) => t.status === 'doing').length

  if (tasks.length === 0) return null

  return (
    <details className="inline-card">
      <summary className="inline-card-header" style={{ cursor: 'pointer', listStyle: 'none' }}>
        <span className="icon"><ListTodo size={16} /></span>
        <span>任务看板</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto', marginRight: 8 }}>
          {doneCount}/{tasks.length} 完成
          {doingCount > 0 && <span style={{ color: 'var(--accent)' }}> · {doingCount} 进行中</span>}
        </span>
        <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
      </summary>
      <div style={{ marginTop: 8 }}>
        <TaskBoard compact />
      </div>
    </details>
  )
}
```

- [ ] **Step 4: 实现 InlineDeployCard**

```jsx
import React from 'react'
import { Terminal, ExternalLink, ChevronRight } from 'lucide-react'
import { useCanvasStore } from '../../stores/canvasStore'

export default function InlineDeployCard() {
  const logs = useCanvasStore((s) => s.deployLogs)
  const status = useCanvasStore((s) => s.deployStatus)
  const url = useCanvasStore((s) => s.deployedUrl)

  if (status === 'idle') return null

  return (
    <details className="inline-card" open={status === 'running'}>
      <summary className="inline-card-header" style={{ cursor: 'pointer', listStyle: 'none' }}>
        <span className="icon"><Terminal size={16} /></span>
        <span>部署状态</span>
        <span style={{
          fontSize: 12, marginLeft: 'auto', marginRight: 8,
          color: status === 'success' ? 'var(--green)' : status === 'failed' ? 'var(--red)' : 'var(--accent)',
        }}>
          {status === 'running' ? '部署中...' : status === 'success' ? '部署成功' : '部署失败'}
        </span>
        <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
      </summary>
      <div style={{
        marginTop: 8, background: 'var(--code-bg)', borderRadius: 'var(--radius-md)',
        padding: 'var(--space-3)', fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)',
        maxHeight: 120, overflow: 'auto', color: 'var(--text-secondary)',
      }}>
        {logs.length === 0 && <span style={{ color: 'var(--text-muted)' }}>等待日志...</span>}
        {logs.slice(-10).map((line, i) => (
          <div key={i} style={{ lineHeight: 1.6 }}>{line}</div>
        ))}
      </div>
      {url && (
        <a href={url} target="_blank" rel="noopener noreferrer" style={{
          display: 'inline-flex', alignItems: 'center', gap: 4, marginTop: 8,
          fontSize: 'var(--text-xs)', color: 'var(--accent)', textDecoration: 'none',
        }}>
          <ExternalLink size={12} /> {url}
        </a>
      )}
    </details>
  )
}
```

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/Layout/SlidePanel.jsx frontend/src/components/Chat/InlineDAGCard.jsx frontend/src/components/Chat/InlineTaskCard.jsx frontend/src/components/Chat/InlineDeployCard.jsx
git commit -m "feat: add SlidePanel with code/preview tabs and inline DAG/Task/Deploy cards"
```

---

### Task 11: 清理与整合

**文件:**
- 删除: `frontend/src/components/Layout/CanvasPanel.jsx`
- 删除: `frontend/src/styles/theme-tech-dark.css`
- 删除: `frontend/src/styles/theme-vibrant.css`
- 修改: `frontend/src/components/Canvas/AgentDAG.jsx`（支持 compact prop）
- 修改: `frontend/src/components/Canvas/TaskBoard.jsx`（支持 compact prop）
- 修改: `frontend/src/components/Layout/SettingsPanel.jsx`（适配新主题切换）

- [ ] **Step 1: 清理旧文件**

```bash
rm frontend/src/components/Layout/CanvasPanel.jsx
rm frontend/src/styles/theme-tech-dark.css
rm frontend/src/styles/theme-vibrant.css
```

- [ ] **Step 2: 更新 AgentDAG 支持 compact 模式**

在 `AgentDAG.jsx` 中添加 `compact` prop，compact 模式下缩小节点、隐藏标签、缩小容器高度为 240px。

- [ ] **Step 3: 更新 TaskBoard 支持 compact 模式**

在 `TaskBoard.jsx` 中添加 `compact` prop，compact 模式下去除列标题、缩小卡片、单行显示。

- [ ] **Step 4: 更新 SettingsPanel 主题部分**

SettingsPanel 中的主题相关 UI 切换到 `light`/`dark` 的切换按钮，使用 Lucide `Sun`/`Moon` 图标。

- [ ] **Step 5: 提交**

```bash
git add .
git commit -m "chore: remove old CanvasPanel and theme files, add compact mode to DAG/TaskBoard"
```

---

### Task 12: 响应式适配

**文件:**
- 修改: `frontend/src/components/Layout/ChatPanel.jsx`（汉堡菜单）
- 修改: `frontend/src/styles/global.css`（已有 @media 规则）

- [ ] **Step 1: ChatPanel 添加汉堡菜单按钮**

在 `ChatPanel.jsx` 的 chat-header 最左侧添加汉堡菜单按钮（`<Menu size={18} />`），仅在 ≤1279px 时显示。点击切换侧边栏 mobile 状态。

- [ ] **Step 2: 侧边栏 mobile 模式**

Sidebar 添加 `mobileOpen` prop，使用 `sidebar-overlay` + `sidebar mobile-open` CSS 类实现浮层侧边栏。

- [ ] **Step 3: 验证各断点**

- ≥1280px：侧边栏可见 + 聊天居中 700px + 面板按钮
- 768-1279px：汉堡菜单 + 聊天居中 600px + 面板 320px
- <768px：汉堡菜单 + 聊天全宽 padding 16px + 无面板按钮

- [ ] **Step 4: 提交**

```bash
git add .
git commit -m "feat: add responsive hamburger menu and mobile sidebar overlay"
```

---

### Task 13: 最终验证与修复

- [ ] **Step 1: 全面功能验证**

```bash
cd frontend && npm run dev
```

验证清单：
1. 浅色/深色主题切换正常
2. 侧边栏搜索、置顶、拖拽、右键菜单正常
3. Agent 选择器（新建/+和@触发）正常
4. 单聊/群聊顶栏区分正常
5. 消息发送、流式接收、停止生成正常
6. 代码块渲染、特殊标签（options/clarify/mockup）正常
7. 内联 DAG/任务/部署卡片折叠展开正常
8. 右侧面板滑出/关闭/常驻/标签切换正常
9. 响应式断点切换正常
10. 所有图标为 Lucide 线性图标（无 emoji）

- [ ] **Step 2: 修复发现的问题**

- [ ] **Step 3: 最终提交**

```bash
git add .
git commit -m "fix: final polish and bug fixes for Coze redesign"
```
