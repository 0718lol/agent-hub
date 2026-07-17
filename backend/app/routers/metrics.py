"""Metrics router — SSE endpoint for real-time trace streaming.

Replaces polling with Server-Sent Events for zero-delay trace updates.
SSE is preferred over WebSocket because:
- Server-to-client only (no client messages needed)
- Browser auto-reconnect on connection loss
- HTTP-based, works through all proxies
"""
import asyncio
import json
import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.core.metrics import metrics
from app.core.tenancy import belongs_to_user, request_user_id

logger = logging.getLogger("metrics_router")

router = APIRouter(tags=["metrics"])

# Global list of SSE subscriber queues
_trace_queues: list[tuple[str, asyncio.Queue]] = []
_MAX_QUEUE_SIZE = 100


async def push_trace(trace_data: dict):
    """Push a trace update to all SSE subscribers.

    Called from metrics.TaskTrace.finish().
    Non-blocking: if queue is full, drops silently.
    """
    dead = []
    conversation_id = trace_data.get("conversation_id", "")
    for user_id, q in _trace_queues:
        if not belongs_to_user(conversation_id, user_id):
            continue
        try:
            q.put_nowait(trace_data)
        except asyncio.QueueFull:
            pass
        except Exception:
            dead.append(q)
    for q in dead:
        try:
            _trace_queues[:] = [entry for entry in _trace_queues if entry[1] is not q]
        except ValueError:
            pass


@router.get("/metrics")
async def get_metrics(request: Request):
    """Return evaluation metrics belonging to the current tenant."""
    return metrics.get_dashboard_data(user_id=request_user_id(request))


@router.get("/metrics/traces")
async def get_traces(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
):
    """Return completed and in-flight traces belonging to the current tenant."""
    user_id = request_user_id(request)
    traces = [
        trace.to_dict()
        for trace in metrics.traces
        if belongs_to_user(trace.conversation_id, user_id)
    ]
    return traces[-limit:]


@router.get("/metrics/traces/stream")
async def stream_traces(request: Request):
    """SSE endpoint: stream trace updates in real-time.

    Usage:
        const es = new EventSource('/api/metrics/traces/stream')
        es.onmessage = (e) => { const trace = JSON.parse(e.data) }
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUE_SIZE)
    entry = (request_user_id(request), queue)
    _trace_queues.append(entry)
    logger.debug(f"SSE subscriber connected (total: {len(_trace_queues)})")

    async def event_generator():
        try:
            # Send initial ping
            yield "data: {\"type\": \"connected\"}\n\n"
            while True:
                try:
                    data = await queue.get()
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                except asyncio.CancelledError:
                    break
        except Exception as e:
            logger.debug(f"SSE generator error: {e}")
        finally:
            try:
                _trace_queues.remove(entry)
            except ValueError:
                pass
            logger.debug(f"SSE subscriber disconnected (total: {len(_trace_queues)})")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
