"""Shared lease maintenance for local and queued generation flows."""

import asyncio
import contextlib
import logging

from app.core.concurrency import generation_admission
from app.services.agent_orchestrator import _stop_events

logger = logging.getLogger("generation_runner")


async def run_admitted_flow(user_id: str, conversation_id: str, flow) -> None:
    async def maintain_lease() -> None:
        last_heartbeat = 0.0
        while True:
            if await generation_admission.cancel_requested(conversation_id):
                event = _stop_events.get(conversation_id)
                if event:
                    event.set()
            now = asyncio.get_running_loop().time()
            if now - last_heartbeat >= max(5, generation_admission.lease_ttl // 3):
                if not await generation_admission.heartbeat(user_id, conversation_id):
                    event = _stop_events.get(conversation_id)
                    if event:
                        event.set()
                    logger.error("Generation lease was lost for %s", conversation_id)
                    return
                last_heartbeat = now
            await asyncio.sleep(0.5)

    maintenance = asyncio.create_task(
        maintain_lease(), name=f"generation_lease_{conversation_id}"
    )
    status = "completed"
    try:
        await flow
    except Exception:
        status = "failed"
        raise
    finally:
        if await generation_admission.cancel_requested(conversation_id):
            status = "cancelled"
        maintenance.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await maintenance
        await generation_admission.release(user_id, conversation_id, status=status)
