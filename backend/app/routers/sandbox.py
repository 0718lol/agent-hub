"""Code sandbox execution and healing endpoints."""
import asyncio
import logging
import re

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.metrics import metrics
from app.core.sandbox import execute_code
from app.core.tenancy import request_user_id
from app.core.tenant_settings import get_tenant_llm_client

logger = logging.getLogger("routers.sandbox")
router = APIRouter(tags=["sandbox"])


class CodeRunRequest(BaseModel):
    code: str
    language: str = "python"
    timeout: int = 10
    stdin: str = ""


@router.post("/sandbox/run")
async def sandbox_run(req: CodeRunRequest, request: Request):
    """Execute code in a sandboxed subprocess and return results."""
    result = await execute_code(
        code=req.code,
        language=req.language,
        timeout=max(1, min(req.timeout, 30)),
        stdin_data=req.stdin,
    )
    metrics.record_sandbox(
        req.language,
        result.status,
        result.duration_ms,
        user_id=request_user_id(request),
    )
    return result.to_dict()


class CodeHealRequest(BaseModel):
    code: str
    language: str
    error_output: str


@router.post("/sandbox/heal")
async def sandbox_heal(req: CodeHealRequest, request: Request):
    """Ask backend agent to heal broken code."""
    prompt = (
        f"你是一个专门修复代码报错的 AI 专家。\n"
        f"用户运行了一段 {req.language} 代码，但是失败了。\n"
        f"请分析报错原因，并只输出修复后的完整可运行代码。\n"
        f"不要任何多余的解释，必须包含在 ```{req.language} ... ``` 代码块中。\n\n"
        f"### 原始代码\n```{req.language}\n{req.code}\n```\n\n"
        f"### 报错信息\n```text\n{req.error_output}\n```\n"
    )

    response = ""
    try:
        client = await asyncio.to_thread(get_tenant_llm_client, request_user_id(request))
        async for chunk in client.chat_stream(
            [{"role": "user", "content": prompt}],
            "你是代码修复专家。只输出修复后的完整代码，不要解释。"
        ):
            response += chunk
    except Exception as e:
        return {"error": str(e), "healed_code": ""}

    # Extract code block from response
    pattern = r"```" + re.escape(req.language) + r"\s*\n(.*?)```"
    code_match = re.search(pattern, response, re.DOTALL)
    healed_code = code_match.group(1).strip() if code_match else response.strip()

    return {"healed_code": healed_code, "raw_response": response}
