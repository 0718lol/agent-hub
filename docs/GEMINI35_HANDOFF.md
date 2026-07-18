# AgentHub 后续修复执行单（交给 Gemini 3.5）

> 状态更新（2026-07-18）：Gemini 未产生新增提交或有效修改，以下任务已由 Codex
> 继续执行并完成。最终验证为后端 521 passed、1 skipped，前端 98 passed，
> Ruff、ESLint 和 production build 均通过。当前机器没有 Docker，且沙箱不允许
> 新监听 Playwright 所需端口，因此 Compose 运行验证、浏览器 E2E、真实
> PostgreSQL/Redis E2E、Android SDK 和微信真实凭证验收仍需在 CI 或具备相应依赖
> 的环境执行。本文保留为实现决策和验收记录。

## 1. 任务目标

继续完成 AgentHub 的生产就绪加固。不要重新设计界面，也不要重做已经完成的功能。本轮目标是：
 
1. 保证多人、多 API 副本运行时不会重复生成、重复执行定时任务或串租户数据。
2. 保证 PostgreSQL、Redis、S3/MinIO、远程 Chroma、身份代理的生产路径可配置且可验证。
3. 保证模型 Token 用量按租户记录，依赖和 CI 构建可复现。
4. 完成剩余静态检查、前端测试、构建、Compose 和 E2E 验证。
5. 最终只提交本项目相关改动，不回滚用户已有文件，不把密钥或运行数据提交到 Git。

## 2. 唯一工作目录和 Git 状态

- 工作目录：`/Users/wanganchang/Documents/Codex/2026-07-14/ai-1-agent-web-api-apk/work/agent-hub-publish`
- 当前分支：`agent/platform-production-readiness`
- 当前基线提交：`de8ca73`
- 本轮改动全部已经写入磁盘，但尚未提交。
- 不要改 `/Users/wanganchang/Desktop/agent-hub`，那个目录以前存在用户自己的脏改动。
- 不要执行 `git reset --hard`、`git checkout -- .`、`git clean -fd` 或任何会丢改动的命令。

开始工作前先运行：

```bash
cd /Users/wanganchang/Documents/Codex/2026-07-14/ai-1-agent-web-api-apk/work/agent-hub-publish
git status --short
git diff --check
```

## 3. 已完成的实现

### 3.1 分布式生成状态

文件：

- `backend/app/core/concurrency.py`
- `backend/app/routers/ws.py`
- `backend/app/routers/conversations.py`

已实现：

- Redis Lua 原子获取会话生成租约。
- 每租户并发上限。
- Redis 心跳、停止信号、运行状态和终态。
- `GET /api/conversations/{conversation_id}/generation` 状态接口。
- WebSocket 重连时，如果任务仍在运行，立即恢复前端生成状态。
- 租约过期但状态仍为 `running/cancelling` 时自动标记 `interrupted`，避免永久卡住。
- Redis 不可用时保留单机内存降级。

明确边界：生成执行本身仍在接收 WebSocket 的 API 进程中。进程崩溃后会标记中断并允许重试，但不会从中间 Token 断点续跑。不要把它描述成持久化生成 Worker。

### 3.2 定时任务多实例协调

文件：

- `backend/app/core/redis_lease.py`
- `backend/app/core/crud/cron.py`
- `backend/app/services/daemon_scheduler.py`
- `backend/app/routers/cron.py`

已实现：

- Redis CAS 主节点租约，只有一个 API 副本轮询定时任务。
- 数据库原子 `claim_cron_task`，自动触发与手动触发不能同时抢到同一任务。
- 每个执行任务有独立 Redis execution lease。
- 新主节点只恢复没有活跃 execution lease 的 `running` 任务。
- 重试次数存 Redis，主节点切换后仍保留。
- 子进程启动失败、异常退出和 API 正常关闭时把任务恢复为 `active`。
- 定时任务按会话解析租户，绑定该租户的 LLM、质量门禁、工具开关和自定义 Agent。

