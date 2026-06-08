# AgentHub 技术架构文档

## 1. 系统概述

AgentHub 是一个 IM 风格的多 Agent 协作平台。用户可以像在钉钉/飞书中聊天一样，与多个预置 AI Agent 对话，驱动软件开发全流程——从需求拆解、UI 设计、前后端编码、测试到部署，全部在群聊界面中完成。

核心设计原则：
- **IM 优先**：所有交互基于聊天消息流，降低用户学习成本
- **Agent 即插件**：每个 Agent 是独立的 Python 类，通过注册中心动态管理
- **流式输出**：所有 LLM 响应通过 WebSocket 实时推送，支持中断
- **质量自愈**：输出经过质量门禁检测，不合格自动重试

## 2. 技术栈

| 层级       | 技术                                                    |
| ---------- | ------------------------------------------------------- |
| 后端框架   | Python 3.12 + FastAPI + WebSocket                       |
| 前端框架   | React 18 + Zustand + Vite                               |
| 数据库     | SQLite (WAL 模式) + SQLModel (SQLAlchemy)               |
| 缓存/广播  | Redis (可选，用于 WebSocket 多实例 Pub/Sub 广播)        |
| LLM 客户端 | httpx，支持 OpenAI / Claude / Ollama 多后端             |
| 协议       | MCP (Model Context Protocol) Stdio 桥接                 |
| 容器化     | Docker + docker-compose                                 |
| 代码质量   | Ruff (linter/formatter)                                 |

## 3. 核心架构

### 3.1 应用入口与生命周期

- **位置**: backend/app/main.py
- **框架**: FastAPI，使用 lifespan 上下文管理器处理启动/关闭
- **启动时**: 初始化数据库 (init_db)、加载 LLM 配置、启动 DaemonScheduler、注册所有路由
- **关闭时**: 停止 DaemonScheduler、关闭浏览器会话和终端会话
- **中间件**: CORS、RequestId 日志追踪、API 密钥/IP 鉴权
- **路由挂载**: 18 个独立路由模块，统一挂载在 /api 前缀下

**路由模块清单**:

| 路由模块             | 路径前缀           | 职责                       |
| -------------------- | ------------------ | -------------------------- |
| agents               | /api/agents        | Agent 管理与查询           |
| conversations        | /api/conversations | 会话与消息 CRUD            |
| ws                   | /ws                | WebSocket 实时通信端点     |
| settings             | /api/settings      | LLM 与 HIL 配置           |
| quality              | /api/quality       | 质量门禁设置               |
| prompt               | /api/prompt        | 提示词引擎配置             |
| mcp                  | /api/mcp           | MCP 工具管理               |
| sandbox              | /api/sandbox       | 代码沙盒执行               |
| benchmark            | /api/benchmark     | 基准测试执行               |
| speech               | /api/speech        | STT 设置与语音转录         |
| webhook              | /api/webhook       | Slack & Telegram 回调      |
| workflows            | /api/workflows     | 工作流导入/导出/编译       |
| tools                | /api/tools         | 工具列表与测试             |
| uploads              | /api/uploads       | 文件上传                   |
| cron                 | /api/cron          | 定时任务管理               |
| adapters             | /api/adapters      | Agent 适配器管理与代理     |
| knowledge            | /api/knowledge     | 知识库 CRUD 与语义检索     |
| harness              | /api/harness       | Harness 辩论沙盒 API       |

### 3.2 Agent 体系

- **基类位置**: backend/app/agents/base.py
- **注册中心位置**: backend/app/services/agent_registry.py

**BaseAgent** 是所有 Agent 的抽象基类，提供：
- stream_reply() — 流式生成回复，支持工具调用循环（最多 5 轮）
- _build_messages() — 构建 LLM 消息数组，包含历史裁剪（约 12000 字符上限）
- _get_tools_prompt() — 将工具描述注入系统提示词
- PromptEngine 集成 — 自动检测任务类型，分层注入提示词

**内置 Agent（7 个）**:

| Agent ID         | 类名              | 职责                          |
| ---------------- | ----------------- | ----------------------------- |
| agent_pm         | PMAgent           | 规划需求、拆解任务、分配工作  |
| agent_frontend   | FrontendAgent     | 开发 React 前端组件           |
| agent_backend    | BackendAgent      | 编写 Python 后端 API          |
| agent_tester     | TesterAgent       | 编写与执行 pytest 测试        |
| agent_devops     | DevopsAgent       | 配置 Docker 容器和部署        |
| agent_designer   | DesignerAgent     | UI/UX 设计及样式美化建议      |
| agent_builder    | AgentBuilderAgent | 协助用户创建自定义 Agent      |
| agent_reviewer   | CodeReviewerAgent | 代码审查（规则引擎 + LLM 审查 + 自愈管道） **[新增]** |

**CustomAgent** (backend/app/agents/custom.py): 支持用户通过 [create_agent:{json}] 标签动态创建自定义 Agent，持久化到数据库。

### 3.3 StateGraph 引擎

- **位置**: backend/app/core/state_graph.py
- **作用**: 管理多 Agent 之间的任务流转状态
- **设计**: 基于 Pydantic 的 GraphState 模型，追踪已完成节点和已分配 Agent
- **状态字段**:
  - completed_nodes — 已完成的 Agent 节点列表
  - assigned_agents — 被分配任务的 Agent 列表
  - {agent}_response — 各 Agent 的输出结果（pm/designer/frontend/backend/tester/devops）
  - {agent}_feedback — PM 对各 Agent 的反馈评价
  - original_prompt — 用户原始输入
- **兼容性**: 提供 get() / __getitem__() 字典式访问，支持 model_extra 动态字段
- **HIL 支持**: 支持 Human-in-the-Loop 检查点持久化，用户可暂停/恢复流程

### 3.4 Agent 编排流

- **位置**: backend/app/services/agent_orchestrator.py
- **核心流程**:

