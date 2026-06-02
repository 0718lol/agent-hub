---
name: agent-hub-orchestrator
description: Professional AI skill to deploy, diagnose, test, and dynamically extend the agent-hub high-performance multi-agent framework
---

# 🚀 AgentHub Orchestrator Skill

本技能包旨在教导、约束并辅导任何协同开发 AI 智能体，使其能够在 `agent-hub` 高性能多智能体编排系统上执行零错误环境诊断、回归测试以及架构规范级的功能扩展（例如添加新 Agent、绑定 MCP 工具及编排状态图 DAG）。

---

## 📐 1. 核心架构约束与开发准则

为了保证 `agent-hub` 工业级的高吞吐、强容错表现，所有 AI 助手在开发和维护代码时，必须严格遵守以下契约约束：

### A. 模块化路由规范 (FastAPI Decoupling)
* **严禁膨胀上帝文件**：绝不能再将新路由逻辑直接写入 `app/main.py`！
* **领域驱动设计**：所有领域接口必须划分到 `app/routers/` 的独立子模块中，例如 `app/routers/settings.py`。
* **安全包含**：在 `app/main.py` 中仅通过标准 `app.include_router(new_router.router, prefix="/api")` 集中挂载。

### B. 协程安全注册表与 Agent 标准化 (AgentRegistry Spec)
* **单例访问**：严禁在其他模块中自定义 mutable 全局 `AGENTS` 字典。必须统一导入并调用并发安全单例：
  ```python
  from app.services.agent_registry import agent_registry
  agent = await agent_registry.get_agent("agent_id")
  ```
* **BaseAgent 规范**：所有新智能体必须继承自 `app.agents.base.BaseAgent` 并正确复写 `stream_reply`。
* **Pydantic 契约**：Agent 输入必须配置强类型 `params_model: Optional[Type[BaseModel]]`，防止隐式字典传参引起的运行时类型漂移。

### C. 事务级影子沙盒安全网 (Git-level Autorecovery)
* **隔离路径**：多会话工作空间必须隔离在 `/agenthub_export/{conversation_id}/` 下。
* **事务级回滚**：任何调用 `workspace_write_file` 或 `workspace_run_command` 的写操作与 Shell 执行，必须在 Pre-action 阶段自动触发 Git 提交备份；一旦检测到静态语法编译错误（py_compile）或指令退出码非 0，瞬间调用 `git_rollback` 回滚沙盒以防写烂。

### D. 记忆反思与幂等拦截 (Reflection Idempotency)
* **0 耗防碰锁**：在 `memory_engine.py` 内部增量提炼时，必须使用以 `conversation_id` 为键值的原子布尔锁 `_reflection_locks`，高并发竞态下直接幂等丢弃，节约云端大模型 Token 并杜绝 SQLite WAL 写死锁。

---

## 🔧 2. Skill 工具箱与自动化脚本

本技能包配备了两个高可用的诊断与生成脚本：

1. **`scripts/diagnose_env.py`**：运行全面的物理环境诊断。检查 Ollama 本地端口、SQLite WAL 并发性能、APM 遥测通道存活状况。
2. **`scripts/generate_agent.py`**：自动生成符合 Pydantic 强类型规范与 BaseAgent 接口的新智能体类文件，提供开箱即用模板。

---

## 🧪 3. 全量测试与发布流程

每次修改或扩展核心功能后，必须严格遵循以下质量验证双轨制：

1. **后端回归验证**：
   在 `backend/` 目录下运行 `python -m pytest`，确保全套 69 项并发、沙箱、APM 单元/集成测试 100% 保持绿灯通过。
2. **前端编译校验**：
   在 `frontend/` 目录下运行 `npm run build`，确保 Vite 生产构建 100% 成功，零编译和打包警告。
