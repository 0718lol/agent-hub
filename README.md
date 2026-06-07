# AgentHub - 多 Agent 协作平台

> 用 IM 聊天的方式，与多个 AI Agent 协作完成软件开发全流程。

## 项目简介

AgentHub 是一个 IM 风格的多 Agent 协作平台。用户像在钉钉/飞书里聊天一样，与 6 个预置 AI Agent 对话，驱动需求分析、任务拆解、代码生成、UI 设计、测试验证、部署上线的完整开发流程。

## 核心功能

**单聊 & 群聊**
- 与 6 个 Agent 1v1 对话，或创建项目群多 Agent 协作
- 流式输出，Agent 回复逐字显示
- 微信风格的正在输入状态 + 已读回执（✓/✓✓）
- 群聊支持多人同时输入（"3人正在输入..."）

**8 个预置 Agent（新增构建与自定义智能体）**
- PM 小助手 📋 — 需求分析、任务拆解、自动分配任务给其他 Agent
- 前端工程师 🎨 — React 组件、HTML 页面生成、实时预览
- 后端工程师 ⚙️ — API 接口、数据模型
- 测试工程师 🧪 — 测试用例、Bug 分析
- 运维工程师 🚀 — Docker、CI/CD、部署
- 设计顾问 🎯 — UI/UX 设计、SVG 原型图
- 构建工程师 🛠️ — 负责代码编译与项目构建，验证代码的可构建性 **[新增]**
- 自定义智能体 👥 — 支持动态扩展的自定义 Prompt 智能体，便于定制专属角色 **[新增]**

**LLM 集成**
- 支持 OpenAI 兼容格式（小米 MiLM、通义千问、DeepSeek 等）
- 支持 Anthropic 格式（Claude API）
- 前端设置面板一键配置 API Key、地址、模型
- 无 API Key 时自动降级为 Mock 回复
- 配置持久化，重启不丢失

**DeepSeek 风格思考展示**
- Agent 工作时显示实时思考过程
- 思考内容逐字流式展示，带旋转动画
- 代码自动发送到右侧面板，聊天只显示摘要

**任务自动化**
- PM 分配任务后自动触发对应 Agent 工作
- 任务看板自动更新（进行中 → 已完成）
- 生成过程中显示停止按钮，可随时中断
- Agent 可输出内联选项，用户点击继续

**可视化协作画布**
- DAG 图实时展示 Agent 间任务流转
- 任务看板（自动根据 Agent 进度更新）
- 代码面板（语法高亮，Agent 生成的代码自动显示）
- 网页预览（iframe 实时渲染 Agent 生成的 HTML）

**消息系统**
- 代码卡片 — 语法高亮 + 一键复制
- 原型卡片 — SVG 线框图
- 预览标记 — 自动触发右侧面板渲染
- 内联选项 — 可点击的选项按钮
- 需求澄清 — 结构化问答卡片

**代码质量与构建验证 [新增]**
- 内置代码质量门禁 (Quality Gate)，对 Agent 生成的代码进行自动检测，确保符合规范标准
- 代码编译与构建校验，利用构建工程师 (Builder Agent) 实时编译验证，避免存在编译错误的代码
- 多底层能力适配：支持集成 **Claude Code** 和 **OpenCode** 客户端，以实现更强大的底层生成与修改能力

**可视化部署面板 [新增]**
- 右侧画布新增**部署面板 (Deploy Panel)**，实时展示构建进度、部署状态以及服务日志，实现完整的 DevOps 闭环体验

**浏览器 Agent [新增]**
- 打开网页、提取内容、截图、点击、输入、滚动
- Playwright 单例管理器 + 7 个浏览器工具
- 专用浏览器 Agent，支持错误检测 + 自动路由

**Git 集成 [新增]**
- commit、push、create PR
- 安全措施：路径校验、命令白名单、超时控制

