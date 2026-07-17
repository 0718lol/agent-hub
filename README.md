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
- 代码面板（真实多文件树、语法高亮、Git 快照与版本恢复）
- 项目预览（静态多文件 Web、隔离 Vite、API 请求调试、小程序体验二维码）

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

**Reflexion 自我进化引擎 [新增]**
- Agent 从失败中自动学习，不需要人工干预
- 结构化反思：LLM 分析失败原因，提取教训
- 滑动窗口记忆：每个 Agent 最多保留 10 条反思
- 自动注入：生成代码前自动注入历史教训
- 零外部依赖：纯 Python 实现

**技能库系统（Skill Library）[新增]**
- Agent 自动积累可复用的代码技能
- ChromaDB 向量存储 + 关键词检索双模式
- 技能质量评估：基于 Quality Gate 分数
- 滑动窗口：每个 Agent 最多 100 个技能

**自动 Debug Agent [新增]**
- 代码运行出错时自动分析错误、生成修复、验证结果
- 基于 Python stdlib traceback 解析（100% 准确）
- 最小修改原则：只修复出错的行，不重写整个代码
- 沙盒验证：修复后重新运行，防止引入新 bug
- 最多自动重试 3 轮

**Agent 导出/导入 [新增]**
- 团队成员可以导出自定义 Agent 为 JSON 文件
- 其他成员可以导入 JSON 文件创建相同的 Agent
- 导出时自动过滤 API Key 等敏感信息
- 导入时自动处理重名（添加后缀）

**Agent 决策追踪系统 [新增]**
- 交互式追踪树：树形展示 Agent 执行过程，支持展开/折叠
- 实时推送：通过 SSE (Server-Sent Events) 实时推送追踪数据，零延迟
- 错误归因：TraceSpan 记录错误信息，快速定位失败环节
- 甘特图可视化：TraceView 组件展示时间线

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

## 自动化测试

```bash
cd frontend

# Vitest 单元与组件测试
npm test

# 首次运行端到端测试时安装浏览器
npx playwright install chromium

# 生成 -> 预览 -> 对话修改 -> API 发布 -> 历史回滚
npm run test:e2e
```

端到端测试使用真实 React 页面和状态管理，并在浏览器层模拟 HTTP 与 WebSocket 后端，因此不需要模型密钥、Docker 或微信凭证。失败时会在 `frontend/test-results/` 保留截图、视频和 trace；GitHub Actions 同时上传测试报告。

## LLM 配置

1. 打开前端设置面板（右上角齿轮图标）
2. 选择模型提供商（小米 MiLM / DeepSeek / 通义千问 / OpenAI / Claude）
3. 输入 API Key 和模型名称
4. 保存即可

无 API Key 时 Agent 使用 Mock 回复，功能完整可用。

## 构建与发布流水线

部署面板支持自动识别或手动选择以下目标：

| 目标 | 流水线 | 交付结果 |
|------|--------|----------|
| Web | 校验 `index.html` → 打包 → Netlify | 公网地址；未配置 Netlify 时为 ZIP |
| API | Docker 镜像构建 → 受限容器运行 → 反向代理 | 可分享的公网 API 地址 |
| Android APK | 独立容器构建 → 演示密钥或用户 keystore 签名 → 校验 | 受当前用户权限保护的已签名 APK |
| 微信小程序 | 工程校验 → `miniprogram-ci` 体验预览或真实上传 | 凭证齐全时返回二维码或上传代码；否则生成开发者工具上传包 |

Web 公网发布需要在 `.env` 配置 `AGENTHUB_NETLIFY_TOKEN` 和
`AGENTHUB_NETLIFY_SITE_ID`。基础服务使用 `docker compose up --build` 启动；需要本机 Docker
构建能力的演示环境必须显式启用隔离风险开关：

```bash
docker compose -f docker-compose.yml -f docker-compose.local-docker.yml \
  --profile deployment up --build
```

该命令也会构建 `agenthub-runtime-sandbox:local`，其中预装 Node.js 20、Python 3.12、
TypeScript、pytest、numpy、pandas 和 matplotlib。Agent 运行终端命令时，当前生成项目会以只读
归档传入容器，再解压到临时目录执行，因此本地和远程 Docker 都不要求共享项目数据卷；命令
产生的改动不会写回源项目。运行时默认断网并限制 CPU、内存、进程数和最长执行时间。

