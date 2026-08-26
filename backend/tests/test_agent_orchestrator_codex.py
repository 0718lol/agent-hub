from unittest.mock import MagicMock, patch

from app.agents.pm import PMAgent
from app.services.agent_orchestrator import (
    _html_fallback_for_visual_task,
    _image_capability_error,
    _terminal_model_error,
    get_agents,
)


def test_terminal_visual_error_is_detected_and_has_html_fallback():
    error = '[LLM 终端错误 (不可重试): This model does not support image]'
    fallback = _html_fallback_for_visual_task('张雪峰主题巧乐滋海报')

    assert _terminal_model_error(error) is True
    assert _image_capability_error(error) is True
    assert '<!doctype html>' in fallback
    assert '张雪峰主题巧乐滋海报' in fallback


def test_regular_output_is_not_treated_as_terminal_error():
    assert _terminal_model_error('已生成 HTML 预览。') is False


def test_pm_is_routed_through_configured_codex_adapter():
    codex = MagicMock()
    codex.name = "Codex"
    codex.description = "Codex 本机连接器"
    codex.adapter_type = "codex"

    with patch("app.services.agent_orchestrator.agent_registry.get_agent_dict", return_value={"agent_pm": PMAgent()}), \
         patch("app.adapters.registry.adapter_registry.get_adapters", return_value={"codex": codex}), \
         patch("app.adapters.registry.adapter_registry.get", return_value=codex), \
         patch("app.adapters.registry.adapter_registry.get_config", return_value={}), \
         patch("app.routers.adapters.load_saved_adapters"):
        agents = get_agents("tenant-codex")

    assert agents["agent_pm"].agent_id == "agent_pm"
    assert agents["agent_pm"].adapter is codex
    assert agents["agent_pm"].system_prompt == PMAgent.system_prompt


def test_pm_keeps_builtin_agent_without_codex():
    pm = PMAgent()
    with patch("app.services.agent_orchestrator.agent_registry.get_agent_dict", return_value={"agent_pm": pm}), \
         patch("app.adapters.registry.adapter_registry.get_adapters", return_value={}), \
         patch("app.adapters.registry.adapter_registry.get", return_value=None), \
         patch("app.routers.adapters.load_saved_adapters"):
        agents = get_agents("tenant-without-codex")

    assert agents["agent_pm"] is pm
