"""AgentHub backend test configuration and fixtures."""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def test_env():
    """Set test environment variables for all tests."""
    os.environ["AGENTHUB_DB_PATH"] = ":memory:"
    os.environ["AGENTHUB_ENCRYPT_KEY"] = "test-key-12345"
    yield


@pytest.fixture(autouse=True)
def setup_database():
    """Auto-create all tables before each test, drop after."""
    from sqlmodel import SQLModel

    from app.core._engine import engine
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def mock_llm_client():
    """Mock LLM client that returns predictable responses."""
    client = MagicMock()
    client.is_configured.return_value = False
    client.provider = "openai"
    client.api_key = ""
    client.base_url = ""
    client.model = ""
    client.temperature = None
    client.max_tokens = None

    async def mock_stream(messages, system=""):
        for char in "Mock LLM response for testing.":
            yield char

    client.chat_stream = mock_stream
    return client


@pytest.fixture
def mock_ws_manager():
    """Mock WebSocket connection manager."""
    manager = MagicMock()
    manager.broadcast = AsyncMock()
    manager.connect = AsyncMock()
    manager.disconnect = MagicMock()
    return manager


@pytest.fixture
def sample_conversation_id():
    return "conv_test_001"


@pytest.fixture
def tmp_sandbox(tmp_path):
    """Create a temporary sandbox directory for file operation tests."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    return sandbox