用户消息 → WebSocket 接收 → PM Agent 拆解任务（输出包含 [assign:agent_xxx] 标签）→ 编排器解析标签分配任务 → 多 Agent 并行执行（asyncio.gather）→ 流式输出 → WebSocket 广播 → 前端渲染 → 质量门禁检测（不合格则自动重试）

- **关键协议标签**:
  - [assign:agent_xxx] — PM 指定任务分配给某个 Agent
  - [thinking]...[/thinking] — Agent 思考过程，前端折叠展示
  - [create_agent:{json}] — 动态创建自定义 Agent
  - [tool_call:name]{params}[/tool_call] — Agent 调用运行时工具
- **停止机制**: 每个会话维护独立的 asyncio.Event 停止信号，用户可通过 WebSocket 发送 stop 指令中断生成
- **检查点恢复**: resume_graph_from_checkpoint() 支持从 HIL 检查点恢复执行

### 3.5 WebSocket 双通道通信

- **后端位置**: backend/app/core/websocket.py + backend/app/routers/ws.py
- **前端位置**: frontend/src/utils/websocket.js
- **端点**: ws://host/ws/{conversation_id}
- **鉴权**: 支持 x-api-secret Header 或 ?token= Query 参数；无密钥时仅允许本机连接

**ConnectionManager**:
- 维护 active_connections: dict[str, set[WebSocket]]，按会话 ID 分组管理连接
- 每个 WebSocket 绑定独立的 asyncio.Lock 防止并发写入冲突
- 懒启动 Redis Pub/Sub 监听任务（首连接时触发）

**广播策略**:
- 优先通过 Redis Pub/Sub 发布到 agenthub:ws_broadcast 频道（支持多实例部署）
- Redis 不可用时自动降级为本地广播
- 消息类型: message, typing, thinking, code, deploy_status, task_status

**前端 WSClient**:
- 指数退避重连（1s 基础延迟，最大 30s）
- 连接状态追踪: connected / reconnecting / disconnected
- 状态变更监听器模式，UI 组件可订阅连接状态
- 离线消息队列，重连后自动补发

### 3.6 质量门禁

- **位置**: backend/app/core/quality_gate.py + backend/app/core/quality_standards.py
- **配置**: 可开关，支持 max_retries（重试次数）、best_of_n（候选数量）、use_llm_judge（LLM 评判）

**评估流水线**:
1. 从 Agent 输出中提取代码块
2. 自动检测输出类型（html / python / api / document）
3. 运行规则引擎检查（即时、确定性）
4. 可选运行 LLM-as-Judge（语义评估）
5. 不合格则注入反馈到提示词，自动重试
6. Best-of-N: 并行生成 N 个候选，取最高分
7. 广播质量报告到前端

### 3.7 MCP 集成

- **位置**: backend/app/core/mcp_bridge.py + backend/app/mcp_server.py
- **作用**: 将 AgentHub 注册为 Claude Code 等外部工具的 MCP Server
- **通信方式**: Stdio 管道，基于 JSON-RPC 协议
- **提供工具**: agenthub_quality_judge, agenthub_complexity_judge, agenthub_alignment_judge
- **生命周期**: MCPServerProcess 管理子进程的启动、通信、关闭

### 3.8 工具系统

- **位置**: backend/app/tools/ 目录
- **基类**: AgentTool (backend/app/tools/registry.py)
- **注册表**: ToolRegistry 全局单例，支持运行时注册/注销

**内置工具**:

| 工具模块                     | 功能               |
| ---------------------------- | ------------------ |
| browser_tools.py             | 浏览器自动化操作   |
| code_agent_tools.py          | 代码生成与分析     |
| code_interpreter_tools.py    | 代码执行沙盒       |
| file_ops.py                  | 文件读写操作       |
| http_request.py              | HTTP 请求发送      |
| web_search.py                | 网页搜索           |
| stateful_terminal_tool.py    | 有状态终端会话     |
| block_editor_tools.py        | 块编辑器操作       |
| judge_tools.py               | 质量评判工具       |
| code_review_rules.py          | 8 条确定性审查规则（硬编码密码、SQL 注入、命令注入等） |
| code_review_service.py        | 混合审查服务（规则引擎 + LLM）+ 自愈管道               |

工具通过 [tool_call:name]{params}[/tool_call] 协议在 LLM 输出中被识别和执行。

### 3.9 Agent 适配器系统

- **位置**: backend/app/adapters/ 目录
- **基类**: AgentAdapter (backend/app/adapters/base.py)
- **注册表**: AdapterRegistry 全局单例 (backend/app/adapters/registry.py)
- **API**: backend/app/routers/adapters.py，提供 CRUD、连接测试、本地代理启停

**功能定位**: 统一接入外部 Agent 平台，将 Claude、Codex、Coze、自部署（Dify/SelfDeployed）、自建 Agent 封装为标准接口，使上层编排器无需关心底层平台差异。

**核心组件**:

| 组件                 | 说明                                                         |
| -------------------- | ------------------------------------------------------------ |
| AgentAdapter 基类    | 定义 stream_reply() 流式接口和 validate_config() 校验接口   |
| AdapterConfig        | 统一配置数据类（api_key、api_url、model、tool_mode 等）      |
| AdapterRegistry      | 注册/注销/查询适配器实例，持久化配置到 data/adapters.json    |
| AdapterAgent 包装器  | 将适配器包装为 BaseAgent 接口，无缝接入编排器               |
| 本地 Agent 代理      | 通过 Node.js proxy 桥接 OpenCode serve，支持本地 Agent 接入 |

**技术特点**:
- 延迟导入：各平台适配器按需加载，缺失依赖时优雅降级而不影响整体启动
- 工具模式：支持 agent（工具注入）、text（纯文本）、auto（自动检测）三种模式
- 前端可配置：支持自定义显示名称、头像、简介，适配器状态实时查询

### 3.10 知识库与 RAG 系统

