"""Compatibility shim for the retired quality retry gate."""

from typing import Any


async def evaluate_and_retry(
    conversation_id: str,
    agent,
    task: str,
    raw_output: str,
    llm_client: Any = None,
    manager: Any = None,
    stop_event=None,
    history: list | None = None,
) -> dict:
    """Keep the call site stable while bypassing quality gate retries."""
    return {
        "final_output": raw_output,
        "evaluation_passed": True,
        "total_score": None,
        "retried": False,
        "retry_warning": False,
        "report": {"skipped_reason": "disabled"},
    }
