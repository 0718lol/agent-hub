"""AgentHub backend test configuration and fixtures."""
import os
import sys
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


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
