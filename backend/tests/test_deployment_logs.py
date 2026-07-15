"""Tests for tenant-scoped deployment log downloads."""

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.main import download_deployment_logs
from app.services.deployment_queue import DeploymentJob, deployment_queue


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


@pytest.mark.asyncio
async def test_download_log_contains_structured_pipeline_entries(monkeypatch):
    job = DeploymentJob(
        id="a" * 32,
        conversation_id="tenant__api-client__conv__demo",
        user_id="api-client",
        target="apk",
        status="failed",
        stage="sign",
        progress=74,
        log="签名失败",
        log_entries=[{
            "timestamp": "2026-07-15T08:00:00+00:00",
            "stage": "sign",
            "level": "error",
            "message": "签名失败",
            "progress": 74,
        }],
    )

    async def get_job(_job_id):
        return job

    monkeypatch.setattr(deployment_queue, "get", get_job)
    response = await download_deployment_logs(job.id, _request())
    content = response.body.decode("utf-8")

    assert response.headers["content-disposition"].endswith(f'"deployment-{job.id}.log"')
    assert "[签名] [ERROR] 签名失败" in content
    assert "status: failed" in content


@pytest.mark.asyncio
async def test_download_log_does_not_expose_another_users_job(monkeypatch):
    job = DeploymentJob(
        id="b" * 32,
        conversation_id="tenant__other__conv__demo",
        user_id="other",
        target="web",
    )

    async def get_job(_job_id):
        return job

    monkeypatch.setattr(deployment_queue, "get", get_job)
    with pytest.raises(HTTPException) as exc:
        await download_deployment_logs(job.id, _request())

    assert exc.value.status_code == 404