- **RAG 引擎**: backend/app/core/rag_engine.py
- **API**: backend/app/routers/knowledge.py
- **向量数据库**: ChromaDB（嵌入式，数据持久化到 data/chroma_db/）

**功能定位**: 为 Agent 提供外部知识增强能力，支持文档上传、分块、向量化存储和语义检索，检索结果自动注入 Agent 上下文。

**核心组件**:

| 组件               | 说明                                                         |
| ------------------ | ------------------------------------------------------------ |
| RAGEngine 单例     | 提供 add_document()、query()、build_context_prompt() 接口    |
| split_text()       | 语义感知型递归文本分块（段落→行→标点→字符逐级切分）         |
| ChromaDB 集合      | 每个知识库对应独立 collection，余弦相似度检索               |
| KnowledgeDoc 模型  | 数据库持久化文档元数据（文件名、路径、块数、字符数）         |

**技术特点**:
- 分块参数：chunk_size=500 字符，overlap=80 字符，Top-K=5
- Embedding：使用 ChromaDB 内置 all-MiniLM-L6-v2 模型，零配置
- 多知识库：支持创建多个独立知识库，每个对应独立的 ChromaDB collection
- 上下文注入：build_context_prompt() 将检索结果格式化为带来源和相关度的提示词

### 3.11 Harness 辩论引擎

- **引擎**: backend/app/agents/harness_engine.py
- **WebSocket 集成**: backend/app/routers/harness_handler.py
- **API**: backend/app/routers/harness.py

**功能定位**: 多 Agent 辩论评估沙盒，对复杂技术问题自动触发 Proposer（激进派）vs Reviewer（保守派）的对抗辩论，用户最终裁决采纳方案。

**三段式工作流**:

| 阶段                       | 函数                        | 说明                                   |
| -------------------------- | --------------------------- | -------------------------------------- |
| 1. 意图拦截                | evaluate_interaction_need() | 关键词匹配 + LLM 判断是否需要辩论     |
| 2. 辩论沙盒                | run_debate_arena()          | Proposer vs Reviewer 多轮代码对抗      |
| 3. 结果打包                | format_debate_response()    | 按前端协议输出候选方案 JSON            |

**技术特点**:
- 关键词快速匹配：预设"还是"、"对比"、"vs"等选型关键词，命中即触发，跳过 LLM 判断
- 前端裁决协议：支持 accept_a（采纳激进派）、accept_b（采纳审查派）、reject_all（重新讨论）
- 优雅降级：Harness 异常时自动放行给普通 Agent 处理，不影响主流程
- 辩论日志持久化：辩论结果自动保存到数据库

### 3.12 自动评估器 Agent

- **位置**: backend/app/agents/auto_evaluator.py

**功能定位**: 对 Agent 生成的代码进行自动化测试与量化打分，串联静态语法检查和 LLM 深度审查，输出综合评估报告。

**评估流水线**:

| 步骤                  | 函数                          | 说明                                   |
| --------------------- | ----------------------------- | -------------------------------------- |
| 1. 代码提取           | extract_code_from_text()      | 从 Markdown 中提取第一个代码块         |
| 2. 静态语法检查       | static_syntax_check()         | Python 使用 ast.parse，其他语言跳过    |
| 3. LLM 深度打分       | llm_as_a_judge_scoring()      | 三维度评分：逻辑正确性(40)、健壮性(30)、架构(30) |
| 4. 综合报告           | execute_automated_evaluation()| 合并静态检查扣分 + LLM 打分            |

**技术特点**:
- 评分阈值：总分 >= 60 为通过，语法错误扣 20 分
- 容错解析：LLM 返回非标准 JSON 时使用正则提取评分字段
- 默认中位分：LLM 调用异常时返回 50 分默认值，保证流程不阻塞

### 3.13 APM 指标收集

- **位置**: backend/app/core/metrics.py
- **单例**: MetricsCollector (全局变量 metrics)

**功能定位**: 收集 Agent 执行全过程的性能指标和链路追踪数据，为前端 EvalDashboard 和 TraceView 提供数据源，支持导出到 Langfuse APM 平台。

**核心数据模型**:

| 模型           | 说明                                                         |
| -------------- | ------------------------------------------------------------ |
| TraceSpan      | 子跨度（LLM 调用、工具执行、RAG 检索），记录耗时和状态      |
| TraceStep      | 单个 Agent 执行步骤，包含多个 TraceSpan                      |
| TaskTrace      | 完整的用户请求→多 Agent 响应链路                             |

**技术特点**:
- ContextVar 传播：通过 contextvars 实现跨异步调用的 trace/step 上下文无侵入传递
- 内存限制：保留最近 100 条 Trace、每个 Agent 最近 50 条指标数据
- Langfuse 集成：完成的 Trace 自动异步导出到 Langfuse（需配置环境变量）
- Dashboard 数据：提供 Agent 统计、Best-of-N 命中率、沙盒执行成功率、质量门禁通过率

### 3.14 Reflexion 自我进化引擎

- **位置**: backend/app/core/reflexion_engine.py
- **核心类**: ReflexionEngine

**功能定位**: Agent 从失败中自动学习的自我进化引擎，通过结构化反思提取教训，并在后续任务中自动注入历史经验，实现无需人工干预的持续改进。

**核心方法**:

| 方法            | 说明                                                         |
| --------------- | ------------------------------------------------------------ |
| reflect()       | 结构化反思，LLM 分析失败原因并提取可复用教训                 |
| get_context()   | 获取反思上下文，将历史教训格式化为可注入提示词的内容         |
| should_retry()  | 重试判断，基于历史反思决定是否值得再次尝试                   |

**集成点**:
- 在 `agent_orchestrator.py` 中的质量评估后触发反思，当质量门禁检测不通过时自动调用 `reflect()` 分析失败原因
- Agent 生成代码前通过 `get_context()` 自动注入历史教训，提高生成质量

