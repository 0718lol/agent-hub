"""Administrator-only account migration and recovery endpoints."""

import asyncio

from fastapi import APIRouter, HTTPException, Request

from app.core.accounts import list_legacy_tenants
from app.core.auth import SESSION_COOKIE, get_session_account

router = APIRouter(tags=["admin"])


def _require_admin(request: Request):
    account = get_session_account(request.cookies.get(SESSION_COOKIE))
    if account is None:
        raise HTTPException(status_code=401, detail="请先登录")
    if not account.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可访问")
    return account


@router.get("/admin/legacy-tenants")
async def legacy_tenants(request: Request):
    _require_admin(request)
    tenants = await asyncio.to_thread(list_legacy_tenants)
    return {"tenants": tenants, "automatic_merge": False}
