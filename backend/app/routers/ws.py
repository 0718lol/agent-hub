"""WebSocket endpoint for real-time agent communication."""
import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.async_wrappers import async_get_pending_hil_checkpoint, async_save_message
from app.core.concurrency import generation_admission
from app.core.crud import create_conversation, initialize_conversation_goal
from app.core.logging_config import get_logger
from app.core.tenancy import (
    reset_current_tenant,
    scope_conversation_id,
    set_current_tenant,
    websocket_user_id,
)
from app.core.websocket import manager
from app.routers.harness_handler import handle_verdict
from app.services.agent_orchestrator import (
    _stop_events,
    get_agents,
    resume_graph_from_checkpoint,
    run_target_agent_flow,
    run_user_message_flow,
)
from app.tools.judge_tools import _pending_interactions

router = APIRouter()
logger = get_logger("ws")

# Background task tracking
_BACKGROUND_TASKS: set[asyncio.Task] = set()


async def _run_admitted_flow(user_id: str, conversation_id: str, flow) -> None:
    try:
        await flow
    finally:
        await generation_admission.release(user_id, conversation_id)


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


async def _protocol_error(conversation_id: str, text: str) -> None:
    await manager.broadcast(conversation_id, {
        "type": "error",
        "conversation_id": conversation_id,
        "content": {"text": text},
    })


@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str):
    user_id = websocket_user_id(websocket)
    if not user_id:
        await websocket.accept()
        await websocket.close(code=4001, reason="Unauthorized connection attempt")
        return

    token = set_current_tenant(user_id)
    try:
        await _serve_authenticated_websocket(websocket, conversation_id, user_id)
    finally:
        reset_current_tenant(token)


async def _serve_authenticated_websocket(
    websocket: WebSocket,
    public_conversation_id: str,
    user_id: str,
) -> None:
    conversation_id = public_conversation_id

    try:
        conversation_id = scope_conversation_id(user_id, public_conversation_id)
    except ValueError:
        await websocket.accept()
        await websocket.close(code=4002, reason="Invalid conversation ID")
        return
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
    # Heartbeat task to keep connection alive
    async def _heartbeat():
        while True:
            try:
                await asyncio.sleep(30)
                await websocket.send_json({"type": "ping"})
            except Exception:
                break

    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await _protocol_error(conversation_id, "Invalid JSON message")
                continue
            if not isinstance(msg, dict):
                await _protocol_error(conversation_id, "Message must be a JSON object")
                continue

            msg_type = msg.get("type", "message")
            if not isinstance(msg_type, str):
                await _protocol_error(conversation_id, "Message type must be a string")
                continue
            content = msg.get("content", {})
            if not isinstance(content, dict):
                await _protocol_error(conversation_id, "Message content must be an object")
                continue
            text = content.get("text", "")
            if not isinstance(text, str):
                await _protocol_error(conversation_id, "Message text must be a string")
                continue
            target_agent = content.get("target_agent")
            if target_agent is not None and not isinstance(target_agent, str):
                await _protocol_error(conversation_id, "target_agent must be a string")
                continue
            sender = "user"

            logger.debug(f"conv={conversation_id} type={msg_type} sender={sender} target_agent={target_agent} text={text[:60]}")

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
                    # Recovery path: trigger asynchronous recovery task
                    create_tracked_task(resume_graph_from_checkpoint(conversation_id, reply_text), name=f"resume_graph_{conversation_id}")

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

            # Only empty input is ignored. Single-character, numeric, and
            # punctuation replies can carry valid conversational meaning.
            if sender == "user":
                stripped = text.strip()
                if not stripped:
                    continue

                admitted, reason = await generation_admission.acquire(user_id, conversation_id)
                if not admitted:
                    await manager.broadcast(conversation_id, {
                        "type": "error",
                        "conversation_id": conversation_id,
                        "content": {"text": reason},
                    })
                    continue

                await asyncio.to_thread(initialize_conversation_goal, conversation_id, stripped)

            await async_save_message(conversation_id, sender, content, streaming=False)

            await manager.broadcast(conversation_id, {
                "type": "message",
                "conversation_id": conversation_id,
                "sender": sender,
                "content": {"text": text},
                "stream": False,
            })

            current_agents = get_agents(user_id)
            if target_agent and target_agent in current_agents:
                create_tracked_task(
                    _run_admitted_flow(
                        user_id,
                        conversation_id,
                        run_target_agent_flow(conversation_id, current_agents[target_agent], text),
                    ),
                    name=f"target_agent_{conversation_id}",
                )
            elif sender == "user":
                create_tracked_task(
                    _run_admitted_flow(
                        user_id,
                        conversation_id,
                        run_user_message_flow(conversation_id, text, target_agent),
                    ),
                    name=f"user_flow_{conversation_id}",
                )

    except WebSocketDisconnect:
        heartbeat_task.cancel()
        pass
    except Exception:
        logger.exception("WebSocket handler failed for conversation %s", conversation_id)
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason="Internal server error")
    finally:
        manager.disconnect(websocket, conversation_id)
        # A browser refresh or brief network loss must not abort generation.
        # The explicit "stop" message remains the only user cancellation path.
