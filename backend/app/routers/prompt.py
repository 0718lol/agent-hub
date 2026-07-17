"""Prompt engine configuration endpoints."""
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.prompt_engine import prompt_engine
from app.core.tenancy import request_user_id
from app.services.agent_registry import agent_registry


class PromptLayerToggle(BaseModel):
    enabled: bool = True


class PromptPreviewRequest(BaseModel):
    agent_id: str = "agent_frontend"
    message: str = ""
    task_type: str | None = None


router = APIRouter(tags=["prompt"])


@router.get("/prompt/layers")
async def list_prompt_layers():
    """List all prompt layers with their status."""
    return prompt_engine.get_layers_info()


@router.post("/prompt/layers/{layer_id}")
async def toggle_prompt_layer(layer_id: str, body: PromptLayerToggle):
    """Enable/disable a prompt layer."""
    enabled = body.enabled
    prompt_engine.set_layer_enabled(layer_id, enabled)
    return {"status": "ok", "layer_id": layer_id, "enabled": enabled}


@router.post("/prompt/preview")
async def preview_prompt(body: PromptPreviewRequest, request: Request):
    """Preview the assembled prompt for a given agent and context."""
    agent_id = body.agent_id
    message = body.message
    task_type = body.task_type

    agent = await agent_registry.get_agent(agent_id, request_user_id(request))
    if not agent:
        return {"error": f"Agent {agent_id} not found"}

    if not task_type and message:
        task_type = prompt_engine.detect_task_type(message, agent_id)

    ctx = {"task_type": task_type}
    assembled = prompt_engine.build(agent, ctx)
    return {
        "agent_id": agent_id,
        "task_type": task_type,
        "assembled_prompt": assembled,
        "char_count": len(assembled),
        "estimated_tokens": len(assembled) // 3,
    }
