"""Agent Adapter 基类 — 统一接口定义。

所有 Agent 适配器（Claude、Codex、Coze、自部署、自建）都实现此接口。
调用方只需要调 stream_reply()，无需关心底层是哪个 Agent 平台。
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncGenerator, Any, Optional

logger = logging.getLogger("adapter_base")


@dataclass
class AdapterConfig:
    """适配器配置"""
    adapter_type: str           # "claude" | "codex" | "coze" | "self_deployed" | "self_built"
    api_key: str = ""           # API Key
    api_url: str = ""           # API 端点 URL
    model: str = ""             # 模型名称
    timeout: int = 60           # 请求超时（秒）
    max_retries: int = 2        # 最大重试次数
    tool_mode: str = "agent"    # "agent" | "text" | "auto" — 工具注入模式
    extra: dict = field(default_factory=dict)  # 平台特定配置
    display_name: str = ""      # 自定义显示名称（可选）
    display_avatar: str = ""    # 自定义头像 URL/emoji（可选）
    display_desc: str = ""      # 自定义简介（可选）


@dataclass
class AdapterResult:
    """适配器调用结果"""
    success: bool
    text: str = ""
    error: str = ""
    tool_calls: list = field(default_factory=list)  # 工具调用列表
    usage: dict = field(default_factory=dict)       # token 用量


class AgentAdapter(ABC):
    """Agent 适配器基类。

    所有适配器必须实现：
    - stream_reply(): 流式返回 Agent 回复文本
    - validate_config(): 检查配置是否完整可用
    """

    name: str = ""
    adapter_type: str = ""
    description: str = ""

    def __init__(self, config: AdapterConfig):
        self.config = config

    @abstractmethod
    async def stream_reply(
        self,
        message: str,
        history: list[dict] = None,
        system_prompt: str = "",
        tools: list[dict] = None,
        conversation_id: str = None,
    ) -> AsyncGenerator[str, None]:
        """流式返回 Agent 回复。

        Args:
            message: 用户消息
            history: 对话历史 [{role: "user"|"assistant", content: "..."}]
            system_prompt: 系统提示词
            tools: 工具定义列表（各平台格式已统一转换）
            conversation_id: 会话 ID

        Yields:
            回复文本片段（chunk）
        """
        ...

    @abstractmethod
    def validate_config(self) -> tuple[bool, str]:
        """检查配置是否完整可用。

        Returns:
            (is_valid, error_message)
        """
        ...

    def get_status(self) -> dict:
        """返回适配器当前状态（供前端查询）。"""
        valid, err = self.validate_config()
        return {
            "name": self.config.display_name or self.name,
            "adapter_type": self.adapter_type,
            "description": self.config.display_desc or self.description,
            "configured": valid,
            "error": err if not valid else "",
            "model": self.config.model,
            "tool_mode": self.config.tool_mode,
            "extra": self.config.extra,
            "display_name": self.config.display_name,
            "display_avatar": self.config.display_avatar,
            "display_desc": self.config.display_desc,
        }
