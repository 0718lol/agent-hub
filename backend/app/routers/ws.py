"""WebSocket endpoint for real-time agent communication."""
import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.async_wrappers import async_get_pending_hil_checkpoint, async_save_message
from app.core.auth import (
    SESSION_COOKIE,
    bearer_client_identity,
    trusted_proxy_identity,
    trusted_proxy_role,
    verify_session_token,
)
from app.core.concurrency import generation_admission
from app.core.config import settings
from app.core.crud import create_conversation
from app.core.llm_client import llm_client
from app.core.logging_config import get_logger
from app.core.quality_gate import quality_gate
from app.core.tenancy import scope_conversation_id, websocket_user_id
from app.core.tenant_settings import get_tenant_llm_client, get_tenant_quality_gate
from app.core.websocket import manager
from app.routers.harness_handler import handle_verdict
from app.services.agent_orchestrator import (
    _stop_events,
    get_agents,
    resume_graph_from_checkpoint,
    run_target_agent_flow,
    run_user_message_flow,
)
from app.services.generation_queue import (
    GenerationAlreadyQueued,
    GenerationQueueUnavailable,
    generation_queue,
)
from app.services.generation_runner import run_admitted_flow
from app.tools.judge_tools import (
    _pending_interactions,
    submit_distributed_hil_reply,
)
from app.tools.registry import reset_tool_tenant, set_tool_tenant

router = APIRouter()
logger = get_logger("ws")

# Background task tracking
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def create_tracked_task(coro, name: str | None = None) -> asyncio.Task:
    """Create and strongly reference a background asyncio task to prevent GC."""
    task = asyncio.create_task(coro, name=name)
    _BACKGROUND_TASKS.add(task)

    def finish(completed: asyncio.Task) -> None:
        _BACKGROUND_TASKS.discard(completed)
        if completed.cancelled():
            return
        try:
            error = completed.exception()
        except asyncio.CancelledError:
            return
        if error:
            logger.error(
                "Background generation failed",
                exc_info=(type(error), error, error.__traceback__),
            )

    task.add_done_callback(finish)
    return task