需要重点复核：

- `_run_task` 最后的 `await execution_lease.release()` 在 Redis 瞬时断线时可能抛异常。建议用 `try/except` 或 `contextlib.suppress` 包裹，不能因为释放租约失败让已成功任务的子进程以非零状态退出。
- execution lease 当前固定 180 秒，Agent 主体有 90 秒超时。确认前处理和后处理不会超过租约；更稳妥的方案是执行期间续租，而不是单纯继续加大 TTL。
- 真实 `multiprocessing.Process` 崩溃恢复尚未做 Docker/Redis 集成测试，现有测试覆盖数据库抢占和主节点恢复逻辑。

### 3.3 数据库与迁移

文件：

- `backend/app/core/database.py`
- `backend/app/core/crud/__init__.py`
- `backend/app/scripts/migrate.py`
- `backend/app/main.py`
- `docker-compose.yml`

已实现：

- 删除 `database.py` 中重复的 CRUD 实现，只保留初始化、兼容导出和缓存包装器。
- 唯一 CRUD 实现在 `backend/app/core/crud/`。
- 本地默认 `AGENTHUB_AUTO_MIGRATE=true`。
- Compose 增加一次性 `migration` 服务；API 使用 `AGENTHUB_AUTO_MIGRATE=false` 并等待迁移成功。
- CI 真实后端 E2E 增加 PostgreSQL 16，并先运行 `python -m app.scripts.migrate`。

不要重新把 CRUD 复制回 `database.py`。

### 3.4 身份认证和权限

文件：

- `backend/app/core/auth.py`
- `backend/app/core/tenancy.py`
- `backend/app/main.py`
- `backend/app/routers/auth.py`
- `backend/app/routers/ws.py`
- `frontend/src/components/Settings/SecurityTab.jsx`

已实现：

- 保留 shared secret 演示模式。
- 新增受信任身份代理模式，代理必须提供共享签名、外部用户 ID 和角色头。
- 外部用户 ID 哈希后作为内部稳定租户 ID。
- 支持每个机器客户端独立 Token 的 JSON 映射。
- 配置独立 Token 后必须提供 `X-AgentHub-Client-ID`。
- 未配置独立 Token 时，兼容旧版仅传 `X-API-Secret` 的客户端。
- 登录尝试使用 Redis 限流，Redis 不可用时本地限流。
- `viewer` HTTP 只允许 GET/HEAD/OPTIONS；WebSocket 只能发送 read receipt，不能生成、停止或修改。

生产模式目前仍要求 `AGENTHUB_API_SECRET`，即使启用了 proxy。这是额外的内部安全密钥，不要在未评估 webhook、会话签名和兼容性之前删除。

### 3.5 文件和向量存储

文件：

- `backend/app/core/file_storage.py`
- `backend/app/routers/uploads.py`
- `backend/app/core/rag_engine.py`
- `backend/app/core/preflight.py`

已实现：

- 文件后端支持 `local` 和 `s3`，兼容 AWS S3 与 MinIO endpoint。
- 上传先原子写本地缓存，再上传对象存储。
- S3 下载先写临时文件，再原子替换，避免并发读取半文件。
- list/exists/size/delete/healthcheck 统一走存储管理器。
- Chroma 支持 `HttpClient` 远程服务。
- 预检显示对象存储与远程向量库状态，S3 网络检查在线程池执行，不阻塞事件循环。

明确边界：S3 当前覆盖上传、签名文件和构建产物；可变生成工程工作区仍使用共享卷。多主机生产必须提供 RWX 卷或相同远程 Docker 数据卷。

建议复核：`FileStorageManager._s3_client` 是进程级缓存。如果运行时修改 S3 配置，需要显式重置客户端，否则继续使用旧 endpoint/凭证。

### 3.6 模型用量与配额

文件：

- `backend/app/core/llm_client.py`
- `backend/app/core/tenant_settings.py`
- `backend/app/routers/metrics.py`
- `backend/app/services/agent_orchestrator.py`