**输出校验系统 [新增]**
- Pydantic 校验 + 自动重试
- 四层防御：Tool Calling -> Few-shot -> 校验重试 -> 浏览器兜底
- 反模式检测（问句拦截）

**Code Review Agent [新增]**
- 规则引擎（8 条确定性审查规则）：检测硬编码密码、SQL 注入、命令注入等安全问题
- LLM 审查：深度分析代码正确性、性能、可维护性
- 自愈管道：高危问题自动触发修复重试，直到通过审查

**适配器系统 [新增]**
- 统一适配器接口，支持接入 Claude Code、Codex、Coze、自部署模型等外部 Agent
- 适配器热插拔，通过配置即可切换底层 Agent 引擎，无需修改业务代码

**知识库系统 [新增]**
- 基于 ChromaDB 的向量知识库，支持文档上传与语义搜索
- 为 Agent 提供上下文增强，提升代码生成与需求理解的准确性

**Harness 辩论引擎 [新增]**
- 多 Agent 辩论评估沙盒，多个 Agent 对同一问题提出方案并互相评审
- 支持人类在环裁决，用户可介入决策并选择最优方案

**自动评估器 [新增]**
- 对 Agent 生成的代码进行自动化测试与量化打分
- 综合评估代码质量、覆盖率、性能等维度，输出结构化评估报告

**APM 指标系统 [新增]**
- Agent 执行全链路追踪，记录每次调用的 Token 用量、响应延迟、错误率
- 支持指标聚合与可视化，便于监控 Agent 运行状态和成本分析

**桌面宠物 [新增]**
- Agent 角色浮动桌宠，支持拖拽移动和快捷聊天入口
- 提供趣味交互体验，点击桌宠即可快速发起对话

## 技术栈

**后端**
- FastAPI + WebSocket（实时双向通信）
- httpx 异步流式 HTTP（LLM API 调用）
- Pydantic 数据校验
- Agent 策略模式（可扩展）

**前端**
- React 18 + Vite
- Zustand 状态管理
- 实时 WebSocket 通信
- CSS 动画（思考旋转、输入跳动）

**通信协议**
- WebSocket 实时消息
- 消息类型：message / typing / thinking / code / generating / task_status / read / stop
- 流式输出 + 结构化标签解析（[thinking]、[assign]、[options]、[preview]）

## 快速启动

```bash
# 后端
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev
```

打开 http://localhost:3000

## LLM 配置

1. 打开前端设置面板（右上角齿轮图标）
2. 选择模型提供商（小米 MiLM / DeepSeek / 通义千问 / OpenAI / Claude）
3. 输入 API Key 和模型名称
4. 保存即可

无 API Key 时 Agent 使用 Mock 回复，功能完整可用。

## 集成 Claude Code (Model Context Protocol - MCP)

AgentHub 完美适配了 Anthropic 最新的 **Model Context Protocol (MCP)** 标准协议。你可以将 AgentHub 强大的代码审查、任务分析和需求对齐评估工具作为 “MCP 工具 / 技能” 挂载并集成到 **Claude Code** 终端助理中。

### 1. 注册 MCP 服务至 Claude Code
在终端中，运行以下命令（在本地 Claude Code 会话中，或全局配置中）注册 AgentHub Judge 工具集：

```bash
# 进入后端目录并注册 stdio MCP 服务的完整路径
claude mcp add --transport stdio agenthub-judges -- python d:/project/high-agent-hub/backend/app/mcp_server.py
```
*(注意：请将命令中的 `d:/project/high-agent-hub/backend/app/mcp_server.py` 替换为你实际的绝对路径)*

### 2. 支持的智能体评审工具
集成成功后，Claude Code 将自动发现并支持以下评审工具：
*   `agenthub_quality_judge`：代码质量评估。结合 Python 静态语法检查与大模型对逻辑、健壮性及架构的深度评分（0-100 分），并输出评审报告。
*   `agenthub_complexity_judge`：任务复杂度分析。精准评估需求的技术深度、方案多样性、实现难度与潜在风险。
*   `agenthub_alignment_judge`：需求对齐度审查。校验最终的代码方案是否完美覆盖了原始用户需求规范，防止架构偏离。

