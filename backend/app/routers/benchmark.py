"""Benchmark execution and status endpoints."""
import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.benchmark import BENCHMARK_CASES, get_current_run, run_benchmark

router = APIRouter(tags=["benchmark"])
from app.core.logging_config import get_logger

logger = get_logger("benchmark")

# Module-level reference to prevent GC of background benchmark task.
# KNOWN LIMITATION: With uvicorn --workers > 1, each worker has its own
# independent copy of this variable. Workers cannot detect each other's
# running benchmarks. Cross-worker coordination requires an external store
# (e.g. Redis lock or database flag) — not yet implemented.
_active_benchmark_task: asyncio.Task | None = None


class BenchmarkRequest(BaseModel):
    case_ids: list[str] | None = None
    provider: str | None = None
    model: str | None = None


@router.get("/benchmark/cases")
async def list_benchmark_cases():
    return [{"id": c.id, "name": c.name, "category": getattr(c, "category", "general")}
            for c in BENCHMARK_CASES]


@router.post("/benchmark/run")
async def start_benchmark(req: BenchmarkRequest):
    import asyncio
    global _active_benchmark_task
    if _active_benchmark_task and not _active_benchmark_task.done():
        return {"status": "error", "message": "A benchmark is already running."}
    case_ids = req.case_ids or [c.id for c in BENCHMARK_CASES]
    _active_benchmark_task = asyncio.create_task(run_benchmark(case_ids))
    _active_benchmark_task.add_done_callback(_on_benchmark_done)
    return {"status": "started", "case_count": len(case_ids)}


def _on_benchmark_done(task: asyncio.Task):
    global _active_benchmark_task
    _active_benchmark_task = None
    try:
        task.result()
    except Exception as e:
        logger.warning(f"Benchmark task failed: {e}")


@router.get("/benchmark/status")
async def benchmark_status():
    run = get_current_run()
    if not run:
        return {"status": "idle"}
    return run
