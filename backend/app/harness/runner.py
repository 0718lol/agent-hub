"""Runner — executes test suites against judge tools."""

import json
import asyncio
from pathlib import Path
from typing import Any

from app.tools.base import JudgeResult
from app.tools.judge_tools import (
    InteractionJudgeTool,
    ComplexityJudgeTool,
    QualityJudgeTool,
    AlignmentJudgeTool,
    UserInteractionJudgeTool,
)
from app.harness.evaluator import evaluate_result, EvalReport

# Registry of available tools
TOOL_REGISTRY = {
    "interaction_judge": InteractionJudgeTool,
    "complexity_judge": ComplexityJudgeTool,
    "quality_judge": QualityJudgeTool,
    "alignment_judge": AlignmentJudgeTool,
    "user_interaction_judge": UserInteractionJudgeTool,
}

SAMPLES_DIR = Path(__file__).parent / "samples"


def load_suite(name: str) -> list[dict]:
    """Load a test suite JSON file by name."""
    path = SAMPLES_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Test suite not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_suites() -> list[str]:
    """List all available test suite names."""
    if not SAMPLES_DIR.exists():
        return []
    return [f.stem for f in SAMPLES_DIR.glob("*.json")]


class HarnessRunner:
    """Runs test suites and collects evaluation reports."""

    def __init__(self, llm_client: Any = None):
        self.llm_client = llm_client

    async def run_case(self, tool_name: str, case: dict) -> EvalReport:
        """Run a single test case against a tool."""
        tool_cls = TOOL_REGISTRY.get(tool_name)
        if not tool_cls:
            raise ValueError(f"Unknown tool: {tool_name}. Available: {list(TOOL_REGISTRY.keys())}")

        tool = tool_cls()

        # Build input_data from case
        input_data = case.copy()

        # Run the tool
        result = await tool.run(input_data, llm_client=self.llm_client)

        # Evaluate the result
        input_summary = case.get("description", case.get("user_input", case.get("task", ""))[:60])
        report = evaluate_result(
            tool_name=tool_name,
            input_summary=input_summary,
            result=result,
            expected_decision=case.get("expected_decision", ""),
            expected_score_range=tuple(case.get("expected_score_range", [0, 100])),
            pass_threshold=case.get("pass_threshold", 60.0),
        )

        return report

    async def run_suite(self, suite_name: str) -> list[EvalReport]:
        """Run all cases in a test suite."""
        cases = load_suite(suite_name)
        reports = []
        for case in cases:
            tool_name = case.get("tool", suite_name)
            try:
                report = await self.run_case(tool_name, case)
                reports.append(report)
            except Exception as e:
                reports.append(EvalReport(
                    tool_name=tool_name,
                    input_summary=case.get("description", "")[:60],
                    total_score=0.0,
                    passed=False,
                    signals={"error": str(e)[:200]},
                ))
        return reports

    async def run_all(self) -> dict[str, list[EvalReport]]:
        """Run all available test suites."""
        suites = list_suites()
        results = {}
        for suite_name in suites:
            results[suite_name] = await self.run_suite(suite_name)
        return results
