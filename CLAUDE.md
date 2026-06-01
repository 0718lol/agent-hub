# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AgentHub — IM-style multi-Agent collaboration platform. Users chat with 7+ pre-built AI agents (PM, frontend, backend, tester, devops, designer, builder) plus runtime custom agents. Backend orchestrates LLM streaming and agent-to-agent task assignment over WebSocket; frontend renders chat + a "canvas" panel (DAG, tasks, code preview, deploy log).

Built for the AI Fullstack Competition. xmz's portion focuses on the **eval harness framework** (see `backend/app/harness/` and `backend/app/tools/`) and the **debate sandbox** that intercepts complex queries before normal agent dispatch.

## Commands

```bash
# Backend (FastAPI + WebSocket on :8000)
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# Frontend (Vite dev server on :3000, proxies /api and /ws → :8000)
cd frontend
npm install
npm run dev

# Eval harness — run judge tools against test suites
cd backend
python -m app.harness.cli list                                   # list suites
python -m app.harness.cli run --suite interaction_judge          # run one
python -m app.harness.cli run --suite all -o report.json --html report.html

# Debate harness smoke test (requires backend running)
cd backend
python test_harness.py
```

No formal test framework — verification is done via `test_harness.py` (WebSocket integration test) and the harness CLI (judge-tool unit tests). No linter configured.

## Architecture

### Request lifecycle (the part that's non-obvious from file names)

User sends a message → frontend WebSocket → `main.py:websocket_endpoint` → routes to one of:

1. **Harness debate intercept** (`routers/harness_handler.py` → `agents/harness_engine.py`) — keyword match or LLM judge decides if the query needs multi-agent debate. If yes, runs Proposer vs Reviewer rounds, sends a debate card to the frontend, and waits for user verdict.
2. **Target agent flow** — single agent reply, with PM optionally assigning downstream agents via `[assign:agent_id]` tags.
3. **Group flow** — PM first, then designer + frontend + backend in parallel (or whoever PM assigned).

**Critical**: generation runs inside `asyncio.create_task` so the WebSocket main loop stays free to receive `stop` messages. Stop signals propagate via `_stop_events: dict[conv_id, asyncio.Event]` checked inside `agent.stream_reply` loops. Awaiting generation in the main loop will silently break the stop button.

### Agent base + prompt engine

`agents/base.py:BaseAgent.stream_reply` is the entry point. It builds messages via `_build_messages` (history from SQLite + inline context + current message, deduped to avoid Anthropic role-alternation violation) and calls `llm_client.chat_stream` with a prompt assembled by `core/prompt_engine.py` (layered: role → task-type-specific addons).

Custom agents are user-created at runtime, persisted in SQLite, loaded into `AGENTS` dict on startup via `_load_custom_agents()`.

### LLM client provider quirks

`core/llm_client.py` is one unified `LLMClient` with provider switch (`openai` / `anthropic` / `claude_code` / `opencode`). The Anthropic path requires **strict user/assistant alternation starting with user** — `_sanitize_for_anthropic` merges consecutive same-role messages and drops leading assistant messages. OpenAI tolerates duplicates; Anthropic 400s. When debugging "consecutive user roles" errors, check `main.py` save-then-fetch sequencing too, not just the sanitizer.

LLM config lives in `backend/data/llm_config.json` (written by `POST /api/settings/llm`). The harness CLI reads the same file.

### Eval harness (xmz's module)

```
backend/app/tools/        — JudgeTool Protocol + 4 implementations
backend/app/harness/      — Runner / Evaluator (4-dim weighted) / Reporter (JSON+HTML) / CLI
backend/app/harness/samples/  — JSON test suites; one per tool
```

Each `JudgeTool` returns a `JudgeResult{decision, score, reason, signals, raw}`. The evaluator scores on 4 weighted dimensions: correctness 40% / confidence 20% / signals 20% / semantic 20%. Adding a new judge = new class in `tools/judge_tools.py` + register in `harness/runner.py:TOOL_REGISTRY` + JSON suite in `harness/samples/`.

Three of the four tools wrap existing logic: `InteractionJudgeTool` → `harness_engine.evaluate_interaction_need`, `QualityJudgeTool` → `auto_evaluator.execute_automated_evaluation`. Don't reimplement; wrap.

### Frontend message protocol

WebSocket messages share `{type, conversation_id, ...}`. Types: `message` (with `stream: bool`), `typing`, `thinking`, `code`, `preview`, `generating`, `task_status`, `read`, `stop`, `harness_debate_result`, `harness_verdict`, `agent_created`, `agent_deleted`, `quality_report`, `deploy_status`.

Streaming messages set `stream: true` and append to the existing streaming bubble for that sender (see `ChatPanel.jsx` WS handler). The first non-streaming chunk closes it.

Backend echoes the user's own message over WS. The frontend filters this with `if (data.sender === 'user') return` to prevent duplicate user bubbles (since `handleSend` already adds locally).

### Inline tag conventions

LLM outputs are parsed for these tags (handled in `main.py` and `MessageBubble.jsx`):

- `[thinking]...[/thinking]` — extracted and broadcast as `thinking` events, stripped from chat
- `[assign:agent_id]` — PM uses this to route to downstream agents; stripped
- `[clarify:q1|q2|...]` — renders a clarification card
- `[options:opt1|opt2|...]` — renders clickable option buttons
- `[mockup:type]` / `[preview:type]` — renders mockup card or triggers canvas preview
- ` ```lang\n...\n``` ` — code blocks are routed to the Canvas panel; chat shows `[code_generated]` placeholder
- Bare HTML (no fence) is detected via regex fallback in `main.py` and also routed to Canvas

### Persistence

SQLite at `backend/data/agenthub.db`. Schema in `core/database.py`. Messages saved with `streaming=False` only after the agent finishes — but the **user message is saved before** fetching history (which is why `base.py:_build_messages` dedups the last entry). LLM error strings (matched on `[LLM Error` / `[LLM 调用出错`) are **not** saved, to avoid feeding them back as context on the next turn.

### What lives outside src

- `xmz/` — xmz's design docs and notes (debate UI plan, harness framework plan, Anthropic API pitfalls)
- `backend/test_harness.py` — encoding-safe WS smoke test for the debate flow
- `backend/harness_report.json` / `harness_full.html` — last harness run outputs
- `资料/` — competition reference materials

## Gotchas

- **Windows GBK terminal** — console output truncates Chinese chars in stack traces. `test_harness.py` does `sys.stdout.reconfigure(encoding='utf-8')`; do the same for any new CLI script.
- **uvicorn `--reload`** can hang on Windows mid-reload (saw it during development). If port 8000 stays in `TIME_WAIT` / zombie state, kill via `powershell -Command "Get-Process python ... Stop-Process -Force"` (using a `.ps1` file — Git Bash mangles `$_` in inline PowerShell).
- **Bash path translation** — Git Bash converts `/F` to `D:/Program Files/Git/F`. Use `cmd //c "..."` or run PowerShell from a file when commands have leading-slash flags.
- **Frontend Vite proxy** is hardcoded to `localhost:8000` in `vite.config.js`. Don't change backend port without updating it.
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




### xmz 任务 
我这部分完成的主要是agent 的harness 部分，现在阶段就是优化agent 的输出 ，有一个需求 帮我 完成一个工具，这个工具能够在调用的时候像 claude code 询问用户 哪种方案 合适 ，或者 yes no else 那种执行效果，在需要用户参与的时候调用这个工具。
在 xmz 任务完成期间 ，自动提交 git 提交 重要改动，本地提交
