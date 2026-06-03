"""Adapter Registry — 适配器注册与管理。

职责：
- 注册/注销适配器实例
- 根据 agent_id 查找对应适配器
- 提供适配器状态查询接口
- 持久化适配器配置到 JSON 文件
"""

import os
import json
import logging
from typing import Optional
from app.adapters.base import AgentAdapter, AdapterConfig

logger = logging.getLogger("adapter_registry")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "adapters.json")


class AdapterRegistry:
    """适配器注册表 — 全局单例。"""

    def __init__(self):
        self._adapters: dict[str, AgentAdapter] = {}   # agent_id → adapter
        self._configs: dict[str, dict] = {}             # agent_id → config dict
        self._load_configs()

    def _load_configs(self):
        """从持久化文件加载适配器配置。"""
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    self._configs = json.load(f)
                logger.info(f"Loaded {len(self._configs)} adapter configs")
        except Exception as e:
            logger.warning(f"Failed to load adapter configs: {e}")

    def _save_configs(self):
        """持久化适配器配置。"""
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._configs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save adapter configs: {e}")

    def register(self, agent_id: str, adapter: AgentAdapter):
        """注册适配器。"""
        self._adapters[agent_id] = adapter
        logger.info(f"Registered adapter: {agent_id} ({adapter.adapter_type})")

    def unregister(self, agent_id: str):
        """注销适配器。"""
        self._adapters.pop(agent_id, None)
        logger.info(f"Unregistered adapter: {agent_id}")

    def get(self, agent_id: str) -> Optional[AgentAdapter]:
        """获取适配器实例。"""
        return self._adapters.get(agent_id)

    def has_adapter(self, agent_id: str) -> bool:
        """检查 agent 是否有适配器。"""
        return agent_id in self._adapters

    def get_all_status(self) -> list[dict]:
        """返回所有适配器状态（包含 agent_id）。"""
        result = []
        for agent_id, adapter in self._adapters.items():
            status = adapter.get_status()
            status["agent_id"] = agent_id
            result.append(status)
        return result

    def get_status_by_id(self, agent_id: str) -> Optional[dict]:
        """返回指定适配器状态（包含 agent_id）。"""
        adapter = self._adapters.get(agent_id)
        if not adapter:
            return None
        status = adapter.get_status()
        status["agent_id"] = agent_id
        return status

    def save_config(self, agent_id: str, config: dict):
        """保存适配器配置（持久化）。"""
        self._configs[agent_id] = config
        self._save_configs()

    def get_config(self, agent_id: str) -> Optional[dict]:
        """获取已保存的适配器配置。"""
        return self._configs.get(agent_id)

    def remove_config(self, agent_id: str):
        """删除适配器配置。"""
        self._configs.pop(agent_id, None)
        self._save_configs()

    def get_saved_configs(self) -> dict:
        """获取所有已保存的配置。"""
        return self._configs.copy()


# 全局单例
adapter_registry = AdapterRegistry()