**技术特点**:
- 滑动窗口记忆：每个 Agent 最多保留 10 条反思记录，自动淘汰旧记录
- 纯内存存储：反思数据不持久化，避免敏感信息泄露
- 零外部依赖：纯 Python 实现，不引入额外框架
- 异常隔离：所有反思操作在 try/except 中执行，不影响主流程

### 3.15 技能库系统

- **位置**: backend/app/core/skill_library.py
- **核心类**: SkillLibrary

**功能定位**: Agent 自动积累可复用的代码技能库，基于 ChromaDB 向量存储实现语义检索，让 Agent 在遇到相似任务时自动注入历史成功经验。

**核心方法**:

| 方法 | 说明 |
|------|------|
| add_skill() | 添加技能到库中（向量存储 + 内存字典） |
| search() | 语义检索相关技能（ChromaDB 优先，关键词兜底） |
| extract_skills_from_output() | 从 Agent 输出中提取可复用代码片段 |
| get_stats() | 获取库统计信息 |

**技术特点**:
- 双模式检索：ChromaDB 向量语义搜索 + 关键词匹配兜底，ChromaDB 不可用时自动降级
- 自动提取：从 Agent 成功输出中自动提取代码块作为技能
- 滑动窗口：每个 Agent 最多 100 个技能，自动淘汰低优先级技能
- 零外部依赖（必须）：ChromaDB 为可选依赖，无 ChromaDB 时使用关键词检索

**集成点**:
- 在 `agent_orchestrator.py` 中，Agent 生成代码前自动检索相关技能注入 prompt
- Agent 输出通过质量评估后，自动提取代码片段存入技能库
- 与 Reflexion 引擎协同：反思记录驱动技能提取，技能库提供可复用代码

### 3.16 自动 Debug Agent 架构

- **文件**: `backend/app/core/debug_engine.py` + `backend/app/agents/debug_agent.py`
- **核心类**: DebugEngine、DebugAgent

### 3.16b Agent 决策追踪系统架构

- **核心组件**: TraceSpan（子跨度）+ TraceStep（步骤）+ TaskTrace（完整追踪）
- **可视化**: TraceView（甘特图）+ TraceTreeView（交互式树）
- **实时推送**: TaskTrace.finish() 通过 WebSocket 广播
- **错误归因**: TraceSpan.error 字段记录失败原因

**功能定位**: 代码运行出错时自动分析错误、生成修复并验证结果，实现无人干预的自动修复闭环。

**核心流程**:

| 步骤 | 说明 |
|------|------|
| 1. 代码运行 | Agent 生成的代码在沙盒中执行 |
| 2. 错误解析 | 基于 Python stdlib traceback 模块解析异常堆栈（100% 准确） |
| 3. 修复 prompt | 构建包含错误上下文的修复提示词，遵循最小修改原则 |
| 4. LLM 修复 | 调用 LLM 生成修复代码，仅修改出错的行 |
| 5. 沙盒验证 | 修复后重新运行，验证不引入新 bug |

**集成点**:
- 在 `agent_orchestrator.py` 中，代码块提取后自动触发 Debug Agent
- 与质量门禁协同：修复通过后交由质量门禁二次评估
- 与 Reflexion 引擎协同：修复失败时记录反思，供后续任务参考

**技术特点**:
- 最小修改原则：只修复出错的行，不重写整个代码
- 有限重试：最多自动重试 3 轮，防止无限循环
- 仅对可修复错误触发：SyntaxError、NameError、TypeError 等可自动修复的异常类型才触发 Debug Agent
- 沙盒隔离：修复验证在独立沙盒中执行，不影响主流程

### 3.17 前端 Canvas 组件

- **位置**: frontend/src/components/Canvas/

**功能定位**: 代码预览画布区域的核心可视化组件，提供执行链路追踪、代码差异对比、评估仪表盘和 Agent 流程图展示。

| 组件            | 文件              | 说明                                           |
| --------------- | ----------------- | ---------------------------------------------- |
| TraceView       | TraceView.jsx     | Agent 执行 Trace 甘特图可视化，4 秒轮询刷新    |
| DiffViewer      | DiffViewer.jsx    | 基于 Monaco Editor 的代码展示与 Diff 对比面板  |
| EvalDashboard   | EvalDashboard.jsx | 评估指标仪表盘（Agent 评分、Token 用量等）     |
| AgentFlow       | AgentFlow.jsx     | 基于 ReactFlow 的 Agent 协作流程 DAG 可视化    |
| AgentDAG        | AgentDAG.jsx      | Agent 依赖关系有向图                            |
| DeployPanel     | DeployPanel.jsx   | 部署状态面板                                    |
| WebPreview      | WebPreview.jsx    | HTML 实时预览（iframe 沙盒）                   |
| TaskBoard       | TaskBoard.jsx     | 任务看板视图                                    |

**技术特点**:
- TraceView 使用颜色编码区分不同 Agent（PM 紫色、Frontend 蓝色、Backend 绿色等）
- DiffViewer 内置零依赖 Diff 算法，支持 Lookahead 行移位检测
- AgentFlow 基于 @xyflow/react 实现可拖拽的节点连线图

### 3.16 DesktopPet 桌面宠物系统

- **位置**: frontend/src/components/AgentCharacter/DesktopPet.jsx + DesktopPet.css
- **依赖**: AgentCharacter、DraggableFloating、PetMiniChat 组件

**功能定位**: 可拖拽的桌面宠物浮窗，展示 Agent 角色动画，支持空闲随机动作、双击打开迷你聊天、右键菜单等交互。

**技术特点**:
- 空闲动作池：每 8-18 秒随机触发挥手、跳跃、伸懒腰等动画
- 可拖拽定位：基于 DraggableFloating 实现自由拖拽，位置记忆到 localStorage
- 迷你聊天：双击宠物打开 PetMiniChat 快捷对话窗口
- 虚拟办公室联动：监听 agenthub:open-office 等自定义事件，与 VirtualOffice 视图协同

