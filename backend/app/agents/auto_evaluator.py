"""
Auto Evaluator — Agent 生成代码的自动化测试与量化打分模块

功能：
  1. extract_code_from_text    — 从 Markdown 中提取代码块
  2. static_syntax_check       — Python 静态语法检查（ast.parse）
  3. llm_as_a_judge_scoring    — LLM 深度打分（逻辑/健壮性/架构三维度）
  4. execute_automated_evaluation — 编排函数，串联以上步骤生成综合报告
"""

import ast
import json
import re
from typing import Any


def _parse_scoring_json(response_text: str) -> dict:
    """Extract a complete JSON object containing the scoring contract."""
    text = response_text.strip()
    if not text:
        raise ValueError("评分模型返回空内容")

    try:
        candidates = [json.loads(text)]
    except json.JSONDecodeError:
        candidates = []
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", text):
            try:
                candidate, _ = decoder.raw_decode(text[match.start():])
            except json.JSONDecodeError:
                continue
            candidates.append(candidate)

    for candidate in candidates:
        if isinstance(candidate, dict) and {
            "total_score", "dimensions"
        }.issubset(candidate):
            return candidate

    raise ValueError(f"无法从响应中提取评分 JSON: {text[:200]}")


def _normalize_scoring_result(result: dict) -> dict:
    dims = result.get("dimensions")
    if not isinstance(dims, dict):
        raise ValueError("评分 dimensions 必须是 JSON 对象")

    limits = {"logic": 40, "robustness": 30, "architecture": 30}
    normalized_dims = {}
    for name, limit in limits.items():
        value = dims.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"评分维度 {name} 必须是数字")
        normalized_dims[name] = max(0, min(limit, int(value)))

    total_score = result.get("total_score")
    if isinstance(total_score, bool) or not isinstance(total_score, (int, float)):
        raise ValueError("total_score 必须是数字")

    feedback = result.get("feedback", "")
    if not isinstance(feedback, str):
        feedback = str(feedback)

    return {
        "status": "ok",
        "total_score": max(0, min(100, int(total_score))),
        "dimensions": normalized_dims,
        "feedback": feedback,
        "error": None,
    }

# ============================================================
# 任务 1：代码提取
# ============================================================

async def extract_code_from_text(text: str) -> str:
    """
    从 Markdown 文本中提取第一个代码块的内容。

    匹配 ```language ... ``` 格式。如果没有代码块，返回原文。

    Args:
        text: 包含 Markdown 格式的文本

    Returns:
        提取到的代码字符串，或原文
    """
    match = re.search(r'```[\w]*\n(.*?)```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


# ============================================================
# 任务 2：静态语法检查
# ============================================================

async def static_syntax_check(code: str, language: str = "python") -> dict:
    """
    对代码进行静态语法检查。

    目前仅支持 Python（使用 ast.parse）。
    其他语言直接跳过，返回通过。

    Args:
        code: 待检查的代码字符串
        language: 代码语言，默认 "python"

    Returns:
        {
            "passed": bool,
            "error": str | None,
            "penalty": int  # 扣分分值，0 或 20
        }
    """
    if language.lower() != "python":
        # 非 Python 语言暂不检查，直接通过
        return {"passed": True, "error": None, "penalty": 0}

    try:
        ast.parse(code)
        return {"passed": True, "error": None, "penalty": 0}
    except SyntaxError as e:
        error_detail = f"语法错误 (第 {e.lineno} 行): {e.msg}"
        return {"passed": False, "error": error_detail, "penalty": 20}


# ============================================================
# 任务 3：LLM 深度打分
# ============================================================

JUDGE_SYSTEM_PROMPT = """\
你是一个无情的代码审查机器。你的唯一职责是对代码方案进行严苛、客观的量化打分。

评分维度（满分 100 分）：
1. 逻辑正确性（40 分）：代码是否能正确实现需求描述的功能？核心算法和业务逻辑是否无误？
2. 代码健壮性与边界处理（30 分）：是否有异常处理？是否考虑了边界条件（空值、极端输入、并发）？是否有安全隐患？
3. 架构合理性与性能（30 分）：代码结构是否清晰？是否有明显的性能瓶颈？是否遵循最佳实践？

你必须严格且仅输出以下 JSON 格式，不要输出任何其他内容：
{
  "total_score": 85,
  "dimensions": {
    "logic": 35,
    "robustness": 25,
    "architecture": 25
  },
  "feedback": "扣分原因及具体修改建议"
}

评分标准：
- 90-100 分：生产级代码，几乎无改进空间
- 70-89 分：可用但有改进空间
- 50-69 分：存在明显问题，需要修改
- 0-49 分：严重缺陷，不建议使用
"""


async def llm_as_a_judge_scoring(task: str, solution: str, llm_client: Any) -> dict:
    """
    使用 LLM 对代码方案进行深度打分。

    Args:
        task: 用户原始任务描述
        solution: Agent 生成的代码方案
        llm_client: LLM 客户端实例

    Returns:
        {
            "total_score": int,
            "dimensions": {"logic": int, "robustness": int, "architecture": int},
            "feedback": str
        }
        异常时明确返回 status=error，不伪造质量分。
    """
    try:
        user_prompt = (
            f"## 用户任务\n{task}\n\n"
            f"## 待审查代码方案\n{solution}"
        )
        messages = [{"role": "user", "content": user_prompt}]

        # 流式收集完整响应
        response_text = ""
        async for chunk in llm_client.chat_stream(
            messages,
            system=JUDGE_SYSTEM_PROMPT,
            enabled_tools=[],
            response_format={"type": "json_object"},
        ):
            response_text += chunk

        return _normalize_scoring_result(_parse_scoring_json(response_text))

    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:160]}"
        print(f"[AutoEvaluator] LLM 评分异常: {error}")
        return {
            "status": "error",
            "total_score": None,
            "dimensions": {},
            "feedback": "质量评分服务暂不可用，未将其计为代码失败",
            "error": error,
        }


