"""Tenant LLM usage accounting tests."""

from unittest.mock import AsyncMock, MagicMock

from app.core.llm_client import LLMClient, get_daily_llm_usage, resilience_manager


class _UsagePipeline:
    def __init__(self, client):
        self.client = client
        self.operations = []

    def hincrby(self, key, field, amount):
        self.operations.append(("inc", key, field, amount))
        return self

    def hset(self, key, mapping):
        self.operations.append(("set", key, mapping))
        return self

    def expire(self, key, seconds):
        self.operations.append(("expire", key, seconds))
        return self

    async def execute(self):
        for operation in self.operations:
            if operation[0] == "inc":
                _, key, field, amount = operation
                values = self.client.values.setdefault(key, {})
                values[field] = str(int(values.get(field, 0)) + amount)
            elif operation[0] == "set":
                _, key, mapping = operation
                self.client.values.setdefault(key, {}).update(mapping)


class _UsageRedis:
    def __init__(self):
        self.values = {}

    async def hget(self, key, field):
        return self.values.get(key, {}).get(field)

    async def hgetall(self, key):
        return dict(self.values.get(key, {}))

    def pipeline(self, transaction=False):
        assert not transaction
        return _UsagePipeline(self)


class _FailingUsageRedis:
    async def hget(self, key, field):
        del key, field
        raise ConnectionError("redis disconnected")

    async def hgetall(self, key):
        del key
        raise ConnectionError("redis disconnected")

    def pipeline(self, transaction=False):
        del transaction
        pipeline = MagicMock()
        pipeline.hincrby.return_value = pipeline
        pipeline.hset.return_value = pipeline
        pipeline.expire.return_value = pipeline
        pipeline.execute = AsyncMock(side_effect=ConnectionError("redis disconnected"))
        return pipeline


async def test_provider_usage_is_persisted_for_the_tenant(monkeypatch):
    from app.core.redis import redis_manager

    fake_redis = _UsageRedis()
    monkeypatch.setattr(redis_manager, "check_connection", AsyncMock(return_value=True))
    monkeypatch.setattr(redis_manager, "get_client", lambda: fake_redis)

    async def fake_execute(client_instance, stream_func, messages, system, enabled_tools):
        del stream_func, messages, system, enabled_tools
        client_instance.provider = "anthropic"
        client_instance.model = "claude-test"
        client_instance._set_provider_usage({"input_tokens": 12, "output_tokens": 5})
        client_instance.provider = "openai"
        client_instance.model = "primary-test"
        yield "done"

    monkeypatch.setattr(resilience_manager, "execute_with_retry", fake_execute)
    client = LLMClient()
    client.configure("openai", "key", "https://example.test/v1", "primary-test")
    client.tenant_id = "tenant-a"

    result = "".join([chunk async for chunk in client.chat_stream([{"role": "user", "content": "hello"}])])
    usage = await get_daily_llm_usage("tenant-a")

    assert result == "done"
    assert usage["prompt_tokens"] == 12
    assert usage["completion_tokens"] == 5
    assert usage["total_tokens"] == 17
    assert usage["provider"] == "anthropic"
    assert usage["model"] == "claude-test"


async def test_usage_backend_failure_does_not_break_model_output(monkeypatch):
    from app.core.config import settings
    from app.core.redis import redis_manager

    fake_redis = _FailingUsageRedis()
    monkeypatch.setattr(settings, "llm_daily_token_quota", 100)
    monkeypatch.setattr(redis_manager, "check_connection", AsyncMock(return_value=True))
    monkeypatch.setattr(redis_manager, "get_client", lambda: fake_redis)
    monkeypatch.setattr(redis_manager, "mark_unavailable", MagicMock())

    async def fake_execute(client_instance, stream_func, messages, system, enabled_tools):
        del client_instance, stream_func, messages, system, enabled_tools
        yield "done"

    monkeypatch.setattr(resilience_manager, "execute_with_retry", fake_execute)
    client = LLMClient()
    client.configure("openai", "key", "https://example.test/v1", "primary-test")
    client.tenant_id = "tenant-a"

    result = "".join([
        chunk async for chunk in client.chat_stream([{"role": "user", "content": "hello"}])
    ])
    usage = await get_daily_llm_usage("tenant-a")

    assert result == "done"
    assert usage == {"available": False, "quota": 100}
    assert redis_manager.mark_unavailable.call_count >= 2