### 3. 使用方法示例
在 Claude Code 会话中，你现在可以直接用自然语言让它调用你的工具，例如：
> “请使用 `agenthub_quality_judge` 对我刚刚修改的 backend/app/core/pipeline.py 代码文件进行质量打分和架构评估。”

## 项目结构

```
agent-hub/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI + WebSocket 入口
│   │   ├── agents/              # 8 个 Agent 实现（新增 builder、custom 智能体）
│   │   ├── core/
│   │   │   ├── llm_client.py    # 统一 LLM 客户端
│   │   │   ├── claude_code_client.py  # Claude Code 客户端 [新增]
│   │   │   ├── opencode_client.py     # OpenCode 客户端 [新增]
│   │   │   ├── quality_gate.py  # 代码质量门禁 [新增]
│   │   │   ├── quality_standards.py  # 质量标准配置 [新增]
│   │   │   ├── prompt_engine.py # 结构化 Prompt 编译器 [新增]
│   │   │   ├── websocket.py     # WS 连接管理
│   │   │   └── config.py        # 配置
│   │   └── routers/             # API 路由
│   ├── data/
│   │   └── llm_config.json      # LLM 配置持久化
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Layout/          # 三栏布局 + 设置面板
│   │   │   ├── Chat/            # 聊天组件（消息、输入、选项）
│   │   │   └── Canvas/          # 画布组件（DAG、任务、代码、预览、DeployPanel[新增]）
│   │   ├── stores/              # Zustand 状态管理
│   │   └── utils/               # WebSocket 客户端
│   └── package.json
└── README.md
```

## 测试覆盖

**后端测试：317 个**（14 个测试文件）

| 测试类别 | 测试数 | 覆盖模块 |
|---------|--------|---------|
| 安全专项测试 | 60 | SSRF 防护（31）、路径穿越防护（18）、MCP 命令注入防护（6）、加密模块（5） |
| 质量门禁测试 | 30 | 规则引擎、评分逻辑、输出类型检测 |
| 输出校验测试 | 26 | 反模式检测、格式合规、标签检查 |
| 集成测试 | 75 | Agent 编排流（7）、WebSocket 生命周期（16）、数据库 CRUD（33） |
| AST 沙盒测试 | 19 | 基本执行（7）、安全拦截（6）、边界情况（6） |
| 输出校验测试（新增） | 21 | Pydantic 校验、反模式检测、自动重试 |
| 浏览器工具测试（新增） | 14 | Playwright 自动化、页面操作、截图 |
| Git 工具测试（新增） | 14 | commit、push、create PR |
| 其他测试 | 45 | Agent 回复逻辑、API 端点、配置持久化、工具注册 |

**前端测试：91 个**（7 个测试文件）

**总计：408 个**

| 测试类别 | 测试数 | 覆盖模块 |
|---------|--------|---------|
| Store 测试 | 55 | chatStore（25）、canvasStore（18）、agentStore（12） |
| WebSocket 测试 | 12 | 连接、鉴权、消息收发、断开重连 |
| 组件测试 | 17 | SettingsPanel（Tab 切换、设置保存、主题切换） |
| 其他测试 | 7 | themeStore、uploadStore |

**核心模块覆盖率**

| 模块 | 覆盖率 |
|------|--------|
| quality_standards.py | 87% |
| config_persistence.py | 80% |
| crud/messages.py | 98% |
| crud/agents.py | 91% |
| crud/cron.py | 91% |
| config.py | 76% |
| _engine.py | 76% |
| pm.py | 76% |
| ast_interpreter.py | 58% |
| agent_orchestrator.py | 62% |
| websocket.py | 47% |

**CI/CD**: GitHub Actions 自动运行 Ruff + pytest + ESLint + Bandit + Vitest
