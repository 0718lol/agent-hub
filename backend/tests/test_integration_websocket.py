"""Integration tests for the WebSocket endpoint.

Tests the full lifecycle: connection, authentication, message send/receive,
stop signal, invalid JSON handling, short-message filtering, and disconnect cleanup.

All external dependencies (LLM, Redis, database) are mocked.
"""
import asyncio
import json
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx_ws import WebSocketDisconnect, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ws_app():
    """Build a minimal FastAPI app with the WS router and all heavy deps mocked.

    Patches:
    - redis_manager.check_connection  -> False  (skip Redis, use local broadcast)
    - async_save_message              -> no-op
    - async_get_pending_hil_checkpoint -> None   (no HIL recovery)
    - run_user_message_flow           -> no-op
    - run_target_agent_flow           -> no-op
    - get_agents                      -> empty dict
    - handle_verdict                  -> no-op
    """
    from fastapi import FastAPI
    from app.routers.ws import router

    app = FastAPI()
    app.include_router(router)

    patches = [
        patch(
            "app.core.redis.redis_manager.check_connection",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch("app.routers.ws.async_save_message", new_callable=AsyncMock),
        patch(
            "app.routers.ws.async_get_pending_hil_checkpoint",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.routers.ws.run_user_message_flow", new_callable=AsyncMock),
        patch("app.routers.ws.run_target_agent_flow", new_callable=AsyncMock),
        patch("app.routers.ws.get_agents", return_value={}),
        patch("app.routers.ws.handle_verdict", new_callable=AsyncMock),
    ]

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield app


@pytest.fixture(autouse=True)
def _set_api_secret():
    """Set a known api_secret for every test so auth logic is deterministic."""
    with patch("app.routers.ws.settings") as mock_settings:
        mock_settings.api_secret = "test-secret"
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _receive_json(ws, timeout=2.0):
    """Receive one text frame from the WebSocket and parse it as JSON.

    Returns the parsed dict, or raises TimeoutError if nothing arrives.
    """
    data = await asyncio.wait_for(ws.receive_text(), timeout=timeout)
    return json.loads(data)


def _find_ws_disconnect(exc_group):
    """Recursively search an ExceptionGroup for the first WebSocketDisconnect."""
    for exc in exc_group.exceptions:
        if isinstance(exc, WebSocketDisconnect):
            return exc
        if isinstance(exc, BaseExceptionGroup):
            found = _find_ws_disconnect(exc)
            if found:
                return found
    return None


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_with_valid_query_token(ws_app):
    """A valid token passed as a query parameter should allow the connection."""
    async with ASGIWebSocketTransport(app=ws_app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with aconnect_ws(
                "ws://testserver/ws/conv_auth_ok?token=test-secret", client
            ) as ws:
                await ws.send_text(json.dumps({"type": "read"}))
                resp = await _receive_json(ws)
                assert resp["type"] == "read"
                assert resp["conversation_id"] == "conv_auth_ok"


@pytest.mark.asyncio
async def test_connect_with_valid_header_token(ws_app):
    """A valid token passed via the x-api-secret header should allow the connection."""
    async with ASGIWebSocketTransport(app=ws_app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with aconnect_ws(
                "ws://testserver/ws/conv_auth_header?token=test-secret",
                client,
                headers={"x-api-secret": "test-secret"},
            ) as ws:
                await ws.send_text(json.dumps({"type": "read"}))
                resp = await _receive_json(ws)
                assert resp["type"] == "read"


@pytest.mark.asyncio
async def test_connect_without_token_rejected(ws_app):
    """When api_secret is set, omitting the token should close the socket with 4001.

    The server accepts then immediately closes with code 4001.  httpx_ws wraps
    the resulting WebSocketDisconnect inside an ExceptionGroup via anyio.
    """
    async with ASGIWebSocketTransport(app=ws_app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            with pytest.raises(BaseExceptionGroup) as exc_info:
                async with aconnect_ws(
                    "ws://testserver/ws/conv_no_token", client
                ) as ws:
                    await ws.send_text(json.dumps({"type": "read"}))
                    await ws.receive_text()
            ws_err = _find_ws_disconnect(exc_info.value)
            assert ws_err is not None, "Expected WebSocketDisconnect in exception group"
            assert ws_err.code == 4001


@pytest.mark.asyncio
async def test_connect_with_wrong_token_rejected(ws_app):
    """An incorrect token should close the socket with 4001."""
    async with ASGIWebSocketTransport(app=ws_app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            with pytest.raises(BaseExceptionGroup) as exc_info:
                async with aconnect_ws(
                    "ws://testserver/ws/conv_bad_token?token=wrong-secret",
                    client,
                ) as ws:
                    await ws.send_text(json.dumps({"type": "read"}))
                    await ws.receive_text()
            ws_err = _find_ws_disconnect(exc_info.value)
            assert ws_err is not None, "Expected WebSocketDisconnect in exception group"
            assert ws_err.code == 4001


@pytest.mark.asyncio
async def test_connect_localhost_no_secret_allowed(ws_app):
    """When api_secret is empty, localhost clients should be allowed through."""
    with patch("app.routers.ws.settings") as mock_settings:
        mock_settings.api_secret = ""

        async with ASGIWebSocketTransport(app=ws_app) as transport:
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                async with aconnect_ws(
                    "ws://testserver/ws/conv_localhost", client
                ) as ws:
                    await ws.send_text(json.dumps({"type": "read"}))
                    resp = await _receive_json(ws)
                    assert resp["type"] == "read"


# ---------------------------------------------------------------------------
# Message flow tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_broadcast(ws_app):
    """Sending a normal user message should produce a broadcast with type=message."""
    async with ASGIWebSocketTransport(app=ws_app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with aconnect_ws(
                "ws://testserver/ws/conv_msg_001?token=test-secret", client
            ) as ws:
                payload = {
                    "type": "message",
                    "sender": "user",
                    "content": {"text": "Hello, agent!"},
                }
                await ws.send_text(json.dumps(payload))
                resp = await _receive_json(ws)

                assert resp["type"] == "message"
                assert resp["conversation_id"] == "conv_msg_001"
                assert resp["sender"] == "user"
                assert resp["content"]["text"] == "Hello, agent!"
                assert resp["stream"] is False


@pytest.mark.asyncio
async def test_stop_message_sets_event(ws_app):
    """Sending a 'stop' message should set the corresponding _stop_events entry."""
    from app.services.agent_orchestrator import _stop_events

    conv_id = "conv_stop_001"
    _stop_events[conv_id] = asyncio.Event()

    try:
        async with ASGIWebSocketTransport(app=ws_app) as transport:
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                async with aconnect_ws(
                    f"ws://testserver/ws/{conv_id}?token=test-secret", client
                ) as ws:
                    await ws.send_text(json.dumps({"type": "stop"}))
                    await asyncio.sleep(0.05)
                    assert _stop_events[conv_id].is_set()
    finally:
        _stop_events.pop(conv_id, None)


@pytest.mark.asyncio
async def test_stop_message_no_crash_when_event_missing(ws_app):
    """Sending 'stop' when no pre-existing event exists should still not crash."""
    from app.services.agent_orchestrator import _stop_events

    conv_id = "conv_stop_missing"
    _stop_events.pop(conv_id, None)

    try:
        async with ASGIWebSocketTransport(app=ws_app) as transport:
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                async with aconnect_ws(
                    f"ws://testserver/ws/{conv_id}?token=test-secret", client
                ) as ws:
                    await ws.send_text(json.dumps({"type": "stop"}))
                    await asyncio.sleep(0.05)
                    # Connection should still be alive
                    await ws.send_text(json.dumps({"type": "read"}))
                    resp = await _receive_json(ws)
                    assert resp["type"] == "read"
    finally:
        _stop_events.pop(conv_id, None)


@pytest.mark.asyncio
async def test_read_receipt(ws_app):
    """Sending a 'read' message should broadcast a read receipt."""
    async with ASGIWebSocketTransport(app=ws_app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with aconnect_ws(
                "ws://testserver/ws/conv_read_001?token=test-secret", client
            ) as ws:
                await ws.send_text(json.dumps({"type": "read"}))
                resp = await _receive_json(ws)

                assert resp["type"] == "read"
                assert resp["conversation_id"] == "conv_read_001"
                assert resp["reader"] == "user"


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_json_handled_gracefully(ws_app):
    """Sending malformed JSON should return an error message, not crash the socket."""
    async with ASGIWebSocketTransport(app=ws_app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with aconnect_ws(
                "ws://testserver/ws/conv_bad_json?token=test-secret", client
            ) as ws:
                await ws.send_text("this is not valid json {{{")
                resp = await _receive_json(ws)

                assert resp["type"] == "error"
                assert resp["conversation_id"] == "conv_bad_json"
                assert "Invalid JSON" in resp["content"]["text"]

                # Socket should still be alive - send a valid message to confirm
                await ws.send_text(json.dumps({"type": "read"}))
                resp2 = await _receive_json(ws)
                assert resp2["type"] == "read"


@pytest.mark.asyncio
async def test_short_user_message_filtered(ws_app):
    """A single-character user message should be silently dropped (no broadcast)."""
    async with ASGIWebSocketTransport(app=ws_app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with aconnect_ws(
                "ws://testserver/ws/conv_short?token=test-secret", client
            ) as ws:
                payload = {
                    "type": "message",
                    "sender": "user",
                    "content": {"text": "x"},
                }
                await ws.send_text(json.dumps(payload))
                # No broadcast expected; confirm the socket is still alive with a read
                await ws.send_text(json.dumps({"type": "read"}))
                resp = await _receive_json(ws)
                assert resp["type"] == "read"


@pytest.mark.asyncio
async def test_punctuation_only_user_message_filtered(ws_app):
    """A punctuation-only user message should be silently dropped."""
    async with ASGIWebSocketTransport(app=ws_app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with aconnect_ws(
                "ws://testserver/ws/conv_punct?token=test-secret", client
            ) as ws:
                payload = {
                    "type": "message",
                    "sender": "user",
                    "content": {"text": "!!??##"},
                }
                await ws.send_text(json.dumps(payload))
                await ws.send_text(json.dumps({"type": "read"}))
                resp = await _receive_json(ws)
                assert resp["type"] == "read"


@pytest.mark.asyncio
async def test_digit_only_user_message_filtered(ws_app):
    """A digit-only user message should be silently dropped."""
    async with ASGIWebSocketTransport(app=ws_app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with aconnect_ws(
                "ws://testserver/ws/conv_digits?token=test-secret", client
            ) as ws:
                payload = {
                    "type": "message",
                    "sender": "user",
                    "content": {"text": "12345"},
                }
                await ws.send_text(json.dumps(payload))
                await ws.send_text(json.dumps({"type": "read"}))
                resp = await _receive_json(ws)
                assert resp["type"] == "read"


# ---------------------------------------------------------------------------
# Disconnect / cleanup tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_cleans_up_connection(ws_app):
    """After disconnect, the conversation should be removed from active_connections."""
    from app.core.websocket import manager

    conv_id = "conv_disconnect_001"

    async with ASGIWebSocketTransport(app=ws_app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with aconnect_ws(
                f"ws://testserver/ws/{conv_id}?token=test-secret", client
            ) as ws:
                assert conv_id in manager.active_connections

            await asyncio.sleep(0.1)
            assert conv_id not in manager.active_connections


@pytest.mark.asyncio
async def test_disconnect_does_not_stop_generation(ws_app):
    """A transient client disconnect must not cancel in-flight generation."""
    from app.services.agent_orchestrator import _stop_events

    conv_id = "conv_disconnect_stop"
    event = asyncio.Event()
    _stop_events[conv_id] = event

    try:
        async with ASGIWebSocketTransport(app=ws_app) as transport:
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                async with aconnect_ws(
                    f"ws://testserver/ws/{conv_id}?token=test-secret", client
                ) as ws:
                    pass

        await asyncio.sleep(0.1)
        assert not event.is_set()
    finally:
        _stop_events.pop(conv_id, None)


# ---------------------------------------------------------------------------
# Multi-client broadcast test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcast_reaches_multiple_clients(ws_app):
    """A message sent by one client should be broadcast to all clients in the
    same conversation."""
    conv_id = "conv_multi_001"
    url = f"ws://testserver/ws/{conv_id}?token=test-secret"

    async with ASGIWebSocketTransport(app=ws_app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with aconnect_ws(url, client) as ws1, \
                       aconnect_ws(url, client) as ws2:
                payload = {
                    "type": "message",
                    "sender": "user",
                    "content": {"text": "Hello from client 1"},
                }
                await ws1.send_text(json.dumps(payload))

                resp1 = await _receive_json(ws1)
                resp2 = await _receive_json(ws2)

                assert resp1["type"] == "message"
                assert resp1["content"]["text"] == "Hello from client 1"
                assert resp2["type"] == "message"
                assert resp2["content"]["text"] == "Hello from client 1"
