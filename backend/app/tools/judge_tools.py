"""Concrete JudgeTool implementations wrapping existing evaluation logic."""

import re
import json
from typing import Any

from app.tools.base import JudgeResult


# ============================================================
# Tool 1: InteractionJudgeTool
# Wraps harness_engine.evaluate_interaction_need
# ============================================================

class InteractionJudgeTool:
    """Determines if a user query requires multi-agent debate interaction."""

    name = "interaction_judge"
    description = "判断用户输入是否需要多 Agent 辩论交互"

    async def run(self, input_data: dict, llm_client: Any = None) -> JudgeResult:
        from app.agents.harness_engine import evaluate_interaction_need

        user_input = input_data.get("user_input", "")
        result = await evaluate_interaction_need(user_input, llm_client)

        needs = result.get("needs_interaction", False)
        return JudgeResult(
            decision="needs_interaction" if needs else "direct_answer",
            score=100.0 if needs else 0.0,
            reason=f"{'需要' if needs else '不需要'}辩论交互",
            signals={"needs_interaction": needs},
            raw=result,
        )


# ============================================================
# Tool 2: ComplexityJudgeTool
# Evaluates task complexity on a 0-100 scale
# ============================================================

COMPLEXITY_SYSTEM_PROMPT = """\
你是一个任务复杂度分析器。对用户输入进行复杂度评分。

评分维度（满分 100）：
- 技术深度（0-30）：涉及多少技术领域？是否有架构设计？
- 方案多样性（0-30）：存在多少种可行方案？是否有明显 trade-off？
- 实现难度（0-25）：代码量、边界处理、集成复杂度
- 风险程度（0-15）：出错后果、回滚难度、影响范围

严格且仅输出 JSON：
{"score": 75, "depth": 25, "diversity": 20, "difficulty": 18, "risk": 12, "reason": "一句话理由"}
"""


class ComplexityJudgeTool:
    """Scores task complexity on a 0-100 scale with sub-dimensions."""

    name = "complexity_judge"
    description = "评估任务复杂度（技术深度/方案多样性/实现难度/风险）"

    async def run(self, input_data: dict, llm_client: Any = None) -> JudgeResult:
        user_input = input_data.get("user_input", "")

        if not llm_client:
            return JudgeResult(
                decision="unknown", score=50.0,
                reason="LLM client not available",
                signals={"error": "no_llm_client"},
            )

        try:
            messages = [{"role": "user", "content": user_input}]
            response_text = ""
            async for chunk in llm_client.chat_stream(messages, system=COMPLEXITY_SYSTEM_PROMPT):
                response_text += chunk

            response_text = response_text.strip()
            try:
                result = json.loads(response_text)
            except json.JSONDecodeError:
                match = re.search(r'\{[\s\S]*?"score"\s*:\s*\d+[\s\S]*?\}', response_text)
                if match:
                    result = json.loads(match.group())
                else:
                    raise ValueError(f"Cannot parse JSON: {response_text[:200]}")

            score = max(0, min(100, result.get("score", 50)))
            return JudgeResult(
                decision="complex" if score >= 60 else "simple",
                score=float(score),
                reason=result.get("reason", ""),
                signals={
                    "depth": result.get("depth", 0),
                    "diversity": result.get("diversity", 0),
                    "difficulty": result.get("difficulty", 0),
                    "risk": result.get("risk", 0),
                },
                raw=result,
            )
        except Exception as e:
            return JudgeResult(
                decision="error", score=50.0,
                reason=f"Complexity evaluation failed: {type(e).__name__}: {str(e)[:100]}",
                signals={"error": str(e)[:200]},
            )


# ============================================================
# Tool 3: QualityJudgeTool
# Wraps auto_evaluator.execute_automated_evaluation
# ============================================================

class QualityJudgeTool:
    """Evaluates code quality via static check + LLM scoring."""

    name = "quality_judge"
    description = "评估代码质量（语法检查 + LLM 打分）"

    async def run(self, input_data: dict, llm_client: Any = None) -> JudgeResult:
        from app.agents.auto_evaluator import execute_automated_evaluation

        task = input_data.get("task", "")
        solution = input_data.get("solution", "")

        if not llm_client:
            return JudgeResult(
                decision="unknown", score=50.0,
                reason="LLM client not available",
                signals={"error": "no_llm_client"},
            )

        report = await execute_automated_evaluation(task, solution, llm_client)

        score = report.get("total_score", 50)
        passed = report.get("evaluation_passed", False)

        return JudgeResult(
            decision="pass" if passed else "fail",
            score=float(score),
            reason=report.get("summary", ""),
            signals={
                "logic": report.get("dimensions", {}).get("logic", 0),
                "robustness": report.get("dimensions", {}).get("robustness", 0),
                "architecture": report.get("dimensions", {}).get("architecture", 0),
                "syntax_passed": report.get("static_check", {}).get("passed", True),
                "syntax_error": report.get("static_check", {}).get("error"),
            },
            raw=report,
        )


# ============================================================
# Tool 4: AlignmentJudgeTool
# Checks if a solution aligns with the original requirement
# ============================================================

ALIGNMENT_SYSTEM_PROMPT = """\
你是一个需求对齐度审查器。判断代码方案是否准确实现了用户需求。

评分维度（满分 100）：
- 功能覆盖（0-40）：需求中的核心功能是否都实现了？
- 技术匹配（0-30）：是否使用了用户指定的技术栈/框架？
- 偏离度（0-30）：是否有未经用户同意的重大偏离（如换了框架、改了需求范围）？

严格且仅输出 JSON：
{"score": 85, "coverage": 35, "tech_match": 28, "deviation": 22, "deviation_notes": "偏离说明或无", "reason": "一句话理由"}
"""


class AlignmentJudgeTool:
    """Checks if a solution aligns with the original user requirement."""

    name = "alignment_judge"
    description = "评估方案与需求的对齐度（功能覆盖/技术匹配/偏离度）"

    async def run(self, input_data: dict, llm_client: Any = None) -> JudgeResult:
        task = input_data.get("task", "")
        solution = input_data.get("solution", "")

        if not llm_client:
            return JudgeResult(
                decision="unknown", score=50.0,
                reason="LLM client not available",
                signals={"error": "no_llm_client"},
            )

        try:
            user_prompt = f"## 用户需求\n{task}\n\n## 代码方案\n{solution}"
            messages = [{"role": "user", "content": user_prompt}]
            response_text = ""
            async for chunk in llm_client.chat_stream(messages, system=ALIGNMENT_SYSTEM_PROMPT):
                response_text += chunk

            response_text = response_text.strip()
            try:
                result = json.loads(response_text)
            except json.JSONDecodeError:
                match = re.search(r'\{[\s\S]*?"score"\s*:\s*\d+[\s\S]*?\}', response_text)
                if match:
                    result = json.loads(match.group())
                else:
                    raise ValueError(f"Cannot parse JSON: {response_text[:200]}")

            score = max(0, min(100, result.get("score", 50)))
            return JudgeResult(
                decision="aligned" if score >= 60 else "misaligned",
                score=float(score),
                reason=result.get("reason", ""),
                signals={
                    "coverage": result.get("coverage", 0),
                    "tech_match": result.get("tech_match", 0),
                    "deviation": result.get("deviation", 0),
                    "deviation_notes": result.get("deviation_notes", ""),
                },
                raw=result,
            )
        except Exception as e:
            return JudgeResult(
                decision="error", score=50.0,
                reason=f"Alignment evaluation failed: {type(e).__name__}: {str(e)[:100]}",
                signals={"error": str(e)[:200]},
            )
