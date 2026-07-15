"""Generation admission control regression tests."""

import pytest

from app.core.concurrency import GenerationAdmissionController


@pytest.mark.asyncio
async def test_same_conversation_cannot_generate_twice():
    controller = GenerationAdmissionController(max_per_user=2)
    assert (await controller.acquire("user", "conv-1"))[0]
    accepted, reason = await controller.acquire("user", "conv-1")
    assert not accepted
    assert "正在生成" in reason
    await controller.release("user", "conv-1")
    assert (await controller.acquire("user", "conv-1"))[0]


@pytest.mark.asyncio
async def test_per_user_limit_does_not_block_another_user():
    controller = GenerationAdmissionController(max_per_user=2)
    assert (await controller.acquire("user-a", "a-1"))[0]
    assert (await controller.acquire("user-a", "a-2"))[0]
    assert not (await controller.acquire("user-a", "a-3"))[0]
    assert (await controller.acquire("user-b", "b-1"))[0]