### 3.17 事件流系统

- **位置**: backend/app/core/event_stream.py
- **单例**: EventStreamManager (全局变量 event_stream_manager)

**功能定位**: 基于 SQLite 的时序事件流管理器，记录会话中的消息、思考、工具调用、工具观察四类事件，并支持将事件流编译为 OpenAI 标准消息列表。

**事件类型**:

| 事件类            | event_type    | 说明                         |
| ----------------- | ------------- | ---------------------------- |
| MessageEvent      | message       | 用户/助手消息                |
| ThoughtEvent      | thought       | Agent 思考过程               |
| ActionCallEvent   | action_call   | 工具调用（名称、参数）       |
| ObservationEvent  | observation   | 工具执行结果（成功/失败）    |

**技术特点**:
- compile_to_messages()：将时序事件流幂等地编译为 OpenAI messages 列表，支持多模态图片
- 工具调用格式化：自动将 ActionCallEvent 转换为 [tool_call:name]{params}[/tool_call] 协议格式
- 错误标准化：失败的 ObservationEvent 自动包装为 {"error": ...} 结构

### 3.18 子进程安全模块

- **位置**: backend/app/core/subprocess_security.py

**功能定位**: 跨平台子进程资源限制与安全终止，防止沙盒代码执行时耗尽宿主机资源。

**核心功能**:

| 函数                      | 平台      | 说明                                   |
| ------------------------- | --------- | -------------------------------------- |
| limit_windows_process()   | Windows   | 通过 Job Object 限制内存和 CPU 时间    |
| release_job_handle()      | Windows   | 释放 Job Object 句柄                   |
| safe_terminate_process_tree() | 跨平台 | 安全终止进程树（taskkill/kill）        |

**技术特点**:
- Windows Job Object：使用 ctypes 调用 kernel32 API，支持 PROCESS_MEMORY、JOB_MEMORY、PROCESS_TIME 限制
- kill-on-job-close：Job Object 设置 KILL_ON_JOB_CLOSE 标志，确保父进程退出时子进程自动终止
- Windows 进程树终止：使用 taskkill /F /T /PID 杀掉整个进程树

### 3.19 代码沙盒管理器

- **位置**: backend/app/core/sandbox_manager.py
- **单例**: SandboxManager (全局变量 sandbox_manager)

**功能定位**: 三级递进式代码执行沙盒调度器，按安全等级自动选择最优执行环境，失败时自动降级。

**沙盒层级（优先级从高到低）**:

| 层级 | 沙盒类型             | 隔离级别       | 说明                                   |
| ---- | -------------------- | -------------- | -------------------------------------- |
| 1    | E2BSandbox           | 云端 MicroVM   | AWS Firecracker 虚拟机，需 API Key     |
| 2    | DockerSandbox        | 本地容器       | Docker 容器隔离，--network none        |
| 3    | SubprocessSandbox    | 本地进程       | 子进程 + 资源限制（ulimit/Job Object） |

**技术特点**:
- Docker 容器：memory 128m、cpus 0.5、network none（零信任网络隔离）
- 输出截断：stdout/stderr 超过 5000 字符自动截断，防止内存溢出
- 支持语言：Python、JavaScript/TypeScript、Shell/Bash
- stdin 注入：支持通过 stdin 管道传入标准输入数据

### 3.20 AST 安全解释器

- **位置**: backend/app/core/ast_interpreter.py
- **类**: SafeASTInterpreter

**功能定位**: 零依赖的异步 Python AST 解释器，将 LLM 生成的代码解析为语法树后逐步执行，白名单内置函数，阻断危险操作。

**安全机制**:

| 机制               | 说明                                           |
| ------------------ | ---------------------------------------------- |
| import 拦截        | 禁止运行时 import 导入模块                     |
| 私有属性拦截       | 禁止访问 __class__ 等私有/魔法属性             |
| 循环熔断           | 最大迭代 1000 步，超出自动终止                 |
| 白名单内置函数     | 仅允许 print/len/range/abs/str/int/float 等安全函数 |

**技术特点**:
- 异步执行：每个 AST 节点通过 async/await 逐步求值，支持协程函数调用
- 输出缓冲：print() 重定向到内部 StringIO 缓冲区，不污染 sys.stdout
- 支持语法：变量赋值、算术运算、布尔逻辑、比较、if/for/while、列表/字典/集合字面量、切片

### 3.21 仓库结构扫描器

- **位置**: backend/app/core/repo_map.py
- **单例**: CodebaseMapScanner (全局变量 codebase_map_scanner)

**功能定位**: 轻量级 AST 代码库分析器，递归扫描工作区目录，提取类、函数、导入等符号定义，生成结构化 Markdown 映射。

**技术特点**:
- Python 文件：使用 ast.parse 提取类名、方法签名、函数签名、import 语句
- JS/TS 文件：使用正则表达式提取 class、function、arrow function、import
- 目录过滤：自动跳过 .git、node_modules、__pycache__、dist 等目录
- 输出格式：Markdown 嵌套列表，包含文件路径、imports、functions、classes/methods

### 3.22 StreamPipeline 流式管线

- **位置**: backend/app/core/pipeline.py

**功能定位**: LLM 流式输出的中间件管线架构，支持链式拦截和转换文本流，实现标签解析、代码块捕获等流式处理。

**核心组件**:

| 组件                   | 说明                                           |
| ---------------------- | ---------------------------------------------- |
| StreamContext          | 流会话上下文，携带 conversation_id 和 agent_id |
| StreamMiddleware       | 中间件抽象基类，定义 on_chunk() 和 finalize()  |
| StreamPipeline         | 管线调度器，按顺序执行中间件链                 |
| UnifiedTagMiddleware   | 统一标签拦截器（[thinking]、[assign]、[create_agent] 等） |
| CodeBlockMiddleware    | Markdown 代码块拦截器，实时广播代码到 Canvas   |

