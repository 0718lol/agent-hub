---
name: minimalist-style-ui
description: >
  Minimalist Style UI 编码规范 Skill。当用户需要编写 React 组件、调整 CSS 样式、
  进行页面布局、使用图标、适配主题时，必须使用此 Skill。
  触发关键词：组件、样式、布局、图标、主题、CSS、JSX、UI、界面、弹窗、面板、按钮、
  输入框、侧边栏、聊天、消息气泡、动画、过渡、Lucide、Coze 风格、极简风格。
  适用场景：编写新组件、修改现有组件样式、调整页面布局、添加图标、适配深色/浅色主题、
  实现弹窗/浮窗、处理滚动条、添加动画效果。
---

# Minimalist Style UI 编码规范

本 Skill 定义了 AgentHub 项目的前端编码规范，所有 UI 相关的代码修改必须严格遵循以下规则。

## 一、基础样式规范

### 1.1 CSS 变量系统

所有样式必须使用 CSS 变量，禁止硬编码颜色值、间距值、字号等。

**颜色变量**：
```css
--bg-primary        /* 主背景色 */
--bg-secondary      /* 次背景色 */
--bg-tertiary       /* 三级背景色 */
--text-primary      /* 主文本色 */
--text-secondary    /* 次文本色 */
--text-muted        /* 弱文本色 */
--accent            /* 强调色 */
--accent-bg         /* 强调色背景 */
--border            /* 边框色 */
--green             /* 成功色 */
--orange            /* 警告色 */
--red               /* 错误色 */
```

**间距变量**：
```css
--space-1   /* 4px */
--space-2   /* 8px */
--space-3   /* 12px */
--space-4   /* 16px */
--space-5   /* 20px */
--space-6   /* 24px */
--space-8   /* 32px */
```

**圆角变量**：
```css
--radius-sm   /* 小圆角 */
--radius-md   /* 中圆角 */
--radius-lg   /* 大圆角 */
--radius-xl   /* 超大圆角 */
```

**字号变量**：
```css
--text-xs   /* 12px */
--text-sm   /* 14px */
--text-base /* 16px */
```

**动画变量**：
```css
--duration-fast   /* 快速过渡 */
--duration-slow   /* 慢速过渡 */
--ease-in-out     /* 缓入缓出 */
--ease-out        /* 缓出 */
```

**层级变量**：
```css
--z-overlay   /* 遮罩层 */
--z-dropdown  /* 下拉菜单 */
--z-modal     /* 弹窗层 */
```

**字体变量**：
```css
--font-ui   /* UI 字体 */
```

### 1.2 布局规范

- 使用 flex 布局，不使用 float 或 grid（除非特殊需求）
- 侧边栏宽度：展开 200px，收起 60px
- 聊天区宽度：max-width 800px
- 右侧面板宽度：默认 380px，可拖拽范围 280-680px

### 1.3 响应式断点

```css
@media (max-width: 1279px) { /* 中屏 */ }
@media (max-width: 767px)  { /* 移动端 */ }
```

## 二、图标规则

### 2.1 图标库

统一使用 **Lucide React** 图标库，禁止使用 emoji 或其他图标库。

```jsx
import { X, Search, Settings, Plus, Trash2 } from 'lucide-react'
```

### 2.2 图标尺寸

- 工具栏图标：`size={20}`
- 小图标/关闭按钮：`size={16}`
- 极小图标：`size={14}`

### 2.3 图标按钮样式

```jsx
<button className="header-icon-btn" onClick={handler}>
  <IconName size={20} />
  <span className="icon-tooltip">提示文字</span>
</button>
```

### 2.4 图标颜色

- 默认：`color: var(--text-muted)`
- 悬停：`color: var(--text-primary)`
- 激活/选中：`color: var(--accent)`

## 三、组件写法规范

### 3.1 组件结构

```jsx
import React from 'react'
import { IconName } from 'lucide-react'
import { useStore } from '../../stores/storeName'

export default function ComponentName({ prop1, prop2 }) {
  const state = useStore((s) => s.stateField)

  return (
    <div className="component-name">
      {/* 组件内容 */}
    </div>
  )
}
```

### 3.2 状态管理

使用 Zustand Store，禁止使用 React Context 或 prop drilling。

```jsx
// 在组件中使用
const value = useStore((s) => s.value)

// 在非 React 上下文（如 WebSocket 回调）中使用
const value = useStore.getState().value
```

### 3.3 弹窗/浮窗组件结构

```jsx
{showPopup && (
  <>
    <div className="popup-backdrop" onClick={onClose} />
    <div className="popup-container">
      <div className="popup-header">
        <span>标题</span>
        <button className="slide-panel-btn" onClick={onClose}>
          <X size={16} />
        </button>
      </div>
      <div className="popup-body">
        {/* 内容 */}
      </div>
    </div>
  </>
)}
```

## 四、代码示例

### 4.1 按钮样式

**工具栏按钮**：
```css
.coze-toolbar-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  display: flex;
  align-items: center;
}
.coze-toolbar-btn:hover {
  color: var(--text-primary);
}
```

**主要按钮**：
```css
.agent-create-btn {
  padding: 6px 14px;
  border-radius: var(--radius-md);
  border: none;
  background: var(--accent);
  color: white;
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  font-family: var(--font-ui);
}
```

