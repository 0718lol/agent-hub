import os
import json
import socket
from dataclasses import dataclass

ROUTER_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "router_config.json")

@dataclass
class ModelRoute:
    provider: str
    base_url: str
    model: str
    api_key: str = ""

def check_port_alive(host: str, port: int, timeout: float = 0.2) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

class SmartRouter:
    def __init__(self):
        self.auto_routing: bool = True
        self.manual_routes: dict = {}  # agent_id -> dict(provider, base_url, model, api_key)
        self._load_config()

    def _load_config(self):
        try:
            if os.path.exists(ROUTER_CONFIG_PATH):
                with open(ROUTER_CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.auto_routing = data.get("auto_routing", True)
                    self.manual_routes = data.get("manual_routes", {})
        except Exception:
            pass

    def save_config(self):
        os.makedirs(os.path.dirname(ROUTER_CONFIG_PATH), exist_ok=True)
        try:
            with open(ROUTER_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "auto_routing": self.auto_routing,
                    "manual_routes": self.manual_routes
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_route_for_agent(self, agent_id: str) -> ModelRoute:
        from app.core.llm_client import llm_client

        # 1. If manual routing is configured and active
        if not self.auto_routing and agent_id in self.manual_routes:
            r = self.manual_routes[agent_id]
            if r.get("provider"):
                return ModelRoute(
                    provider=r["provider"],
                    base_url=r.get("base_url", ""),
                    model=r.get("model", ""),
                    api_key=r.get("api_key", "")
                )

        # 2. Check globally configured LLM settings as base/fallback
        global_route = ModelRoute(
            provider=llm_client.provider,
            base_url=llm_client.base_url,
            model=llm_client.model,
            api_key=llm_client.api_key
        )

        # 3. Dynamic Auto-Routing based on Agent Tier & Self-healing check
        if self.auto_routing:
            # L1 Tier: Planning & Audit (PM, builder) -> Clouds
            if agent_id in ("agent_pm", "agent_builder", "quality_gate"):
                return global_route

            # L2 Tier: High-load Coding (frontend, backend, tester, custom agents) -> Local or high-efficiency
            if agent_id in ("agent_frontend", "agent_backend", "agent_tester") or agent_id.startswith("agent_custom_"):
                # Probe local Ollama service
                if check_port_alive("127.0.0.1", 11434):
                    # Fetch first model from Ollama if possible
                    local_model = "deepseek-r1:7b"
                    try:
                        import httpx
                        r = httpx.get("http://127.0.0.1:11434/api/tags", timeout=0.2)
                        if r.status_code == 200:
                            models = r.json().get("models", [])
                            if models:
                                local_model = models[0]["name"]
                    except Exception:
                        pass
                    return ModelRoute(
                        provider="ollama",
                        base_url="http://127.0.0.1:11434/v1",
                        model=local_model,
                        api_key="local"
                    )

                # Probe local LM Studio service
                if check_port_alive("127.0.0.1", 1234):
                    local_model = "local-model"
                    try:
                        import httpx
                        r = httpx.get("http://127.0.0.1:1234/v1/models", timeout=0.2)
                        if r.status_code == 200:
                            models = r.json().get("data", [])
                            if models:
                                local_model = models[0]["id"]
                    except Exception:
                        pass
                    return ModelRoute(
                        provider="openai",
                        base_url="http://127.0.0.1:1234/v1",
                        model=local_model,
                        api_key="local"
                    )

            # L3 Tier: Design & Creative -> local if available, else cloud
            if agent_id in ("agent_designer", "agent_devops"):
                if check_port_alive("127.0.0.1", 11434):
                    return ModelRoute(
                        provider="ollama",
                        base_url="http://127.0.0.1:11434/v1",
                        model="qwen2.5:7b" if not llm_client.provider == "ollama" else llm_client.model,
                        api_key="local"
                    )

        # Fallback to globally configured model (Self-healing fallback)
        return global_route

# Global Singleton
smart_router = SmartRouter()