**技术特点**:
- 增量前缀感知扫描：处理流式场景下标签被 chunk 分割的问题，缓冲区保留潜在标签前缀
- 实时广播：thinking 标签内容实时推送到前端气泡，代码块实时推送到 DiffViewer/WebPreview
- 未闭合标签容错：finalize() 阶段将未闭合的标签内容回退为普通文本

### 3.23 缓存抽象层

- **位置**: backend/app/core/cache.py
- **单例**: RedisCache (全局变量 cache)

**功能定位**: 统一的缓存读写接口，Redis 优先 + 内存 LRU 回退，所有操作静默失败不影响主业务。

**API 接口**:

| 方法           | 说明                                   |
| -------------- | -------------------------------------- |
| get/set        | 字符串缓存读写，支持 TTL               |
| get_json/set_json | JSON 自动序列化/反序列化            |
| delete         | 删除单个键                             |
| delete_pattern | 按前缀批量删除（Redis SCAN 迭代）      |

**技术特点**:
- 双层缓存：写入时同步更新 Redis 和内存缓存，读取时 Redis 优先、内存回退
- 内存 LRU：最多 512 条，超限时自动清理过期项
- 静默降级：Redis 连接失败时自动标记断开并回退到内存缓存，绝不抛出异常

### 3.24 Async CRUD 包装器

- **位置**: backend/app/core/async_wrappers.py

**功能定位**: 将所有同步 CRUD 操作通过 asyncio.to_thread() 包装为异步接口，避免数据库操作阻塞事件循环。

**技术特点**:
- 覆盖全部 CRUD 操作：消息、会话、自定义 Agent、文件上传、定时任务、记忆、事件流、HIL 检查点、制品
- 零阻塞：所有数据库 I/O 在独立线程中执行
- 调用透明：异步函数签名与同步原函数一一对应

### 3.25 语音录制 Hook

- **位置**: frontend/src/utils/useVoiceRecorder.js

**功能定位**: React Hook，封装浏览器 MediaRecorder API，实现录音→上传→STT 转录的完整流程。

**技术特点**:
- 自动选择编码：优先 audio/webm;codecs=opus，降级到 audio/webm 或 audio/wav
- 麦克风配置：单声道、16kHz 采样率、回声消除、噪声抑制
- 录音时长计时：通过 setInterval 实时更新 duration 状态
- 错误处理：区分权限拒绝（NotAllowedError）和设备缺失（NotFoundError）

### 3.26 浏览器 Agent 架构

- `browser_manager.py`：Playwright 单例管理器，管理浏览器实例的创建、复用和销毁
- `browser_agent_tools.py`：7 个浏览器工具（打开网页、提取内容、截图、点击、输入、滚动、关闭）
- `browser_agent.py`：专用浏览器 Agent，基于 Playwright 实现网页自动化操作
- 集成：错误检测 + 自动路由，当浏览器操作失败时自动重试或降级处理

### 3.27 输出校验架构

- `output_validator.py`：基于 Pydantic 模型的输出校验器，支持自动重试机制
- 四层防御体系：
  1. **Tool Calling** — 结构化工具调用，确保输出格式正确
  2. **Few-shot** — 示例引导，提高输出质量
  3. **校验重试** — Pydantic 校验失败时自动重试，最多 N 次
  4. **浏览器兜底** — 当结构化输出失败时，通过浏览器 Agent 解析网页获取数据

### 3.28 Git 集成

- `git_tools.py`：提供 Git 操作工具集（commit、push、create PR）
- 安全措施：
  - **路径校验** — 验证仓库路径合法性，防止路径穿越
  - **命令白名单** — 仅允许安全的 Git 子命令
  - **超时控制** — 设置命令执行超时，防止阻塞

### 3.29 LLM 客户端

- **位置**: backend/app/core/llm_client.py
- **传输**: httpx 异步 HTTP 客户端
- **支持后端**: OpenAI API / Claude API / Ollama（本地模型）
- **特性**:
  - 流式输出 (chat_stream)
  - 上下文优化 (ContextOptimizer) — 自动裁剪过长消息、过滤进度条噪音
  - 配置持久化 (config_persistence.py) — LLM 设置保存/加载
  - 错误自定义 (LLMAPIError) — 携带状态码和消息

### 3.30 数据层

- **数据库**: SQLite + SQLModel (SQLAlchemy ORM)
- **位置**: backend/app/core/database.py + backend/app/core/_engine.py
- **模型定义**: backend/app/core/models.py
- **CRUD 操作**: backend/app/core/crud/
- **WAL 模式**: 启用 Write-Ahead Logging，支持读写并发
- **主要实体**: 会话 (Conversation)、消息 (Message)、制品 (Artifact)、自定义 Agent、HIL 检查点
- **文件存储**: backend/app/core/file_storage.py，上传目录 data/uploads/

## 4. 关键设计决策

### 4.1 为什么用 WebSocket 而非 SSE？

- SSE 是单向的（服务器到客户端），无法接收用户的 stop/read 消息
- WebSocket 支持双向通信，用户可以随时中断生成
- WebSocket 支持二进制数据传输（未来扩展文件/图片流）
- 前端需要实时反馈连接状态（connected/reconnecting/disconnected），WebSocket 原生支持

### 4.2 为什么用 SQLite 而非 PostgreSQL？

- 项目定位是内部工具/挑战赛作品，不需要高并发
- SQLite 零配置，开箱即用，无需额外部署
- WAL 模式支持读写并发，足够应对 demo 场景
- SQLModel/SQLAlchemy 抽象层使得未来切换到 PostgreSQL 只需改连接字符串

### 4.3 为什么自建 StateGraph 而非 LangGraph？

- LangGraph 依赖 LangChain 生态，引入重，增加维护负担
- 自建 StateGraph 轻量（基于 Pydantic Model），完全可控
- 更容易集成 WebSocket 流式推送和前端画布渲染
- 支持自定义节点类型和动态 Agent 注册

