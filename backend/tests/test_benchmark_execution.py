"""Benchmark execution and tenant-state regression tests."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.benchmark import BENCHMARK_CASES, BenchmarkRun, run_benchmark


class _Agent:
    async def stream_reply(self, message, history=None):
        yield "def answer():\n    return 1\n"


class _Gate:
    def __init__(self, fail_best=False):
        self.best_of_n = 1
        self.fail_best = fail_best
        self.requested_n = None

    def evaluate(self, text, agent_id=""):
        return type("Report", (), {"score": 0.8})()

    async def best_of_n_generate(self, agent, message, agent_id="", n=None):
        self.requested_n = n
        if self.fail_best:
            raise RuntimeError("candidate failure")
        report = type("Report", (), {"score": 0.9})()
        return "best", report, []


@pytest.mark.asyncio
async def test_benchmark_uses_sync_evaluate_and_explicit_best_of_n():
    gate = _Gate(fail_best=True)
    run = await run_benchmark(
        {"agent_backend": _Agent()},
        gate,
        cases=[BENCHMARK_CASES[0]],
    )

    assert run.status == "completed"
    assert gate.best_of_n == 1
    assert gate.requested_n == 3
    assert "candidate failure" in run.results[0].normal_output


@pytest.mark.asyncio
async def test_benchmark_route_accepts_empty_body_and_isolates_status():
    from app.routers import benchmark

    app = FastAPI()

    @app.middleware("http")
    async def inject_tenant(request, call_next):
        request.state.tenant_id = request.headers.get("x-test-tenant", "tenant-a")
        return await call_next(request)

    app.include_router(benchmark.router, prefix="/api")

    async def finish_run(tenant_id, agents, cases, run: BenchmarkRun):
        run.finish()

    transport = ASGITransport(app=app)
    with (
        patch.object(benchmark.agent_registry, "get_all_agents", AsyncMock(return_value={})),
        patch.object(benchmark, "_run_tenant_benchmark", side_effect=finish_run),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            started = await client.post("/api/benchmark/run", headers={"x-test-tenant": "tenant-a"})
            assert started.status_code == 200
            await asyncio.sleep(0)
            own = await client.get("/api/benchmark/status", headers={"x-test-tenant": "tenant-a"})
            other = await client.get("/api/benchmark/status", headers={"x-test-tenant": "tenant-b"})

    assert own.json()["status"] == "completed"
    assert other.json() == {"status": "idle"}


@pytest.mark.asyncio
async def test_benchmark_route_rejects_unknown_case():
    from app.routers import benchmark

    app = FastAPI()

    @app.middleware("http")
    async def inject_tenant(request, call_next):
        request.state.tenant_id = "tenant-a"
        return await call_next(request)

    app.include_router(benchmark.router, prefix="/api")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/benchmark/run", json={"case_ids": ["missing"]})

    assert response.status_code == 422