已实现：

- OpenAI 流式 `usage` 和 Anthropic `message_start/message_delta` 用量解析。
- Provider 未返回 usage 时才使用字符估算。
- 按租户、UTC 日期写 Redis：prompt、completion、total、requests、provider、model。
- 故障切换时记录实际 provider/model，不错误记到主模型。
- `GET /api/metrics/summary` 增加 `daily_llm_usage`。
- `AGENTHUB_LLM_DAILY_TOKEN_QUOTA` 提供每日租户限额。

边界：当前限额是在请求前检查已使用量，并发请求可能小幅越过上限；它不是计费系统。如果要做严格硬配额，应使用 Redis 原子预留和调用后结算。

### 3.7 依赖和 CI

新增：

- `backend/requirements.lock`
- `backend/requirements-test.lock`

已修改：

- `backend/Dockerfile`
- `backend/Dockerfile.builder`
- `.github/workflows/ci.yml`

镜像和 CI 已改用 Python 3.12 完整锁文件。不要删除原始 `requirements.txt`，它仍是人工维护的顶层依赖来源；修改顶层依赖后必须重新生成 lock。

### 3.8 文档

已更新：

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/DELIVERY_ACCEPTANCE.md`
- `docs/IMPLEMENTATION_PLAN.md`

文档已经明确区分模拟 E2E、真实后端 E2E和外部凭证验收，也明确说明生成任务不能断点续跑。

## 4. 已完成的验证

最新完整后端测试结果：

```text
509 passed, 1 skipped, 1 warning in 11.44s
```

跳过的是需要真实 Docker 的沙箱集成测试。警告是 Starlette 对旧 `httpx` TestClient 的弃用提示，不是本轮失败。

针对新增能力的测试文件：

- `backend/tests/test_file_storage.py`
- `backend/tests/test_llm_usage.py`
- `backend/tests/test_scheduler_coordination.py`
- 扩展的 `test_auth.py`、`test_concurrency.py`、`test_api.py`、`test_integration_websocket.py`

注意：完整测试是在最后补 `main.py` 的 `verify_session_token` 导入之前跑完的。这个补丁只增加缺失导入，但仍应再跑一次相关鉴权测试或全量测试。

## 5. 当前未完成项（必须按顺序执行）

### 第一步：修 Ruff

上一次 Ruff 结果为 8 个 `I001` 导入排序问题。`F821 verify_session_token` 已经手动修复。

待排序文件：

- `backend/app/core/concurrency.py`
- `backend/app/core/rag_engine.py`
- `backend/app/core/redis_lease.py`
- `backend/app/core/tenancy.py`
- `backend/app/services/daemon_scheduler.py` 两处局部导入
- `backend/tests/test_auth.py`
- `backend/tests/test_concurrency.py`

执行：

```bash
cd backend
env UV_CACHE_DIR=/tmp/agenthub-uv-cache \
  /Users/wanganchang/.local/bin/uvx ruff check app tests --fix
env UV_CACHE_DIR=/tmp/agenthub-uv-cache \
  /Users/wanganchang/.local/bin/uvx ruff check app tests
```

自动修复后必须查看 `git diff`，确认 Ruff 只移动导入，没有改业务逻辑。

### 第二步：复跑后端

```bash
cd backend
env UV_CACHE_DIR=/tmp/agenthub-uv-cache \
  /Users/wanganchang/.local/bin/uv run --offline \
  --python /Users/wanganchang/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  --with-requirements requirements-test.lock \
  python -m pytest tests/ -q
