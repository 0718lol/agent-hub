"""Code review service - orchestrates rule engine + LLM review + self-healing.

Provides:
- review_code(): hybrid review (rule engine + optional LLM)
- self_healing_review(): auto-fix high-severity issues with retry
"""
import json
import logging
import re

from app.core.code_review_rules import rule_based_review

logger = logging.getLogger("code_review_service")


def parse_llm_review(text: str) -> list[dict]:
    """Extract structured issues from LLM output."""
    try:
        match = re.search(r'\{[\s\S]*"issues"[\s\S]*\}', text)
        if match:
            data = json.loads(match.group())
            return data.get("issues", [])
    except (json.JSONDecodeError, KeyError):
        pass
    return []


def calculate_score(issues: list[dict]) -> dict[str, float]:
    """Calculate quality scores based on issues found."""
    base = 10.0
    for issue in issues:
        severity = issue.get("severity", "low")
        if severity == "high":
            base -= 2.0
        elif severity == "medium":
            base -= 1.0
        elif severity == "low":
            base -= 0.5
    return {"overall": max(0.0, base)}


async def review_code(code: str, agent=None) -> dict:
    """Hybrid review: rule engine + optional LLM agent.
    
    Args:
        code: Source code to review
        agent: Optional CodeReviewerAgent for LLM-based review
        
    Returns:
        dict with 'issues', 'score', 'rule_count', 'llm_count'
    """
    # Layer 1: Rule engine (deterministic, always runs)
    rule_issues = rule_based_review(code)

    # Layer 2: LLM review (optional, for deeper analysis)
    llm_issues = []
    if agent:
        try:
            prompt = (
                "审查以下代码，输出 JSON 格式的问题列表。"
                "只输出 JSON，不要解释。\n\n```\n" + code[:3000] + "\n```"
            )
            result = ""
            async for chunk in agent.stream_reply(prompt):
                result += chunk
            llm_issues = parse_llm_review(result)
        except Exception as e:
            logger.warning(f"LLM review failed: {e}")

    all_issues = rule_issues + llm_issues
    score = calculate_score(all_issues)

    return {
        "issues": all_issues,
        "score": score,
        "rule_count": len(rule_issues),
        "llm_count": len(llm_issues),
    }


async def self_healing_review(code: str, agent, max_retries: int = 1) -> dict:
    """Self-healing review: detect issues, auto-fix, re-review.
    
    Args:
        code: Source code to review and fix
        agent: CodeReviewerAgent for LLM-based review and fixing
        max_retries: Maximum fix attempts (default: 1)
        
    Returns:
        dict with 'status', 'code', 'attempts', 'review'
    """
    current_code = code

    for attempt in range(max_retries + 1):
        # Review current code
        review = await review_code(current_code, agent)

        # No issues found - pass
        if not review["issues"]:
            return {
                "status": "passed",
                "code": current_code,
                "attempts": attempt + 1,
                "review": review,
            }

        # Only low-severity issues - pass with warnings
        high_issues = [i for i in review["issues"] if i.get("severity") == "high"]
        if not high_issues:
            return {
                "status": "passed_with_warnings",
                "code": current_code,
                "attempts": attempt + 1,
                "review": review,
            }

        # High-severity issues found - attempt fix
        if attempt < max_retries:
            fix_prompt = (
                "修复以下代码中的高严重级别问题。只输出修复后的完整代码，不要解释。\n\n"
                f"代码：\n```\n{current_code[:3000]}\n```\n\n"
                f"问题：\n{json.dumps(high_issues, ensure_ascii=False)}"
            )
            fixed = ""
            async for chunk in agent.stream_reply(fix_prompt):
                fixed += chunk
            if fixed.strip():
                # Extract code block if present
                code_match = re.search(r'```(?:\w+)?\n(.*?)```', fixed, re.DOTALL)
                if code_match:
                    current_code = code_match.group(1).strip()
                else:
                    current_code = fixed.strip()

    return {
        "status": "max_retries",
        "code": current_code,
        "attempts": max_retries + 1,
        "review": review,
    }