### 4.4 为什么用 Redis Pub/Sub 而非 Sticky Session？

- 单实例部署时 Redis 是可选的，自动降级为本地广播
- 多实例部署时，Redis Pub/Sub 确保所有连接都能收到消息
- 比 Sticky Session 更灵活，不依赖负载均衡器配置
- Redis 还可用于缓存、限流等其他场景

## 5. 数据流

用户输入 → WebSocket (/ws/{conversation_id}) → Agent 编排器接收消息并保存到数据库 → PM Agent 拆解任务（输出包含 [assign:agent_xxx] 标签）→ 编排器解析标签构建任务分配计划 → 多 Agent 并行执行（asyncio.gather）：

- FrontendAgent: 生成 React 组件代码
- BackendAgent: 生成 Python API 代码
- TesterAgent: 生成 pytest 测试用例
- DesignerAgent: 提供 UI/UX 设计建议

→ 流式输出 → WebSocket 广播（typing → thinking → message）→ 代码块提取 → 前端预览面板渲染 → 质量门禁评估（规则引擎 + LLM Judge）：

- 通过 → 保存制品 (Artifact)
- 不通过 → 注入反馈，自动重试（最多 N 次）

→ DevOps Agent 执行部署模拟 → deploy_status 消息 → 前端展示部署进度

## 6. 目录结构

