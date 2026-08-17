"""Benchmark execution and status endpoints."""
import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.benchmark import BENCHMARK_CASES, BenchmarkRun, run_benchmark
from app.core.quality_gate import quality_gate
from app.core.tenancy import request_user_id, reset_current_tenant, set_current_tenant
from app.services.agent_registry import agent_registry

router = APIRouter(tags=["benchmark"])
from app.core.logging_config import get_logger

logger = get_logger("benchmark")

# Module-level reference to prevent GC of background benchmark task.
# KNOWN LIMITATION: With uvicorn --workers > 1, each worker has its own
# independent copy of this variable. Workers cannot detect each other's
# running benchmarks. Cross-worker coordination requires an external store
# (e.g. Redis lock or database flag) — not yet implemented.
_active_benchmark_tasks: dict[str, asyncio.Task] = {}
_benchmark_runs: dict[str, BenchmarkRun] = {}


class BenchmarkRequest(BaseModel):
    case_ids: list[str] | None = None
    provider: str | None = None
    model: str | None = None


@router.get("/benchmark/cases")
async def list_benchmark_cases():
    return [{"id": c.id, "name": c.name, "category": getattr(c, "category", "general")}
            for c in BENCHMARK_CASES]


async def _run_tenant_benchmark(
    tenant_id: str,
    agents: dict,
    cases: list,
    run: BenchmarkRun,
) -> None:
    token = set_current_tenant(tenant_id)
    try:
        await run_benchmark(agents, quality_gate, cases=cases, run=run)
    except Exception as exc:
        logger.exception("Benchmark failed for tenant %s", tenant_id)
        run.fail(str(exc))
    finally:
        reset_current_tenant(token)


@router.post("/benchmark/run")
async def start_benchmark(request: Request, req: BenchmarkRequest | None = None):
    tenant_id = request_user_id(request)
    active = _active_benchmark_tasks.get(tenant_id)
    if active and not active.done():
        raise HTTPException(status_code=409, detail="A benchmark is already running.")

    requested_ids = (req.case_ids if req else None) or [case.id for case in BENCHMARK_CASES]
    known = {case.id: case for case in BENCHMARK_CASES}
    unknown = sorted(set(requested_ids) - set(known))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown benchmark cases: {', '.join(unknown)}")
    cases = [known[case_id] for case_id in requested_ids]
    agents = await agent_registry.get_all_agents(tenant_id)
    run = BenchmarkRun(total=len(cases))
    _benchmark_runs[tenant_id] = run
    task = asyncio.create_task(_run_tenant_benchmark(tenant_id, agents, cases, run))
    _active_benchmark_tasks[tenant_id] = task
    task.add_done_callback(lambda completed: _on_benchmark_done(tenant_id, completed))
    return {"status": "started", "case_count": len(cases)}


def _on_benchmark_done(tenant_id: str, task: asyncio.Task):
    _active_benchmark_tasks.pop(tenant_id, None)
    try:
        task.result()
    except Exception as e:
        logger.warning(f"Benchmark task failed: {e}")


@router.get("/benchmark/status")
async def benchmark_status(request: Request):
    run = _benchmark_runs.get(request_user_id(request))
    if not run:
        return {"status": "idle"}
    return run.to_dict()
