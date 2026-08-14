"""Tenant-isolated in-memory adapter instances backed by encrypted DB config."""

import logging
from typing import Optional

from app.adapters.base import AgentAdapter
from app.core.tenant_config import get_tenant_json, set_tenant_json

logger = logging.getLogger("adapter_registry")


class AdapterRegistry:
    def __init__(self):
        self._adapters: dict[str, dict[str, AgentAdapter]] = {}

    def _tenant_adapters(self, tenant_id: str) -> dict[str, AgentAdapter]:
        return self._adapters.setdefault(tenant_id, {})

    def register(self, tenant_id: str, agent_id: str, adapter: AgentAdapter) -> None:
        self._tenant_adapters(tenant_id)[agent_id] = adapter
        logger.info("Registered adapter %s for tenant %s", agent_id, tenant_id)

    def unregister(self, tenant_id: str, agent_id: str) -> None:
        self._tenant_adapters(tenant_id).pop(agent_id, None)

    def get(self, tenant_id: str, agent_id: str) -> Optional[AgentAdapter]:
        return self._tenant_adapters(tenant_id).get(agent_id)

    def get_adapters(self, tenant_id: str) -> dict[str, AgentAdapter]:
        return dict(self._tenant_adapters(tenant_id))

    def get_all_status(self, tenant_id: str) -> list[dict]:
        result = []
        for agent_id, adapter in self._tenant_adapters(tenant_id).items():
            status = adapter.get_status()
            status["agent_id"] = agent_id
            result.append(status)
        return result

    def get_status_by_id(self, tenant_id: str, agent_id: str) -> Optional[dict]:
        adapter = self.get(tenant_id, agent_id)
        if not adapter:
            return None
        status = adapter.get_status()
        status["agent_id"] = agent_id
        return status

    def get_saved_configs(self, tenant_id: str) -> dict:
        return get_tenant_json(tenant_id, "adapters", {}, encrypted=True) or {}

    def get_config(self, tenant_id: str, agent_id: str) -> Optional[dict]:
        return self.get_saved_configs(tenant_id).get(agent_id)

    def save_config(self, tenant_id: str, agent_id: str, config: dict) -> None:
        configs = self.get_saved_configs(tenant_id)
        configs[agent_id] = config
        set_tenant_json(tenant_id, "adapters", configs, encrypted=True)

    def remove_config(self, tenant_id: str, agent_id: str) -> None:
        configs = self.get_saved_configs(tenant_id)
        configs.pop(agent_id, None)
        set_tenant_json(tenant_id, "adapters", configs, encrypted=True)


adapter_registry = AdapterRegistry()