@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str):
    public_conversation_id = conversation_id
    # ---- WebSocket IP/Token 鉴权 ----
    # An empty secret explicitly means authentication is disabled. This is
    # needed for local Docker deployments, where the peer is the nginx
    # container rather than 127.0.0.1. Production compose requires a secret.
    auth_required = bool(settings.api_secret or settings.api_client_tokens_json) or settings.auth_mode == "proxy"
    authorized = not auth_required

    if auth_required:
        if trusted_proxy_identity(websocket.headers) or bearer_client_identity(websocket.headers):
            authorized = True
        if settings.api_secret and verify_session_token(
            websocket.cookies.get(SESSION_COOKIE), settings.api_secret
        ):
            authorized = True
    if not authorized:
        await websocket.accept()
        await websocket.close(code=4001, reason="Unauthorized connection attempt")
        return

    read_only = (
        bool(trusted_proxy_identity(websocket.headers))
        and trusted_proxy_role(websocket.headers) == "viewer"
    )
    user_id = websocket_user_id(websocket)
    try:
        conversation_id = scope_conversation_id(user_id, public_conversation_id)
    except ValueError:
        await websocket.accept()
        await websocket.close(code=4002, reason="Invalid conversation ID")
        return
    tenant_client = await asyncio.to_thread(get_tenant_llm_client, user_id)
    tenant_quality_gate = await asyncio.to_thread(get_tenant_quality_gate, user_id)
    # Direct WebSocket clients may connect before the REST conversation list
    # initializes this tenant's default rows.
    await asyncio.to_thread(
        create_conversation,
        conversation_id,
        "single",
        public_conversation_id,
        "",
        public_conversation_id.replace("conv_", "agent_", 1),
        None,
        "",
    )

    await manager.connect(websocket, conversation_id)
    generation_status = await generation_admission.get_status(conversation_id)
    if generation_status.get("state") in {"queued", "running", "cancelling"}:
        await websocket.send_json({
            "type": "generating",
            "conversation_id": public_conversation_id,
            "is_generating": True,
            "state": generation_status["state"],
        })
    tenant_client_token = llm_client.set_current(tenant_client)
    tenant_quality_token = quality_gate.set_current(tenant_quality_gate)
    tenant_tool_token = set_tool_tenant(user_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await manager.broadcast(conversation_id, {
                    "type": "error", "conversation_id": conversation_id,
                    "content": {"text": "Invalid JSON message"},
                })
                continue

            msg_type = msg.get("type", "message")
            sender = msg.get("sender", "user")
            content = msg.get("content", {})
            text = content.get("text", "")
            target_agent = content.get("target_agent")

            if read_only and msg_type != "read":
                await websocket.send_json({
                    "type": "error",
                    "conversation_id": public_conversation_id,
                    "content": {"text": "Viewer role is read-only"},
                })
                continue

            logger.debug(f"conv={conversation_id} type={msg_type} sender={sender} target_agent={target_agent} text={text[:60]}")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            # Intercept user interaction response if there's a pending interactive judge wait
            is_active_hil = conversation_id in _pending_interactions

            # Recovery path check
            is_recovered_hil = False
            if not is_active_hil:
                try:
                    checkpoint = await async_get_pending_hil_checkpoint(conversation_id)
                    if checkpoint:
                        is_recovered_hil = True
                except Exception as e:
                    logger.debug(f"Failed to check HIL checkpoint for recovery: {e}")

            if is_active_hil or is_recovered_hil:
                reply_text = text
                if reply_text.startswith("[ask_user_reply]"):
                    reply_text = reply_text.replace("[ask_user_reply]", "").strip()

                if is_active_hil:
                    fut = _pending_interactions.get(conversation_id)
                    if fut is None:
                        pass  # Entry removed during await, fall through
                    elif not fut.done():
                        with contextlib.suppress(asyncio.InvalidStateError):
                            fut.set_result(reply_text)
                else:
                    status = await generation_admission.get_status(conversation_id)
                    bridged = (
                        settings.generation_worker_enabled
                        and status.get("state") in {"queued", "running", "cancelling"}
                        and await submit_distributed_hil_reply(
                            conversation_id, reply_text
                        )
                    )
                    if not bridged:
                        # No live Worker owns the flow; resume from the DB checkpoint.
                        create_tracked_task(
                            resume_graph_from_checkpoint(
                                conversation_id, reply_text
                            ),
                            name=f"resume_graph_{conversation_id}",
                        )

                # We still want to save and broadcast this message to display it in the Chat UI as a user reply
                await async_save_message(conversation_id, sender, content, streaming=False)
                await manager.broadcast(conversation_id, {
                    "type": "message",
                    "conversation_id": conversation_id,
                    "sender": sender,
                    "content": {"text": text},
                    "stream": False,
                })
                continue

            # Handle stop generation — must be processed without blocking on
            # the in-flight generation task (which is why generation runs as a
            # background task, not awaited here).
            if msg_type == "stop":
                if settings.generation_worker_enabled:
                    with contextlib.suppress(GenerationQueueUnavailable):
                        await generation_queue.request_cancel_by_conversation(
                            conversation_id
                        )
                await generation_admission.request_cancel(conversation_id)
                event = _stop_events.get(conversation_id)
                logger.debug(f"[STOP] conv={conversation_id} event_exists={event is not None} already_set={event.is_set() if event else 'N/A'}")
                if event:
                    event.set()
                continue

            # Handle read receipt
            if msg_type == "read":
                await manager.broadcast(conversation_id, {
                    "type": "read",
                    "conversation_id": conversation_id,
                    "reader": "user",
                })
                continue

            # Handle harness verdict (user裁决指令)
            if msg_type == "harness_verdict":
                await handle_verdict(conversation_id, msg, manager)
                continue

            # 过滤无意义消息：太短、纯数字、纯标点
            if sender == "user":
                stripped = text.strip()
                if len(stripped) < 2:
                    continue
                if stripped.isdigit() or all(c in "!@#$%^&*()_+-=[]{}|;:',.<>?/~`" for c in stripped):
                    continue

                current_agents = get_agents(conversation_id)
                queued_job = None
                if settings.generation_worker_enabled:
                    try:
                        queued_job = await generation_queue.enqueue(
                            conversation_id,
                            user_id,
                            text,
                            target_agent if target_agent in current_agents else None,
                        )
                    except (GenerationAlreadyQueued, GenerationQueueUnavailable) as exc:
                        await manager.broadcast(conversation_id, {
                            "type": "error",
                            "conversation_id": conversation_id,
                            "content": {"text": str(exc)},
                        })
                        continue
                else:
                    admitted, reason = await generation_admission.acquire(
                        user_id, conversation_id
                    )
                    if not admitted:
                        await manager.broadcast(conversation_id, {
                            "type": "error",
                            "conversation_id": conversation_id,
                            "content": {"text": reason},
                        })
                        continue
            else:
                current_agents = get_agents(conversation_id)
                queued_job = None

            await async_save_message(conversation_id, sender, content, streaming=False)

            await manager.broadcast(conversation_id, {
                "type": "message",
                "conversation_id": conversation_id,
                "sender": sender,
                "content": {"text": text},
                "stream": False,
            })

            if queued_job is not None:
                await manager.broadcast(conversation_id, {
                    "type": "generating",
                    "conversation_id": conversation_id,
                    "is_generating": True,
                    "state": "queued",
                    "job_id": queued_job.id,
                })
            elif sender == "user" and target_agent and target_agent in current_agents:
                create_tracked_task(
                    run_admitted_flow(
                        user_id,
                        conversation_id,
                        run_target_agent_flow(conversation_id, current_agents[target_agent], text),
                    ),
                    name=f"target_agent_{conversation_id}",
                )
            elif sender == "user":
                create_tracked_task(
                    run_admitted_flow(
                        user_id,
                        conversation_id,
                        run_user_message_flow(conversation_id, text, target_agent),
                    ),
                    name=f"user_flow_{conversation_id}",
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket, conversation_id)
        # A browser refresh or brief network loss must not abort generation.
        # The explicit "stop" message remains the only user cancellation path.
    finally:
        reset_tool_tenant(tenant_tool_token)
        quality_gate.reset_current(tenant_quality_token)
        llm_client.reset_current(tenant_client_token)
