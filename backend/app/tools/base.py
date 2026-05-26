"""JudgeTool protocol — unified interface for all judgment tools."""

from dataclasses import dataclass, field
from typing import Protocol, Any


@dataclass
class JudgeResult:
    """Standard result from any JudgeTool."""
    decision: str                     # e.g. "needs_interaction", "pass", "fail"
    score: float = 0.0                # 0-100
    reason: str = ""                  # human-readable explanation
    signals: dict = field(default_factory=dict)   # structured signals for evaluator
    raw: Any = None                   # raw LLM response or internal data


class JudgeTool(Protocol):
    """Protocol that all judge tools must implement."""

    name: str
    description: str

    async def run(self, input_data: dict, llm_client: Any = None) -> JudgeResult:
        """Execute the judge tool.

        Args:
            input_data: tool-specific input dict
            llm_client: optional LLM client for tools that need LLM

        Returns:
            JudgeResult with decision, score, reason, signals
        """
        ...