执行 `npm`、Node、Python 或 pytest 项目命令时，平台会先准备受控依赖缓存。Node 依赖只从
配置的 HTTPS Registry 获取并禁用安装脚本；Python 依赖必须使用 `name==version` 固定版本，
并只允许安装二进制 Wheel。缓存按清单内容哈希存入只读 Docker 卷，后续命令直接复用。依赖
准备阶段使用 `AGENTHUB_RUNTIME_DEPENDENCY_NETWORK`，正式运行阶段仍为 `--network none`。
生产环境建议把该变量指向受防火墙或代理控制的专用出站网络。
依赖缓存卷默认最多保留 100 个，超出后按创建时间清理未被使用的旧缓存。
使用 E2B 时默认选择 `code-interpreter` 模板，并在执行 Python 前验证 numpy、pandas 和
matplotlib；能力不完整时会停止使用该实例并回退到 Docker，而不会把缺包误报成用户代码错误。

沙箱同时具有全局并发数、单租户并发数和排队超时，默认分别为 4、1 和 30 秒，避免多人同时
启动大量容器。可以通过 `AGENTHUB_RUNTIME_SANDBOX_MAX_CONCURRENCY`、
`AGENTHUB_RUNTIME_SANDBOX_MAX_PER_TENANT` 和
`AGENTHUB_RUNTIME_SANDBOX_QUEUE_TIMEOUT` 调整。

Vite 开发预览同样运行在只读源目录的受限 Docker 容器中，默认全局最多 8 个、每租户最多
2 个；超出后自动回收最早的预览实例。可通过 `AGENTHUB_PREVIEW_RUNTIME_MAX_TOTAL` 和
`AGENTHUB_PREVIEW_RUNTIME_MAX_PER_TENANT` 调整。

只需单独构建运行沙箱时，可以执行：

```bash
docker build -f backend/Dockerfile.sandbox \
  -t agenthub-runtime-sandbox:local backend
```

生产环境不要使用该 override，应通过 `DOCKER_HOST` 连接独立构建节点，再使用
`docker compose --profile deployment up --build`。`deployment-worker` 包含 JDK、Android SDK
和 Docker CLI。发布请求写入 Redis Streams，
Worker 重启后会重新认领未完成任务，意外错误最多自动重试两次。微信小程序的正式体验版、审核和发布还需要微信 AppID、上传私钥及微信平台审核，
当前流水线负责生成可上传工程包，不会把打包状态误报为已上线。

部署面板保留当前用户最近 20 条发布记录，支持失败重试、API 历史版本恢复和下线。
运行中的任务会显示排队、生成、依赖安装、构建、签名、上传和完成阶段，并通过持久化状态恢复百分比与带时间戳日志；失败任务可以从当前流水线或发布历史下载完整 `.log` 文件。
流水线运行期间可以点击“取消构建”：排队任务会立即释放项目锁，运行中的 Gradle、Docker、签名或小程序上传进程会被安全终止，并清理已经启动的临时构建容器。
Worker 每小时清理超过 7 天或超出用户保留上限的产物、容器和镜像记录，也可以从界面立即触发清理。
系统演示 APK 密钥只适合测试安装；正式发布应上传自己的 keystore。小程序真实上传使用
`miniprogram-ci`，需要在微信公众平台下载代码上传私钥并配置允许的上传 IP。

Agent 的 Python 与 Shell 工具默认只能通过 E2B 或受限 Docker 沙箱执行，不会回退到 API
主进程。需要访问生成项目的终端命令只使用 Docker 沙箱；宿主 Docker Socket 默认不挂载，
只有本地开发 override 会显式开放。生产环境可以通过 `DOCKER_HOST`、`DOCKER_TLS_VERIFY` 和
`DOCKER_CERT_PATH` 连接隔离的远程 Docker 节点；
APK 构建运行在没有 Docker Socket 的临时容器中；
生成的 API 以非 root、只读文件系统、无 Linux capabilities 的方式运行，并限制 CPU、内存和进程数。
API 容器只加入内部 `agenthub_runtime` 网络，由 `/published/{deployment_id}/` 反向代理访问。
生产环境需将 `AGENTHUB_PUBLIC_BASE_URL` 设置为 AgentHub 的公网 Origin。

上线前执行 `cd backend && python -m app.scripts.preflight --profile production`。完整演示流程、
凭证矩阵、能力边界和验收命令见 [docs/DELIVERY_ACCEPTANCE.md](docs/DELIVERY_ACCEPTANCE.md)。

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

**后端测试：488 个**

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

**前端测试：98 个**（8 个测试文件）

**单元与组件测试总计：586 个，另含 Playwright 端到端场景**

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
