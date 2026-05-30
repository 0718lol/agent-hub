"""Benchmark execution and status endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel
from app.core.benchmark import run_benchmark, get_current_run, BENCHMARK_CASES

router = APIRouter(tags=["benchmark"])


class BenchmarkRequest(BaseModel):
    case_ids: list[str] | None = None
    provider: str | None = None
    model: str | None = None


@router.get("/benchmark/cases")
async def list_benchmark_cases():
    return [{"id": c["id"], "name": c["name"], "category": c.get("category", "general")}
            for c in BENCHMARK_CASES]


@router.post("/benchmark/run")
async def start_benchmark(req: BenchmarkRequest):
    import asyncio
    case_ids = req.case_ids or [c["id"] for c in BENCHMARK_CASES]
    task = asyncio.create_task(run_benchmark(case_ids))
    return {"status": "started", "case_count": len(case_ids)}


@router.get("/benchmark/status")
async def benchmark_status():
    run = get_current_run()
    if not run:
        return {"status": "idle"}
    return run
