# AgentHub 架构文档

## 核心模块

### LLM 客户端
- 文件：`backend/app/core/llm_client.py`
- 统一封装 OpenAI 兼容格式与 Anthropic 格式调用
- 支持流式输出与超时重试

### 质量门禁（Quality Gate）
- 文件：`backend/app/core/quality_gate.py`
- 规则引擎 + LLM 深度审查双通道
- 自动拦截高危代码，触发修复重试

### Reflexion 自我进化引擎
- 文件：`backend/app/core/reflexion.py`
- 结构化反思：LLM 分析失败原因，提取教训
- 滑动窗口记忆：每个 Agent 最多保留 10 条反思
- 生成代码前自动注入历史教训

### 技能库架构
- 文件：`backend/app/core/skill_library.py`
- 核心类：`SkillLibrary`
- 方法：`add_skill()`, `search()`, `extract_skills_from_output()`
- 存储：ChromaDB 向量数据库（可选）+ 内存字典（必须）

### 输出校验系统
- 文件：`backend/app/core/output_validator.py`
- Pydantic 校验 + 自动重试
- 四层防御：Tool Calling -> Few-shot -> 校验重试 -> 浏览器兜底

### 浏览器 Agent
- 文件：`backend/app/core/browser_manager.py`
- Playwright 单例管理器 + 7 个浏览器工具
- 专用浏览器 Agent，支持错误检测 + 自动路由

### Git 集成
- 文件：`backend/app/core/git_tools.py`
- commit、push、create PR
- 安全措施：路径校验、命令白名单、超时控制

### Code Review Agent
- 规则引擎（8 条确定性审查规则）
- LLM 深度审查
- 自愈管道：高危问题自动触发修复重试

### 适配器系统
- 统一适配器接口，支持接入 Claude Code、Codex、Coze、自部署模型等外部 Agent
- 适配器热插拔，通过配置即可切换底层 Agent 引擎

### 知识库系统
- 基于 ChromaDB 的向量知识库
- 支持文档上传与语义搜索
- 为 Agent 提供上下文增强

### Harness 辩论引擎
- 多 Agent 辩论评估沙盒
- 支持人类在环裁决

### 自动评估器
- 对 Agent 生成的代码进行自动化测试与量化打分
- 输出结构化评估报告

### APM 指标系统
- Agent 执行全链路追踪
- Token 用量、响应延迟、错误率记录与聚合
