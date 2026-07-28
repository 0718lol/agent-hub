"""Operational readiness endpoints."""

from fastapi import APIRouter, Query

from app.core.preflight import PreflightProfile, run_preflight

router = APIRouter(tags=["system"])


@router.get("/system/preflight")
async def system_preflight(
    profile: PreflightProfile = Query(default="core"),
):
    return await run_preflight(profile)
