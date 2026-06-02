"""FastAPI dependency injection providers.

This module provides FastAPI Depends() wrappers around global singletons
(llm_client, quality_gate, prompt_engine, etc.) to enable:
1. Test isolation — override deps in test fixtures without patching globals
2. Future multi-tenancy — swap implementations per-request
3. Explicit dependency declaration — route signatures document what they need

Usage in route:
    from app.core.deps import get_llm_client, get_quality_gate

    @router.post("/api/...")
    async def my_route(llm=Depends(get_llm_client), qg=Depends(get_quality_gate)):
        ...

Usage in tests:
    app.dependency_overrides[get_llm_client] = lambda: mock_llm
"""
from fastapi import Depends, Request

from app.core.llm_client import llm_client as _llm_client
from app.core.quality_gate import quality_gate as _quality_gate
from app.core.prompt_engine import prompt_engine as _prompt_engine
from app.core.speech import stt_client as _stt_client
from app.core.metrics import metrics as _metrics


def get_llm_client(request: Request = None):
    """Provide the LLM client instance.

    In production, returns the global singleton.
    Override in tests: app.dependency_overrides[get_llm_client] = lambda: mock
    """
    return _llm_client


def get_quality_gate(request: Request = None):
    """Provide the QualityGate instance."""
    return _quality_gate


def get_prompt_engine(request: Request = None):
    """Provide the PromptEngine instance."""
    return _prompt_engine


def get_stt_client(request: Request = None):
    """Provide the STT client instance."""
    return _stt_client


def get_metrics(request: Request = None):
    """Provide the Metrics collector instance."""
    return _metrics


def get_agents(request: Request = None):
    """Provide the AGENTS registry dict."""
    from app.services.agent_registry import agent_registry
    return agent_registry._agents


def get_stop_events(request: Request = None):
    """Provide the per-conversation stop events dict."""
    # This is stored on app.state to avoid module-level mutable state
    if request is not None:
        return request.app.state.stop_events
    # Fallback for non-request contexts
    from app.main import _stop_events
    return _stop_events
