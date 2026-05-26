"""
Auto Evaluator — Agent 生成代码的自动化测试与量化打分模块

功能：
  1. extract_code_from_text    — 从 Markdown 中提取代码块
  2. static_syntax_check       — Python 静态语法检查（ast.parse）
  3. llm_as_a_judge_scoring    — LLM 深度打分（逻辑/健壮性/架构三维度）
  4. execute_automated_evaluation — 编排函数，串联以上步骤生成综合报告
"""

import re
import ast
import json
import asyncio
from typing import Any


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
        异常时返回默认中位分
    """
    default_result = {
        "total_score": 50,
        "dimensions": {"logic": 20, "robustness": 15, "architecture": 15},
        "feedback": "LLM 评分失败，返回默认中位分",
    }

    try:
        user_prompt = (
            f"## 用户任务\n{task}\n\n"
            f"## 待审查代码方案\n{solution}"
        )
        messages = [{"role": "user", "content": user_prompt}]

        # 流式收集完整响应
        response_text = ""
        async for chunk in llm_client.chat_stream(messages, system=JUDGE_SYSTEM_PROMPT):
            response_text += chunk

        response_text = response_text.strip()

        # 解析 JSON
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # 正则容错提取
            json_match = re.search(
                r'\{[\s\S]*?"total_score"\s*:\s*\d+[\s\S]*?\}',
                response_text
            )
            if json_match:
                result = json.loads(json_match.group())
            else:
                raise ValueError(f"无法从响应中提取评分 JSON: {response_text[:200]}")

        # 校验必要字段
        if "total_score" not in result or "dimensions" not in result:
            raise ValueError(f"返回缺少必要字段: {result}")

        # 确保各维度分值在合理范围内
        dims = result["dimensions"]
        dims["logic"] = max(0, min(40, dims.get("logic", 0)))
        dims["robustness"] = max(0, min(30, dims.get("robustness", 0)))
        dims["architecture"] = max(0, min(30, dims.get("architecture", 0)))
        result["total_score"] = max(0, min(100, result.get("total_score", 0)))

        return result

    except Exception as e:
        print(f"[AutoEvaluator] LLM 评分异常: {type(e).__name__}: {str(e)[:100]}")
        default_result["feedback"] = f"LLM 评分异常: {str(e)[:100]}"
        return default_result


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
            "total_score": int,              # 最终总分
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

    # Step 4: 合并评分（静态检查扣分 + LLM 打分）
    base_score = llm_result["total_score"]
    penalty = syntax_result["penalty"]
    final_score = max(0, base_score - penalty)

    # 生成综合评语
    summary_parts = []
    if not syntax_result["passed"]:
        summary_parts.append(f"语法检查未通过: {syntax_result['error']}")
    if llm_result.get("feedback"):
        summary_parts.append(f"LLM 审查: {llm_result['feedback']}")

    summary = " | ".join(summary_parts) if summary_parts else "代码质量良好"

    return {
        "evaluation_passed": final_score >= 60,
        "total_score": final_score,
        "dimensions": llm_result["dimensions"],
        "static_check": {
            "passed": syntax_result["passed"],
            "error": syntax_result["error"],
            "penalty": syntax_result["penalty"],
        },
        "llm_feedback": llm_result.get("feedback", ""),
        "summary": summary,
    }
