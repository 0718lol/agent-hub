"""Compatibility helpers for legacy output validation call sites.

The product no longer uses format gate retries in the main flow. Keep these
helpers permissive so older imports and tests stay stable without enforcing
format constraints.
"""
import logging
import re

logger = logging.getLogger("output_validator")


# ============================================================
# Pydantic schemas for expected output formats
# ============================================================

from pydantic import BaseModel, Field, validator


class ToolCall(BaseModel):
    """Validated tool call from LLM output."""
    name: str = Field(..., description="Tool name")
    params: dict = Field(default_factory=dict, description="Tool parameters")

    @validator("name")
    def validate_tool_name(cls, v):
        valid_tools = {
            "browser_open_url", "browser_get_content", "browser_screenshot",
            "browser_click", "browser_type", "browser_scroll", "browser_wait",
            "git_commit", "git_push", "create_pr",
        }
        if v not in valid_tools:
            raise ValueError(f"Unknown tool: {v}")
        return v


class AgentOutput(BaseModel):
    """Validated agent output."""
    text: str = Field(..., description="Response text")
    tool_calls: list[ToolCall] = Field(default_factory=list, description="Tool calls")
    has_code_block: bool = Field(default=False, description="Whether output contains code")
    ends_with_question: bool = Field(default=False, description="Whether output ends with question")

    @validator("ends_with_question", always=True)
    def check_question(cls, v, values):
        text = values.get("text", "")
        # Exclude [ask_user:] tags
        clean = re.sub(r'\[ask_user:.*?\]', '', text, flags=re.DOTALL)
        # Exclude code blocks
        clean = re.sub(r'```.*?```', '', clean, flags=re.DOTALL)
        # Check if ends with question
        clean = clean.strip()
        if clean and (clean.endswith('?') or clean.endswith('？')):
            return True
        return False


# ============================================================
# Validation functions
# ============================================================

def parse_tool_calls(text: str) -> list[dict]:
    """Parse [tool_call:name]{params}[/tool_call] from text."""
    calls = []
    pattern = r'\[tool_call:(\w+)\](.*?)\[/tool_call\]'
    for match in re.finditer(pattern, text, re.DOTALL):
        name = match.group(1)
        try:
            import json
            params = json.loads(match.group(2))
        except Exception:
            params = {}
        calls.append({"name": name, "params": params})
    return calls


def validate_output(text: str, agent_id: str) -> tuple[bool, str, dict]:
    """Return permissive validation metadata without blocking output."""
    tool_calls = parse_tool_calls(text)
    has_code = "```" in text
    clean = re.sub(r'\[ask_user:.*?\]', '', text, flags=re.DOTALL)
    clean = re.sub(r'```.*?```', '', clean, flags=re.DOTALL)
    clean = clean.strip()
    ends_with_question = clean.endswith('?') or clean.endswith('？') if clean else False
    metadata = {
        "tool_calls": tool_calls,
        "has_code": has_code,
        "ends_with_question": ends_with_question,
        "length": len(text),
    }
    return True, "disabled", metadata


def get_retry_prompt(agent_id: str, reason: str, original_text: str, user_text: str) -> str:
    """Return a neutral compatibility prompt."""
    return f"输出校验已停用。用户原始需求：{user_text}"