```

验收：509 passed、1 skipped；不能出现新的失败。

另外运行语法和差异检查：

```bash
env PYTHONPYCACHEPREFIX=/tmp/agenthub-pycache python3 -m compileall -q backend/app
git diff --check
```

### 第三步：前端单测、Lint 和构建

`frontend/node_modules` 当前已经存在。执行：

```bash
cd frontend
npm test -- --run
npm run lint
npm run build
```

如果 npm 命令找不到 Node，使用：

```bash
export PATH=/Users/wanganchang/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH
```

不要通过删除测试或禁用 ESLint 规则来“修复”失败。

### 第四步：Compose 配置验证

```bash
cd ..
docker compose config --quiet
docker compose -f docker-compose.yml -f docker-compose.local-docker.yml config --quiet
```

重点确认：

- `backend` 等待 `migration` 成功。
- `migration` 等待 PostgreSQL 健康。
- backend 使用 `AGENTHUB_AUTO_MIGRATE=false`。
- Redis、PostgreSQL、S3、Chroma 和身份代理环境变量格式正确。
- production 不应默认挂载宿主 Docker Socket。

### 第五步：Playwright

先跑确定性 UI E2E：

```bash
cd frontend
npm run test:e2e
```

再验证真实后端场景。推荐用 Docker 启动 PostgreSQL 和 Redis，或者直接执行 GitHub Actions 对应 job。

真实场景必须覆盖：

1. 独立 migration 命令成功。
2. API 在 `AGENTHUB_AUTO_MIGRATE=false` 时启动。
3. 浏览器打开真实 React 页面。
4. 通过真实 WebSocket 给 PM 发送“谢谢你的帮助”，出现固定 PM 回复。
5. 真实上传并下载文本文件。
6. 发布 Worker 不在线时返回明确 503；在线时任务进入队列、可查询并取消。

不要声称此 E2E 调用了真实收费 LLM、Android SDK 或微信平台，它没有。

### 第六步：最终代码复核

至少检查这些风险：

1. `daemon_scheduler._run_task` 释放 execution lease 的 Redis 断线处理。
2. scheduler 子进程异常退出后是否会错误覆盖已经成功写入的下一次运行时间。
3. proxy viewer 是否能通过 WebSocket 发除 `read` 之外的消息。
4. 配置 `AGENTHUB_API_CLIENT_TOKENS_JSON` 后，旧共享密钥是否被正确拒绝。
5. S3 下载并发时是否始终通过原子替换。
6. generation lease 过期后是否返回 `interrupted` 而不是永久 `running`。
7. 所有租户 ID 是否在进入数据库、Redis key、文件名和 Chroma collection 前经过稳定作用域处理。

### 第七步：提交（不要自动推送）

先查看：

```bash
git status --short
git diff --check
git diff -- . ':!backend/requirements.lock' ':!backend/requirements-test.lock'
git diff --numstat
```

确认 `.env`、数据库、上传文件、私钥、keystore、构建产物和日志没有被加入。

建议提交信息：

```text
fix: harden distributed coordination and production storage
```

只有用户明确要求推送时才执行 `git push`。

## 6. 最终验收标准

必须同时满足：

- Ruff 0 error。
- 后端 509 passed、1 skipped，或测试数量增加后全部非 Docker 测试通过。
- 前端单测通过。
- ESLint 通过。
- 前端 production build 通过。
- `docker compose config` 通过。
- 模拟 E2E 通过。
- 真实后端 E2E 在 PostgreSQL + Redis 上通过，或明确记录本机缺少 Docker 导致未执行，不能伪报通过。
- `git diff --check` 通过。
- 文档与实际边界一致。
- 最终回复列出已验证命令、未验证项和仍存在的生产限制。

## 7. 禁止事项

- 不要重置、清理或覆盖整个工作树。
- 不要修改桌面上的另一个 agent-hub 目录。
- 不要把 shared secret、S3 密钥、微信私钥、Android keystore 或真实 Token 写入仓库。
- 不要把本地内存降级描述成多实例安全方案。
- 不要把“生成 ZIP/上传包”描述成已经公网发布或微信审核上线。
- 不要把 Mock 回复描述成真实 AI 代码生成。
- 不要为了通过测试而跳过、删除或弱化测试。
