"""Tests for config persistence module."""
import os
import json
import pytest
import tempfile
from app.core.config_persistence import get_hil_settings, save_hil_settings


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_hil_default_settings():
    """Test that HIL settings returns defaults when no config file exists."""
    settings = get_hil_settings()
    assert "human_input_mode" in settings
    assert "cooldown_steps" in settings
    assert settings["human_input_mode"] == "NEVER"
    assert settings["cooldown_steps"] == 2


def test_hil_save_and_load(temp_config_dir, monkeypatch):
    """Test that HIL settings can be saved and loaded."""
    import app.core.config_persistence as cp
    config_path = os.path.join(temp_config_dir, "hil_config.json")
    monkeypatch.setattr(cp, "HIL_CONFIG_PATH", config_path)

    custom_settings = {"human_input_mode": "ALWAYS", "cooldown_steps": 5}
    save_hil_settings(custom_settings)

    loaded = get_hil_settings()
    assert loaded["human_input_mode"] == "ALWAYS"
    assert loaded["cooldown_steps"] == 5


def test_llm_config_save_and_load(temp_config_dir, monkeypatch):
    """Test that LLM config can be saved and loaded with key encryption."""
    import app.core.config_persistence as cp
    config_path = os.path.join(temp_config_dir, "llm_config.json")
    monkeypatch.setattr(cp, "LLM_CONFIG_PATH", config_path)

    from unittest.mock import MagicMock
    from app.core.config import Settings

    mock_client = MagicMock()
    mock_client.api_key = "sk-test-key-12345"
    mock_client.provider = "openai"
    mock_client.base_url = "https://api.example.com/v1"
    mock_client.model = "gpt-4"
    mock_client.temperature = 0.7
    mock_client.max_tokens = 4096

    settings = Settings()

    # Save config
    save_llm_config(mock_client, settings)

    # Verify file was created and key is not plaintext
    assert os.path.exists(config_path)
    with open(config_path, "r") as f:
        saved = json.load(f)
    assert saved["api_key"] != "sk-test-key-12345"
    assert saved["api_key"].startswith("fnt::") or saved["api_key"] == ""

    # Load config back
    mock_client2 = MagicMock()
    mock_client2.api_key = ""
    load_llm_config(mock_client2, settings)
    # The configure method should have been called
    assert mock_client2.configure.called
