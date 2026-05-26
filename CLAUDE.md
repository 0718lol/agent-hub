# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

AgentHub 是一个 IM 风格的多 Agent 协作平台。用户通过聊天界面与多个 AI Agent 对话，驱动需求分析、代码生成、UI 设计、测试验证、部署上线的完整开发流程。后端用 FastAPI + WebSocket 实现实时双向通信，前端用 React 18 + Vite + Zustand 构建微信风格的聊天界面。

## 启动命令

```bash
# 后端 (http://localhost:8000)
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# 前端 (http://localhost:3000)
cd frontend
npm install
npm run dev
```

Vite 开发服务器将 `/api` 和 `/ws` 代理到 `localhost:8000`，无需额外配置。

无测试框架、无 lint 配置、无 Docker 部署文件。

## 核心架构

### 通信协议：WebSocket + REST 双通道

- **REST**：对话历史加载、LLM 配置 CRUD、质量门禁/提示引擎设置、部署触发
- **WebSocket** (`/ws/{conversation_id}`)：实时流式消息、输入状态、思考过程、代码推送、任务状态、部署日志

客户端到服务端的消息类型：`message`（聊天文本）、`stop`（中断生成）、`read`（已读回执）。

服务端到客户端的消息类型：`message`（流式/最终文本）、`typing`、`thinking`、`code`、`preview`、`generating`、`task_status`、`deploy_status`、`quality_report`、`agent_created`/`agent_deleted`。

### Agent 系统与特殊标签协议

所有 Agent 继承自 `backend/app/agents/base.py` 的 `BaseAgent`，只需声明类级别属性（`agent_id`、`name`、`avatar`、`role`、`style`、`system_prompt`）和可选的 `_generate_reply()` 离线回退方法。**不要重写 `stream_reply()` 或 `_build_messages()`**。

Agent LLM 输出中的特殊标签驱动系统行为：

| 标签 | 作用 |
|------|------|
| `[thinking]...[/thinking]` | 提取为思考气泡，不显示在主消息中 |
| `[assign:agent_xxx]` | PM 专用，触发下游 Agent 并发执行 |
| `[create_agent:{json}]` | Agent Builder 专用，运行时注册自定义 Agent |
| `[delete_agent:agent_xxx]` | 删除自定义 Agent |
| `[options:opt1\|opt2]` | 前端渲染为可点击按钮 |
| `[clarify:Q1\|Q2]` | 前端渲染为结构化问答卡片 |
| `[mockup:type]` | 前端渲染 SVG 原型图 |
| \`\`\`language ... \`\`\` | 提取为独立 `code` 事件推送到代码面板；HTML 块额外发送 `preview` 事件 |

**Agent 编排**：WebSocket 处理函数先运行 PM Agent，从其输出中解析 `[assign:...]` 标签确定下游 Agent，然后通过 `asyncio.gather()` 并发执行下游 Agent。无分配时默认团队为 `[designer, frontend, backend]`。

**生成中断**：每个对话维护一个 `asyncio.Event`，收到 `stop` 消息时设置，流式循环每轮检查此事件。

### LLM 集成

`backend/app/core/llm_client.py` 是单例统一 LLM 客户端，支持四种后端：`openai`（OpenAI 兼容格式）、`anthropic`（Claude API）、`claude_code`（Claude Code SDK）、`opencode`（子进程 CLI）。前端设置面板配置 API Key/地址/模型，持久化到 `backend/data/llm_config.json`。未配置时 Agent 自动降级为离线 Mock 回复。

### 质量门禁与提示引擎

- **质量门禁** (`backend/app/core/quality_gate.py`)：基于规则 + 可选 LLM 评判的代码质量评估。支持 Best-of-N 生成（并行 N 个候选，选最高分）和自动重试（失败时注入质量反馈重新生成）。质量报告通过 `quality_report` WebSocket 消息推送前端。
- **提示引擎** (`backend/app/core/prompt_engine.py`)：分层系统提示组装框架，6 个层级（身份→能力→标准→上下文→任务→约束），每层可独立启用/禁用，支持运行时动态调整。

### 前端状态管理

四个 Zustand Store（禁止使用 React Context 或 prop drilling）：

- `chatStore`：对话列表、消息、输入状态、思考内容、已读回执
- `canvasStore`：DAG 图、任务看板、代码面板、预览、部署状态
- `agentStore`：Agent 元数据和在线状态
- `themeStore`：主题切换，持久化到 localStorage

非 React 上下文（如 WebSocket 回调）中直接使用 `useXxxStore.getState()` 访问 store，不用 hook。

### 前端组件树

```
App（三栏布局）
├── Sidebar（左侧 272px 导航）
│   └── SettingsPanel（设置模态框）
├── ChatPanel（中间自适应聊天区）
│   ├── MessageBubble（消息气泡，内含 CodeCard/MockupCard/ClarificationCard）
│   └── InputBar（输入框 + 发送/停止按钮）
└── CanvasPanel（右侧 42% 画布区，300-680px）
    ├── AgentDAG（SVG Agent 关系图）
    ├── TaskBoard（三列看板）
    ├── DiffViewer（Monaco 差异编辑器）
    ├── WebPreview（iframe 沙箱预览）
    └── DeployPanel（终端风格部署控制台）
```

### 主题系统

CSS 自定义属性方案，两个主题文件 `theme-tech-dark.css` 和 `theme-vibrant.css` 通过 `[data-theme]` 选择器切换。主题选择存储在 `localStorage` 的 `agent-hub-theme` 键中。两个 CSS 文件无条件加载，只有匹配当前 `data-theme` 属性的规则生效。

### 重要约束

- **无认证系统**：CORS 配置为 `allow_origins=["*"]`，无用户隔离。这是演示/原型项目。
- **同步 SQLite**：数据库操作是同步的（非 async），启动时 `init_db()` 自动建表和填充默认数据。
- **无路由库**：前端不依赖 React Router，所有导航通过 Zustand 状态切换实现。
- **全局单例**：`llm_client`、`quality_gate`、`prompt_engine` 和 `AGENTS` 字典都是模块级单例。




###xmz 任务 
我这部分完成的主要是agent 的harness 部分，现在阶段就是优化agent 的输出 ，有一个需求 帮我 完成一个工具，这个工具能够在调用的时候像 claude code 询问用户 哪种方案 合适 ，或者 yes no else 那种执行效果，在需要用户参与的时候调用这个工具。
