# AgentHub 交付与验收清单

## 1. 当前交付范围

AgentHub 已形成从自然语言需求到工程文件、运行预览、多轮修改和发布产物的演示闭环。

| 能力 | 当前实现 | 验收结果 |
| --- | --- | --- |
| 自然语言生成 | WebSocket 多 Agent 编排，接入租户自己的 LLM 配置 | 配置有效模型 API 后可用 |
| 多文件工程 | 按代码块 `path=` 写入独立工作区，提供文件树和 Git 快照 | 可用 |
| 多轮修改 | 同一会话持续更新工程，并可恢复历史快照 | 可用 |
| Web 预览 | 静态多文件预览；Vite 项目可启动受限 Docker 开发服务器 | 可用，Vite 模式需要 Docker |
| API 预览 | 构建受限 API 容器，提供 Swagger、OpenAPI 和请求调试器 | 可用，需要 Redis 和构建 Worker |
| APK | Gradle 构建，支持演示密钥和用户 keystore 签名 | 可用，需要 Android 构建节点 |
| 微信小程序 | 工程打包、`miniprogram-ci.preview` 二维码、真实代码上传 | 可用，需要 AppID 和上传私钥 |
| 分享 | Web 使用 Netlify；API 使用 `/published/{id}/`；产物使用受保护下载链接 | 按目标类型可用 |

## 2. 演示验收流程

1. 打开设置，配置当前用户的 LLM Provider、Base URL、模型和 API Key，执行连接测试。
2. 输入“生成一个带新增、筛选和本地存储的团队待办 Web 工具”。
3. 在“代码”页确认出现 `index.html`、脚本和样式文件，并确认生成了 Git 快照。
4. 在“预览”页操作生成的软件。Vite 项目点击播放图标启动隔离开发服务器。
5. 继续对话：“增加优先级筛选，并把添加按钮改成新增任务”，确认文件与预览更新。
6. 从历史快照恢复上一版，再恢复到最新版，确认工程内容同步变化。
7. 在“部署”页选择目标，观察排队、生成、依赖安装、构建、签名、上传、完成状态。
8. API 发布完成后回到“预览”，用请求调试器访问 `health` 或业务接口。
9. 下载失败日志，确认日志包含时间、阶段、级别和错误原因。

## 3. 凭证与基础设施

| 目标 | 必需条件 | 缺少时的行为 |
| --- | --- | --- |
| LLM 生成 | 模型 API Key、Base URL、模型名 | 不能完成真实自然语言生成 |
| 静态 Web 预览 | 生成项目含 `index.html` | 直接预览 |
| Vite Web 预览 | Docker、runtime sandbox 镜像 | 保留静态或流式 HTML 预览，并显示能力状态 |
| Web 公网发布 | Netlify Token、Site ID | 只生成 ZIP |
| API 发布 | Redis、deployment-worker、隔离 Docker 节点、Dockerfile | 队列拒绝并返回明确原因 |
| APK | Gradle Wrapper、Android SDK 构建 Worker | 构建失败并可下载日志 |
| 小程序二维码/上传 | 微信 AppID、代码上传私钥、允许的上传 IP | 只生成开发者工具工程包 |

## 4. 接入模型 API 后仍不自动完成的事项

- 模型 API 只负责理解和生成代码，不会替代 Docker、Android SDK、微信凭证或公网托管服务。
- APK 无法在普通浏览器中模拟真机；当前交付物是经过签名验证的安装包。
- 小程序二维码是体验版入口，上传版本仍需在微信公众平台提交审核和发布。
- Web 公网链接依赖 Netlify 配置；API 公网可达性依赖反向代理、域名和 TLS。
- 任意模型都可能生成不完整的第三方工程。质量门禁、沙箱和构建流水线会发现问题，但不能保证一次生成即达到生产质量。
- 自定义 Agent、知识库、上传、工程和发布记录已按租户隔离；身份代理本身需由部署方提供 OIDC/OAuth2 登录与账号生命周期管理。
- 生成状态与停止信号可跨实例恢复，但模型执行仍在接收任务的 API 进程；进程崩溃后任务标记为 `interrupted`，不会从中间 Token 自动续跑。
- S3/MinIO 已覆盖上传和构建产物；可变工程工作区在多主机部署时仍要求共享 RWX 卷或同一远程 Docker 数据卷。

## 5. 上线预检

```bash
cd backend

# 本地核心功能
python -m app.scripts.preflight --profile core

# Web/API/APK/小程序构建环境
python -m app.scripts.preflight --profile deployment

# 公网生产配置，任一必需项失败时退出码为 1
python -m app.scripts.preflight --profile production
```

运行中的服务也可访问 `GET /api/system/preflight?profile=deployment`。生产验收必须满足：

- `ready=true`，数据库连接和 Alembic Schema 均通过。
- Redis 与 deployment-worker 心跳通过。
- `AGENTHUB_API_SECRET`、`AGENTHUB_ENCRYPT_KEY`、`AGENTHUB_PUBLIC_BASE_URL` 已配置。
- 公网多用户部署启用身份代理与只读角色策略；多主机部署启用 S3/MinIO 和远程 Chroma。
- Alembic 由独立 `migration` 服务完成，API 设置 `AGENTHUB_AUTO_MIGRATE=false`。
- 生成项目目录和构建产物目录可写。
- Nginx 已代理 `/api/`、`/ws/`、`/uploads/` 和 `/published/`。

## 6. 自动化验收

```bash
cd backend
python -m pytest -q
ruff check app tests

cd ../frontend
npm test
npm run lint
npm run build
npm run test:e2e
```

模拟端到端场景覆盖生成、文件树、流式预览、多轮修改、部署进度、API 调试、失败日志、取消和回滚。
真实后端场景使用 PostgreSQL、Redis、FastAPI 和 WebSocket 覆盖迁移、会话、上传及发布队列；外部 LLM、Android SDK 和微信平台由凭证环境单独验收。
