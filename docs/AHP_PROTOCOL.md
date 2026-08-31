# AgentHub Agent 协作协议（AHP）

> AgentHub Protocol for Multi-Agent Collaboration

---

## 一、协议概述

### 1.1 定位

AHP（AgentHub Protocol）是 AgentHub 内部的多 Agent 通信协议，定义了 Agent 之间的消息格式、任务分配、错误处理和安全规范。

### 1.2 与其他协议的关系

| 协议 | 用途 | 关系 |
|------|------|------|
| **MCP** (Anthropic) | Agent ↔ 工具 | AHP 调用 MCP 工具 |
| **A2A** (Google) | Agent ↔ Agent | AHP 是 A2A 的轻量实现 |
| **AHP** (AgentHub) | Agent ↔ Agent ↔ 用户 | AHP 是核心通信协议 |

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| **简单** | 基于文本标签，易于解析和调试 |
| **可扩展** | 支持自定义标签和消息类型 |
| **向后兼容** | 新增标签不影响旧版本 |
| **安全** | 内置权限控制和沙盒隔离 |

---

## 二、消息格式

### 2.1 基础消息结构

```json
{
  "type": "message",
  "conversation_id": "conv_001",
  "sender": "agent_frontend",
  "content": {"text": "消息内容"},
  "stream": false,
  "timestamp": "2026-06-08T12:00:00Z"
}
```

### 2.2 消息类型

| 类型 | 方向 | 说明 |
|------|------|------|
| `message` | 双向 | 普通文本消息 |
| `typing` | 服务器→客户端 | 输入状态 |
| `thinking` | 服务器→客户端 | Agent 思考过程 |
| `code` | 服务器→客户端 | 代码块 |
| `preview` | 服务器→客户端 | HTML 预览 |
| `generating` | 服务器→客户端 | 生成状态 |
| `task_status` | 服务器→客户端 | 任务状态 |
| `deploy_status` | 服务器→客户端 | 部署状态 |
| `candidates_report` | 服务器→客户端 | Best-of-N 候选报告 |
| `quality_report` | 服务器→客户端 | 质量评估报告 |
| `agent_created` | 服务器→客户端 | 新 Agent 创建通知 |
| `agent_deleted` | 服务器→客户端 | Agent 删除通知 |
| `trace_update` | 服务器→客户端 | 追踪数据更新（SSE） |
| `read` | 客户端→服务器 | 已读回执 |
| `stop` | 客户端→服务器 | 停止生成 |

---

## 三、Agent 注册协议

### 3.1 Agent ID 命名规范

| 类型 | 格式 | 示例 |
|------|------|------|
| 内置 Agent | `agent_{role}` | `agent_pm`, `agent_frontend` |
| 自定义 Agent | `agent_custom_{hash}` | `agent_custom_a1b2c3d4` |
| 导入 Agent | `agent_imported_{hash}` | `agent_imported_x8y9z0` |
| 外部 Agent | `agent_{platform}_{name}` | `agent_claude_code` |

### 3.2 Agent 能力声明

```python
class AgentCapability:
    agent_id: str              # 唯一标识
    name: str                  # 显示名称
    avatar: str                # 头像 emoji
    role: str                  # 角色描述
    style: str                 # 风格描述
    system_prompt: str         # 系统提示词
    tools: list[str]           # 可用工具列表
    constraints: dict          # 约束条件
```

### 3.3 Agent 发现

```python
# 获取所有可用 Agent
agents = agent_registry.get_agent_dict()

# 获取特定 Agent
agent = await agent_registry.get_agent("agent_frontend")
```

---

## 四、任务分配协议

### 4.1 标签格式

| 标签 | 格式 | 说明 |
|------|------|------|
| 分配任务 | `[assign:agent_xxx]` | PM 分配任务给 Agent |
| 用户提问 | `[ask_user:问题\|选项1\|选项2]`` | Agent 向用户提问 |
| 创建 Agent | `[create_agent:{json}]` | 动态创建自定义 Agent |
| 删除 Agent | `[delete_agent:agent_id]` | 删除自定义 Agent |
| 工具调用 | `[tool_call:name]{params}[/tool_call]` | 调用工具 |
| 思考过程 | `[thinking]...[/thinking]` | Agent 思考过程 |

### 4.2 任务分配流程

```
用户输入 → PM Agent 分析
    ↓
PM 输出：[assign:agent_frontend] [assign:agent_backend]
    ↓
编排器解析标签，启动对应 Agent
    ↓
Agent 并行执行（asyncio.gather + return_exceptions=True）
    ↓
结果汇总 → 输出给用户
```

### 4.3 任务状态流转

```
pending → doing → done
                → failed → retry (max 3)
                         → report to user
```

---

## 五、错误处理协议

### 5.1 错误类型分类

| 类型 | 可重试 | 示例 |
|------|--------|------|
| LLM 调用失败 | ✅ | API 超时、限流 |
| 输出格式错误 | ✅ | 缺少代码块、问句 |
| 工具调用失败 | ⚠️ | 参数错误、权限不足 |
| 逻辑错误 | ❌ | 断言失败、无限循环 |
| 资源耗尽 | ❌ | 内存溢出、磁盘满 |

### 5.2 重试策略

```python
# 指数退避重试
for attempt in range(max_retries):
    try:
        result = await agent.execute(task)
        if result.success:
            return result
    except RetryableError:
        await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s
    except NonRetryableError:
        break
```

### 5.3 降级策略

| 场景 | 降级方案 |
|------|---------|
| LLM 调用失败 | 切换到备用模型 |
| Agent 崩溃 | 用兜底回复 |
| 浏览器不可用 | 用 HTTP 请求替代 |
| 知识库不可用 | 跳过 RAG，直接生成 |

---

## 六、安全规范

### 6.1 Agent 权限边界

| Agent | 允许的工具 | 禁止的操作 |
|-------|----------|----------|
| PM | 无工具 | 不能执行代码 |
| Frontend | 文件操作、浏览器 | 不能访问数据库 |
| Backend | 文件操作、HTTP 请求 | 不能访问前端代码 |
| Tester | 代码执行、文件操作 | 不能修改生产代码 |
| DevOps | Git、Docker、终端 | 不能修改业务代码 |
| Browser | 浏览器操作 | 不能执行代码 |
| Debugger | 代码执行、文件操作 | 不能修改安全配置 |

### 6.2 工具调用白名单

```python
ALLOWED_TOOLS = {
    "agent_frontend": ["browser_open_url", "browser_get_content", "browser_screenshot"],
    "agent_backend": ["browser_open_url", "browser_get_content", "git_commit", "git_push"],
    "agent_tester": ["sandbox_run", "browser_open_url"],
    "agent_devops": ["git_commit", "git_push", "create_pr", "sandbox_run"],
    "agent_debugger": ["sandbox_run", "browser_open_url"],
}
```

---

## 七、扩展规范

### 7.1 自定义 Agent 注册

```python
# 通过 API 注册
POST /api/agents/custom
{
    "name": "我的 Agent",
    "avatar": "🤖",
    "role": "自定义角色",
    "system_prompt": "你是...",
    "tools": ["browser_open_url"]
}
```

### 7.2 外部 Agent 适配器接入

```python
# 通过适配器系统接入
POST /api/adapters
{
    "name": "Claude Code",
    "adapter_type": "claude",
    "config": {"api_key": "...", "model": "claude-sonnet-4-20250514"}
}
```

### 7.3 协议版本管理

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-06-08 | 初始版本 |