# ============================================================
# 任务 4：主编排函数
# ============================================================

async def execute_automated_evaluation(
    task: str,
    raw_output: str,
    llm_client: Any,
) -> dict:
    """
    自动化评估编排：提取代码 → 静态检查 → LLM 打分 → 合并报告。

    Args:
        task: 用户原始任务描述
        raw_output: Agent 生成的原始输出（含 Markdown）
        llm_client: LLM 客户端实例

    Returns:
        {
            "evaluation_passed": bool,       # 总分 >= 60 为通过
            "total_score": int | None,       # 评审不可用时不伪造分数
            "dimensions": {"logic": ..., "robustness": ..., "architecture": ...},
            "static_check": {"passed": bool, "error": str|None, "penalty": int},
            "llm_feedback": str,
            "summary": str                   # 综合评语
        }
    """
    # Step 1: 提取代码
    code = await extract_code_from_text(raw_output)

    # Step 2: 静态语法检查
    # 自动检测语言（从 Markdown 代码块标记中提取）
    lang_match = re.search(r'```(\w+)', raw_output)
    language = lang_match.group(1).lower() if lang_match else "python"

    syntax_result = await static_syntax_check(code, language)

    # Step 3: LLM 深度打分
    llm_result = await llm_as_a_judge_scoring(task, raw_output, llm_client)

    # Step 4: 合并评分。评审服务异常时只依据确定性的静态检查放行或拦截。
    evaluator_available = llm_result["status"] == "ok"
    base_score = llm_result["total_score"]
    penalty = syntax_result["penalty"]
    final_score = max(0, base_score - penalty) if evaluator_available else None

    # 生成综合评语
    summary_parts = []
    if not syntax_result["passed"]:
        summary_parts.append(f"语法检查未通过: {syntax_result['error']}")
    if evaluator_available and llm_result.get("feedback"):
        summary_parts.append(f"LLM 审查: {llm_result['feedback']}")
    elif not evaluator_available:
        summary_parts.append("质量评分服务暂不可用；未发现的代码问题不会据此判定")

    summary = " | ".join(summary_parts) if summary_parts else "代码质量良好"

    return {
        "evaluation_passed": syntax_result["passed"] and (
            not evaluator_available or final_score >= 60
        ),
        "total_score": final_score,
        "dimensions": llm_result["dimensions"],
        "evaluator_status": llm_result["status"],
        "evaluator_error": llm_result.get("error"),
        "static_check": {
            "passed": syntax_result["passed"],
            "error": syntax_result["error"],
            "penalty": syntax_result["penalty"],
        },
        "llm_feedback": llm_result.get("feedback", ""),
        "summary": summary,
    }