```
high agent-hub/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI 应用入口、中间件、路由挂载
│   │   ├── mcp_server.py            # MCP Server 入口
│   │   ├── agents/                  # Agent 定义
│   │   │   ├── base.py              #   BaseAgent 基类
│   │   │   ├── pm.py                #   PM Agent（任务拆解与分配）
│   │   │   ├── frontend.py          #   Frontend Agent
│   │   │   ├── backend_agent.py     #   Backend Agent
│   │   │   ├── tester.py            #   Tester Agent
│   │   │   ├── devops.py            #   DevOps Agent
│   │   │   ├── designer.py          #   Designer Agent
│   │   │   ├── builder.py           #   AgentBuilder Agent（创建自定义 Agent）
│   │   │   ├── custom.py            #   CustomAgent（用户自定义）
│   │   │   ├── harness_engine.py    #   Harness 评测引擎 Agent
│   │   │   ├── auto_evaluator.py    #   自动评估 Agent
│   │   ├── adapters/                # Agent 适配器
│   │   │   ├── base.py              #   AgentAdapter 基类 & AdapterConfig
│   │   │   ├── registry.py          #   AdapterRegistry 注册表
│   │   │   ├── adapter_agent.py     #   AdapterAgent 包装器
│   │   │   ├── claude_adapter.py    #   Claude Code 适配器
│   │   │   ├── codex_adapter.py     #   Codex 适配器
│   │   │   ├── coze_adapter.py      #   Coze 适配器
│   │   │   └── self_deployed_adapter.py # 自部署/Dify 适配器
│   │   ├── core/                    # 核心基础设施
│   │   │   ├── config.py            #   应用配置（Settings）
│   │   │   ├── database.py          #   数据库入口（导出所有符号）
│   │   │   ├── _engine.py           #   SQLAlchemy 引擎（打破循环依赖）
│   │   │   ├── models.py            #   SQLModel 数据模型
│   │   │   ├── crud/                #   CRUD 操作
│   │   │   ├── llm_client.py        #   LLM 多后端客户端
│   │   │   ├── websocket.py         #   WebSocket ConnectionManager
│   │   │   ├── state_graph.py       #   StateGraph 引擎
│   │   │   ├── quality_gate.py      #   质量门禁
│   │   │   ├── quality_standards.py #   质量规则与评分标准
│   │   │   ├── quality_retry.py     #   质量重试逻辑
│   │   │   ├── mcp_bridge.py        #   MCP Stdio 桥接
│   │   │   ├── mcp_client.py        #   MCP 客户端
│   │   │   ├── prompt_engine.py     #   提示词引擎（分层注入）
│   │   │   ├── redis.py             #   Redis 连接管理器
│   │   │   ├── rag_engine.py        #   RAG 检索引擎
│   │   │   ├── ast_interpreter.py   #   AST 安全解释器
│   │   │   ├── subprocess_security.py # 子进程安全模块
│   │   │   ├── cache.py             #   缓存抽象层（Redis + 内存回退）
│   │   │   ├── async_wrappers.py    #   Async CRUD 包装器
│   │   │   ├── sandbox.py           #   代码沙盒
│   │   │   ├── sandbox_manager.py   #   沙盒管理器
│   │   │   ├── git_sandbox.py       #   Git 沙盒操作
│   │   │   ├── repo_map.py          #   仓库结构映射
│   │   │   ├── terminal.py          #   有状态终端管理器
│   │   │   ├── speech.py            #   语音转文字
│   │   │   ├── image_processor.py   #   图片处理
│   │   │   ├── document_parser.py   #   文档解析
│   │   │   ├── file_storage.py      #   文件存储
│   │   │   ├── event_stream.py      #   事件流
│   │   │   ├── metrics.py           #   指标收集
│   │   │   ├── logging_config.py    #   结构化日志配置
│   │   │   ├── config_persistence.py#   配置持久化
│   │   │   ├── pipeline.py          #   数据管线
│   │   │   ├── benchmark.py         #   基准测试
│   │   │   ├── router.py            #   路由工具
│   │   │   └── deps.py              #   FastAPI 依赖注入
│   │   ├── routers/                 # API 路由
│   │   │   ├── ws.py                #   WebSocket 端点
│   │   │   ├── agents.py            #   Agent 管理
│   │   │   ├── conversations.py     #   会话与消息 CRUD
│   │   │   ├── settings.py          #   LLM & HIL 配置
│   │   │   ├── quality.py           #   质量门禁设置
│   │   │   ├── prompt.py            #   提示词引擎配置
│   │   │   ├── mcp.py               #   MCP 工具
│   │   │   ├── sandbox.py           #   代码沙盒执行
│   │   │   ├── benchmark.py         #   基准测试执行
│   │   │   ├── speech.py            #   STT 设置与转录
│   │   │   ├── webhook.py           #   Slack & Telegram 回调
│   │   │   ├── workflows.py         #   工作流导入/导出/编译
│   │   │   ├── tools.py             #   工具列表与测试
│   │   │   ├── uploads.py           #   文件上传
│   │   │   ├── cron.py              #   定时任务管理
│   │   │   ├── knowledge.py         #   知识库 CRUD 与语义检索
│   │   │   ├── adapters.py          #   Agent 适配器管理 API
│   │   │   └── harness_handler.py   #   Harness 评测处理
│   │   ├── services/                # 业务服务
│   │   │   ├── agent_orchestrator.py#   Agent 编排器（核心）
│   │   │   ├── agent_registry.py    #   Agent 注册中心
│   │   │   ├── memory_engine.py     #   记忆引擎
│   │   │   ├── daemon_scheduler.py  #   后台守护调度器
│   │   │   ├── detector.py          #   检测器
│   │   │   └── webhook_gateway.py   #   Webhook 网关
│   │   ├── tools/                   # 运行时工具
│   │   │   ├── registry.py          #   AgentTool 基类 & ToolRegistry
│   │   │   ├── browser_tools.py     #   浏览器自动化
│   │   │   ├── code_agent_tools.py  #   代码生成与分析
│   │   │   ├── code_interpreter_tools.py # 代码执行沙盒
│   │   │   ├── file_ops.py          #   文件操作
│   │   │   ├── http_request.py      #   HTTP 请求
│   │   │   ├── web_search.py        #   网页搜索
│   │   │   ├── stateful_terminal_tool.py # 有状态终端
│   │   │   ├── block_editor_tools.py#   块编辑器
│   │   │   ├── judge_tools.py       #   质量评判
│   │   │   └── base.py              #   工具基类
│   │   ├── prompts/                 # 提示词模板
│   │   ├── models/                  # Pydantic 请求/响应模型
│   │   ├── harness/                 # Harness 评测框架
│   │   └── mock/                    # 测试 Mock 数据
│   ├── data/                        # 运行时数据（SQLite、上传文件）
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx                  # 应用根组件
│   │   ├── main.jsx                 # 入口文件
│   │   ├── components/              # UI 组件
│   │   │   ├── Chat/                #   聊天界面
│   │   │   ├── Canvas/              #   代码预览画布
│   │   │   │   ├── TraceView.jsx    #     执行 Trace 甘特图
│   │   │   │   ├── DiffViewer.jsx   #     Monaco 代码 Diff 面板
│   │   │   │   ├── EvalDashboard.jsx#     评估指标仪表盘
│   │   │   │   ├── AgentFlow.jsx    #     Agent 流程 DAG 图
│   │   │   │   ├── AgentDAG.jsx     #     Agent 依赖关系图
│   │   │   │   ├── DeployPanel.jsx  #     部署状态面板
│   │   │   │   ├── WebPreview.jsx   #     HTML 实时预览
│   │   │   │   └── TaskBoard.jsx    #     任务看板
│   │   │   ├── AgentCharacter/      #   Agent 角色展示
│   │   │   │   └── DesktopPet.jsx   #     桌面宠物浮窗组件
│   │   │   ├── VirtualOffice/       #   虚拟办公室视图
│   │   │   ├── Layout/              #   布局组件
│   │   │   ├── Settings/            #   设置面板
│   │   │   ├── ConnectionBanner.jsx #   连接状态横幅
│   │   │   ├── ErrorBoundary.jsx    #   错误边界
│   │   │   └── ThemeToggle.jsx      #   主题切换
│   │   ├── stores/                  # Zustand 状态管理
│   │   │   ├── chatStore.js         #   聊天状态
│   │   │   ├── agentStore.js        #   Agent 状态
│   │   │   ├── canvasStore.js       #   画布状态
│   │   │   ├── tabStore.js          #   标签页状态
│   │   │   ├── themeStore.js        #   主题状态
│   │   │   └── uploadStore.js       #   上传状态
│   │   ├── hooks/                   # React Hooks
│   │   ├── utils/                   # 工具函数
│   │   │   ├── websocket.js         #   WebSocket 客户端
│   │   │   └── useVoiceRecorder.js  #   语音录制 Hook
│   │   ├── types/                   # TypeScript 类型定义
│   │   └── styles/                  # 全局样式
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── docs/                            # 项目文档
├── skills/                          # 技能定义
├── docker-compose.yml               # 开发环境编排
├── docker-compose.prod.yml          # 生产环境编排
├── ruff.toml                        # Python 代码风格配置
└── CLAUDE.md                        # Claude Code 项目指令
```

## 7. 部署架构

### 开发环境

```bash
# 后端
cd backend && pip install -r requirements.txt && python -m app.main

# 前端
cd frontend && npm install && npm run dev
```

### Docker 部署

```bash
docker-compose up -d          # 开发环境
docker-compose -f docker-compose.prod.yml up -d  # 生产环境
```

### 生产架构（可选）

```
                    +-------------+
                    |   Nginx     |
                    |  (反向代理)  |
                    +------+------+
                           |
              +------------+------------+
              |            |            |
        +-----+-----+ +---+---+ +-----+-----+
        | Backend-1 | | B-2   | | Backend-N |
        | (FastAPI) | |       | |           |
        +-----+-----+ +---+---+ +-----+-----+
              |            |            |
              +------------+------------+
                           |
                    +------+------+
                    |    Redis    |
                    | (Pub/Sub)   |
                    +-------------+
```

多实例部署时，Redis Pub/Sub 确保 WebSocket 消息在所有实例间同步。单实例部署时 Redis 为可选组件。