### 4.2 弹窗样式

**居中悬浮窗**：
```css
.task-popup {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  min-width: 480px;
  max-width: min(720px, 90vw);
  max-height: 80vh;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  z-index: var(--z-modal);
  display: flex;
  flex-direction: column;
  animation: scaleUp 0.2s var(--ease-out);
}
```

**弹窗遮罩**：
```css
.task-popup-backdrop {
  position: fixed;
  inset: 0;
  z-index: var(--z-overlay);
}
```

**弹窗头部**：
```css
.task-popup-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
  flex-shrink: 0;
}
```

**弹窗内容区**：
```css
.task-popup-body {
  flex: 1;
  overflow: auto;
  padding: var(--space-4);
}
```

### 4.3 滚动条隐藏

必须同时兼容三个浏览器引擎：

```css
.container {
  overflow-y: auto;
  scrollbar-width: none;           /* Firefox */
  -ms-overflow-style: none;        /* IE/Edge */
}
.container::-webkit-scrollbar {
  display: none;                   /* Chrome/Safari */
}
```

**重要**：确保选择器命中实际滚动的元素，而不是父容器。

### 4.4 动画效果

**缩放入场动画**：
```css
@keyframes scaleUp {
  from { transform: scale(0.95); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}

.popup {
  animation: scaleUp 0.2s var(--ease-out);
}
```

**过渡动画**：
```css
.element {
  transition: width var(--duration-slow) var(--ease-out),
              border-color var(--duration-slow) var(--ease-out);
}
```

### 4.5 输入框样式

```css
.agent-create-textarea {
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: var(--text-sm);
  font-family: var(--font-ui);
  outline: none;
  resize: vertical;
  min-height: 120px;
  transition: border-color var(--duration-fast) var(--ease-in-out);
}
.agent-create-textarea:focus {
  border-color: var(--accent);
}
.agent-create-textarea::placeholder {
  color: var(--text-muted);
}
```

### 4.6 侧边栏对话项

```jsx
<div className="conversation-item" onClick={onClick}>
  <div className="conv-avatar">
    <IconAvatar agentId={agent?.agent_id} size={36} />
  </div>
  <div className="conv-info">
    <div className="conv-name">{name}</div>
    <div className="conv-time">{time}</div>
  </div>
</div>
```

### 4.7 头像组件

```jsx
// IconAvatar.jsx - 支持 Lucide 图标和自定义图片
export default function IconAvatar({ agentId, iconKey, size = 32 }) {
  const agents = useAgentStore((s) => s.agents)
  const agent = agents.find((a) => a.agent_id === agentId)
  
  // 自定义图片头像
  const avatarUrl = agent?.avatar?.startsWith('/') || agent?.avatar?.startsWith('http')
    ? agent.avatar
    : null

  if (avatarUrl) {
    return (
      <img
        src={avatarUrl}
        alt={agent?.name || ''}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          borderRadius: 'inherit',
        }}
      />
    )
  }

  // Lucide 图标头像
  const Icon = getIconForAgent(iconKey || agentId)
  return <Icon size={size * 0.55} />
}
```

## 五、特殊约束

### 5.1 禁止事项

1. **禁止硬编码颜色**：不得使用 `#fff`、`rgba(0,0,0,0.5)` 等硬编码颜色值，必须使用 CSS 变量
2. **禁止内联样式设置颜色**：不得在 style 中设置 `color: '#64748b'`，应使用 `color: 'var(--text-secondary)'`
3. **禁止使用 emoji**：所有图标必须使用 Lucide React，不得使用 🗑️ 🌐 🚀 等 emoji
4. **禁止使用 React Context**：状态管理统一使用 Zustand Store
5. **禁止新增样式规则**：只能使用本文档中定义的 CSS 变量和样式规则，不得自行新增

### 5.2 主题适配

所有组件必须支持深色/浅色主题切换，通过 CSS 变量自动适配：

```jsx
// 获取当前主题
const theme = useThemeStore((s) => s.theme)

// Monaco Editor 主题跟随
theme={theme === 'light' ? 'vs' : 'vs-dark'}
```

### 5.3 定位上下文

使用 `position: absolute` 或 `position: fixed` 时，确保父容器有正确的定位上下文：

```css
.parent {
  position: relative;  /* 为子元素的 absolute 定位提供上下文 */
}
```

### 5.4 overflow 处理

当父容器有 `overflow: hidden` 时，弹出的内容会被裁切。解决方案：
- 将弹出内容移出 overflow 容器
- 使用 `position: fixed` 定位
- 通过 `getBoundingClientRect()` 计算位置

### 5.5 文件上传

使用 `/api/upload` 端点，返回格式：
```json
{
  "status": "uploaded",
  "original_name": "文件名",
  "stored_name": "uuid.ext",
  "url": "/uploads/uuid.ext",
  "content_type": "image/png",
  "size": 12345,
  "is_image": true
}
```

Vite 需要配置代理：
```js
'/uploads': 'http://localhost:8000'
```

## 六、参考文件

完整的修改记录和详细示例请参考：
- [原始技术记录](references/skill_source_clean.md)
