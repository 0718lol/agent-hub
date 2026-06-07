"""Output validation and auto-retry for LLM responses.

Provides Pydantic-based validation of LLM output with automatic retry
on validation failure. Works with all LLM providers.
"""
import logging
import re
from typing import Optional

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
    """Validate LLM output against expected format.
    
    Returns:
        (is_valid, reason, metadata)
    """
    # Parse tool calls
    tool_calls = parse_tool_calls(text)

    # Check for code blocks
    has_code = "```" in text

    # Check for questions (excluding [ask_user:] and code blocks)
    clean = re.sub(r'\[ask_user:.*?\]', '', text, flags=re.DOTALL)
    clean = re.sub(r'```.*?```', '', clean, flags=re.DOTALL)
    clean = clean.strip()
    ends_with_question = clean.endswith('?') or clean.endswith('？') if clean else False

    # Agent-specific validation
    if agent_id == "agent_pm":
        if not any(tc["name"] == "" for tc in tool_calls) and "[assign:" not in text:
            return False, "PM must output [assign:agent_xxx] tags", {}

    elif agent_id == "agent_frontend":
        if not has_code and not any(tc["name"].startswith("browser_") for tc in tool_calls):
            return False, "FrontendAgent must output code blocks or use browser tools", {}

    elif agent_id == "agent_backend":
        if not has_code and not any(tc["name"].startswith("browser_") for tc in tool_calls):
            return False, "BackendAgent must output code blocks or use browser tools", {}

    # Anti-pattern: ends with question (except PM with ask_user)
    if ends_with_question and agent_id != "agent_pm":
        return False, "Output ends with question (use [ask_user:] instead)", {}

    # Anti-pattern: too short
    if len(text.strip()) < 20:
        return False, "Output too short", {}

    metadata = {
        "tool_calls": tool_calls,
        "has_code": has_code,
        "ends_with_question": ends_with_question,
        "length": len(text),
    }

    return True, "passed", metadata


def get_retry_prompt(agent_id: str, reason: str, original_text: str, user_text: str) -> str:
    """Generate a retry prompt with explicit format instructions."""
    format_instructions = {
        "agent_pm": (
            "你必须输出任务分配标签。"
            "在回复末尾添加 [assign:agent_frontend] [assign:agent_backend] 等标签。"
            "不要问用户任何问题，直接拆解任务。"
        ),
        "agent_frontend": (
            "你必须输出完整可运行的代码。"
            "用 ```html 或 ```jsx 代码块包裹。"
            "不要问用户任何问题，直接实现。"
        ),
        "agent_backend": (
            "你必须输出完整可运行的代码。"
            "用 ```python 代码块包裹。"
            "不要问用户任何问题，直接实现。"
        ),
        "agent_tester": (
            "你必须输出测试代码。"
            "用 ```python 代码块包裹，包含 def test_ 开头的函数。"
        ),
        "agent_devops": (
            "你必须输出部署配置。"
            "用 ```bash 或 ```yaml 或 ```dockerfile 代码块包裹。"
        ),
    }

    instruction = format_instructions.get(agent_id, "请按照标准格式重新生成。")

    return (
        f"你的上一次输出不符合要求：{reason}。"
        f"请严格按照以下格式重新生成：\n{instruction}"
        f"\n\n用户原始需求：{user_text}"
    )
