"""Quality gate settings and evaluation endpoints."""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.deps import get_quality_gate
from app.core.quality_gate import QualityGate
from app.core.tenancy import request_user_id
from app.core.tenant_config import set_tenant_json

router = APIRouter(tags=["quality"])


class QualityGateSettings(BaseModel):
    enabled: bool = True
    max_retries: int = Field(default=1, ge=0, le=5)
    use_llm_judge: bool = False
    best_of_n: int = Field(default=1, ge=1, le=10)


@router.get("/settings/quality")
async def get_quality_settings(qg: QualityGate = Depends(get_quality_gate)):
    return {
        "enabled": qg.enabled,
        "max_retries": qg.max_retries,
        "use_llm_judge": qg.use_llm_judge,
        "best_of_n": qg.best_of_n,
    }


@router.post("/settings/quality")
async def update_quality_settings(s: QualityGateSettings, request: Request, qg: QualityGate = Depends(get_quality_gate)):
    qg.enabled = s.enabled
    qg.max_retries = s.max_retries
    qg.use_llm_judge = s.use_llm_judge
    qg.best_of_n = s.best_of_n
    set_tenant_json(request_user_id(request), "quality_gate", s.model_dump())
    return {"status": "ok", "best_of_n": qg.best_of_n}


class EvaluateRequest(BaseModel):
    text: str
    agent_id: str = ""


@router.post("/quality/evaluate")
async def evaluate_text(body: EvaluateRequest, qg: QualityGate = Depends(get_quality_gate)):
    """Manual quality evaluation endpoint. Body: {"text": "...", "agent_id": "..."}"""
    text = body.text
    agent_id = body.agent_id
    if not text:
        return {"error": "text is required"}
    report = qg.evaluate(text, agent_id)
    return report.to_dict()


@router.get("/quality/standards")
async def list_quality_standards():
    from app.core.quality_standards import STANDARDS
    return {
        k: {"name": v["name"], "pass_threshold": v["pass_threshold"],
             "rules_count": len(v["rules"])}
        for k, v in STANDARDS.items()
    }
