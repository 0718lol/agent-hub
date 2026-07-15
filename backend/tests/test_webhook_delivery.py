"""Regression tests for outbound HIL notification delivery."""

import pytest

from app.services.webhook_gateway import WebhookGatewayManager


@pytest.mark.asyncio
async def test_slack_delivery_uses_configured_webhook(monkeypatch):
    calls = []

    class Response:
        status_code = 200

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, json):
            calls.append((url, json))
            return Response()

    monkeypatch.setattr("app.services.webhook_gateway.httpx.AsyncClient", lambda **_kwargs: Client())
    gateway = WebhookGatewayManager()
    gateway.register_channels(slack_url="https://hooks.slack.test/services/example")

    delivered = await gateway.send_hil_notification(
        "conversation-1", "Continue?", [{"label": "Approve", "description": "", "recommended": True}],
    )

    assert delivered is True
    assert calls[0][0] == "https://hooks.slack.test/services/example"
    assert calls[0][1]["text"] == "Continue?"


@pytest.mark.asyncio
async def test_webhook_delivery_returns_false_after_failed_retries(monkeypatch):
    calls = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, json):
            calls.append((url, json))
            raise httpx.ConnectError("offline")

    import httpx
    monkeypatch.setattr("app.services.webhook_gateway.httpx.AsyncClient", lambda **_kwargs: Client())
    gateway = WebhookGatewayManager()
    gateway.register_channels(slack_url="https://hooks.slack.test/services/example")

    delivered = await gateway.send_hil_notification(
        "conversation-1", "Continue?", [{"label": "Approve", "description": "", "recommended": True}],
    )

    assert delivered is False
    assert len(calls) == 2


def test_channel_status_does_not_expose_credentials():
    gateway = WebhookGatewayManager()
    gateway.register_channels("https://hooks.slack.test/secret", "bot-secret", "chat-id")
    assert gateway.channel_status() == {"slack": True, "telegram": True}
