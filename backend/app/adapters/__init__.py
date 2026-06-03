"""Agent Adapters — 统一接口层，屏蔽不同 Agent 平台的 API 差异。

架构：
  AgentAdapter (基类) 定义统一接口
  ├── ClaudeAdapter      — Anthropic Messages API + tool_use
  ├── CodexAdapter       — OpenAI Assistants API
  ├── CozeAdapter        — Coze Bot API
  ├── SelfDeployedAdapter — 自部署 Agent 通用 HTTP 适配器 (Dify, LangFlow 等)
  └── SelfBuiltAdapter   — 包装现有 BaseAgent

所有适配器实现同一个接口：stream_reply() → AsyncGenerator[str, None]
前端通过统一的 WebSocket 流式消息接收结果，无需感知底层 Agent 类型。
"""

from app.adapters.base import AgentAdapter, AdapterConfig, AdapterResult
from app.adapters.registry import adapter_registry

__all__ = ["AgentAdapter", "AdapterConfig", "AdapterResult", "adapter_registry"]
