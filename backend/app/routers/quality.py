"""Quality gate settings and evaluation endpoints."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.core.deps import get_quality_gate
from app.core.quality_gate import QualityGate

router = APIRouter(tags=["quality"])


class QualityGateSettings(BaseModel):
    enabled: bool = True
    max_retries: int = 1
    use_llm_judge: bool = False
    best_of_n: int = 1


@router.get("/settings/quality")
async def get_quality_settings(qg: QualityGate = Depends(get_quality_gate)):
    return {
        "enabled": qg.enabled,
        "max_retries": qg.max_retries,
        "use_llm_judge": qg.use_llm_judge,
        "best_of_n": qg.best_of_n,
    }


@router.post("/settings/quality")
async def update_quality_settings(s: QualityGateSettings, qg: QualityGate = Depends(get_quality_gate)):
    qg.enabled = s.enabled
    qg.max_retries = s.max_retries
    qg.use_llm_judge = s.use_llm_judge
    qg.best_of_n = s.best_of_n
    return {"status": "ok", "best_of_n": qg.best_of_n}


@router.post("/quality/evaluate")
async def evaluate_text(body: dict, qg: QualityGate = Depends(get_quality_gate)):
    """Manual quality evaluation endpoint. Body: {"text": "...", "agent_id": "..."}"""
    text = body.get("text", "")
    agent_id = body.get("agent_id", "")
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
