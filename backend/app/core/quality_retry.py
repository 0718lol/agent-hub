"""
Quality Retry — 自动反思与重试 (Self-Reflection & Retry) 机制

当 Agent 生成代码后：
  1. 调用 auto_evaluator 进行静态检查 + LLM 打分
  2. 通过（>=60 分）→ 放行，附带质量报告
  3. 未通过 → 将扣分原因作为反馈发回 Agent 重试一次
  4. 重试仍失败 → 强制放行，附带警告，交由人类裁决

本模块只负责"评估 + 重试"逻辑，不修改 WebSocket 广播，
由 main.py 调用后自行处理消息下发。
"""

import asyncio
import re
from typing import Any

from app.agents.auto_evaluator import execute_automated_evaluation
from app.core.websocket import ConnectionManager

# 硬编码最大重试次数
MAX_RETRIES = 1

# 跳过评估的 Agent（PM 和 Builder 不产出用户可执行代码）
SKIP_AGENTS = {"agent_pm", "agent_builder"}

# 交互标签：输出中含这些标签说明 Agent 在向用户提问/澄清，
# 不是在交付代码，不能用代码质量门禁去打分（否则会被判低分触发无意义重试）。
INTERACTIVE_TAGS = ("[ask_user:", "[clarify:", "[options:")

# 匹配 Markdown 围栏代码块（```lang ... ```）
_CODE_BLOCK_RE = re.compile(r"```[\w]*\n.*?```", re.DOTALL)


def _is_interactive_response(text: str) -> bool:
    return any(tag in text for tag in INTERACTIVE_TAGS)


def _has_code_block(text: str) -> bool:
    """判断输出是否真的包含可评估的代码块。无代码块的对话型回复不应走代码质量门禁。"""
    return bool(_CODE_BLOCK_RE.search(text))


async def _evaluate_code_with_sandbox(task: str, output: str, llm_client: Any) -> dict:
    """
    1. 进行静态分析和 LLM 逻辑评审打分。
    2. 将代码放进 Sandbox 安全沙盒实际运行，如果运行报错或超时，强制扣分判定不及格，并返回运行时 Traceback 报错。
    """
    # 静态评估 + LLM 打分
    report = await execute_automated_evaluation(task, output, llm_client)

    from app.agents.auto_evaluator import extract_code_from_text
    from app.core.sandbox import execute_code

    code = await extract_code_from_text(output)
    lang_match = re.search(r'```(\w+)', output)
    language = lang_match.group(1).lower() if lang_match else "python"

    runnable_langs = {"python", "py", "javascript", "js", "typescript", "ts", "shell", "sh", "bash"}
    if language in runnable_langs:
        # 在安全沙盒中真实执行它！
        sandbox_res = await execute_code(code, language=language)

        if sandbox_res.status != "success":
            # 运行失败（有 Runtime 报错或超时）
            penalty = 35
            report["evaluation_passed"] = False
            report["total_score"] = max(0, report["total_score"] - penalty)
            report["sandbox_run"] = {
                "passed": False,
                "status": sandbox_res.status,
                "stderr": sandbox_res.stderr,
                "stdout": sandbox_res.stdout,
                "exit_code": sandbox_res.exit_code,
            }
            err_msg = sandbox_res.stderr.strip() or f"未知运行错误 (exit: {sandbox_res.exit_code})"
            report["summary"] = f"❌ 沙盒真实运行失败 ({sandbox_res.status})！\n运行时错误:\n{err_msg}\n\n" + report.get("summary", "")
        else:
            # 运行成功
            report["sandbox_run"] = {
                "passed": True,
                "status": "success",
                "stdout": sandbox_res.stdout,
                "duration_ms": sandbox_res.duration_ms,
            }
            report["summary"] = f"✅ 沙盒运行成功 ({sandbox_res.duration_ms}ms)！\n" + report.get("summary", "")

    return report


async def evaluate_and_retry(
    conversation_id: str,
    agent,
    task: str,
    raw_output: str,
    llm_client: Any,
    manager: ConnectionManager,
    stop_event: asyncio.Event = None,
    history: list = None,
) -> dict:
    """
    对 Agent 输出执行质量评估，失败则触发反思重试。

    Args:
        conversation_id: 会话 ID
        agent: Agent 实例（需实现 stream_reply 方法）
        task: 用户原始任务描述
        raw_output: Agent 第一次生成的原始输出
        llm_client: LLM 客户端实例
        manager: WebSocket 连接管理器
        stop_event: 停止信号
        history: 对话历史

    Returns:
        {
            "final_output": str,           # 最终输出（可能是原始的或重试后的）
            "evaluation_passed": bool,     # 是否通过质量门禁
            "total_score": int,            # 最终得分
            "retried": bool,               # 是否触发了重试
            "retry_warning": bool,         # 重试后仍失败的警告标记
            "report": dict,                # 完整评估报告
        }
    """
    agent_id = agent.agent_id

    # 跳过不需要评估的 Agent
    if agent_id in SKIP_AGENTS:
        return {
            "final_output": raw_output,
            "evaluation_passed": True,
            "total_score": 100,
            "retried": False,
            "retry_warning": False,
            "report": {},
        }

    # Agent 在向用户提问（ask_user / clarify / options），不是交付代码 →
    # 直接放行，不评估、不重试。
    if _is_interactive_response(raw_output):
        return {
            "final_output": raw_output,
            "evaluation_passed": True,
            "total_score": 100,
            "retried": False,
            "retry_warning": False,
            "report": {"skipped_reason": "interactive_response"},
        }

    # 输出不含代码块（对话型回复、自定义非代码 Agent、问候语等）→
    # 没东西给代码质量门禁评，直接放行。
    if not _has_code_block(raw_output):
        return {
            "final_output": raw_output,
            "evaluation_passed": True,
            "total_score": 100,
            "retried": False,
            "retry_warning": False,
            "report": {"skipped_reason": "no_code_block"},
        }

    # Step 1: 首次评估 (包含沙盒运行检测)
    report = await _evaluate_code_with_sandbox(task, raw_output, llm_client)

    # 广播评估状态
    await manager.broadcast(conversation_id, {
        "type": "quality_report",
        "conversation_id": conversation_id,
        "agent_id": agent_id,
        "report": {
            "evaluation_passed": report["evaluation_passed"],
            "total_score": report["total_score"],
            "dimensions": report["dimensions"],
            "summary": report["summary"],
        },
    })

    # 通过 → 直接放行
    if report["evaluation_passed"]:
        return {
            "final_output": raw_output,
            "evaluation_passed": True,
            "total_score": report["total_score"],
            "retried": False,
            "retry_warning": False,
            "report": report,
        }

    # Step 2: 未通过，触发反思重试
    retry_count = 0
    current_output = raw_output
    current_report = report

    while retry_count < MAX_RETRIES and not current_report["evaluation_passed"]:
        retry_count += 1

        # 广播重试状态
        await manager.broadcast(conversation_id, {
            "type": "message",
            "conversation_id": conversation_id,
            "sender": agent_id,
            "content": {
                "text": f"⚠️ 质量与运行测试未通过（{current_report['total_score']}分），正在自动反思修正...（{retry_count}/{MAX_RETRIES}）"
            },
            "stream": False,
        })

        # 构造反思 prompt：原始任务 + 扣分反馈 (结合编译期 AST 错误与运行期报错)
        feedback_parts = []
        if current_report.get("static_check", {}).get("error"):
            feedback_parts.append(f"静态语法错误 (Syntax Error):\n{current_report['static_check']['error']}")
        if current_report.get("sandbox_run", {}).get("stderr"):
            feedback_parts.append(f"沙盒实际执行报错 (Runtime Error):\n{current_report['sandbox_run']['stderr']}")
        if current_report.get("llm_feedback"):
            feedback_parts.append(f"模型审查意见:\n{current_report['llm_feedback']}")
        if current_report.get("summary"):
            feedback_parts.append(f"综合评语:\n{current_report['summary']}")

        feedback_text = "\n\n".join(feedback_parts)

        retry_prompt = (
            f"你的原始任务是: {task}\n\n"
            f"【🚨 自动化质量测试未通过 — 你的代码只得了 {current_report['total_score']} 分（60分及格）】\n"
            f"测试不通过的原因及运行时错误如下：\n{feedback_text}\n\n"
            f"请深入反思报错根源，修正你的代码，重新输出一份完美的、可直接运行的完整代码方案。"
        )

        # 流式重试生成
        retry_output = ""
        async for chunk in agent.stream_reply(retry_prompt, history=history):
            if stop_event and stop_event.is_set():
                break
            retry_output += chunk
            await manager.broadcast(conversation_id, {
                "type": "message",
                "conversation_id": conversation_id,
                "sender": agent_id,
                "content": {"text": "[自愈反思修正中...] " + retry_output.strip()[:100]},
                "stream": True,
            })

        if not retry_output.strip():
            break

        current_output = retry_output

        # 重试时若 Agent 改为向用户提问，视为合法响应，跳出循环不再评估
        if _is_interactive_response(current_output):
            current_report = {
                "evaluation_passed": True,
                "total_score": 100,
                "dimensions": {},
                "summary": "Retry produced interactive response (ask_user/clarify).",
            }
            break

        # 重新评估 (包含沙盒运行检测)
        current_report = await _evaluate_code_with_sandbox(task, current_output, llm_client)

        # 广播重试后的评估报告
        await manager.broadcast(conversation_id, {
            "type": "quality_report",
            "conversation_id": conversation_id,
            "agent_id": agent_id,
            "report": {
                "evaluation_passed": current_report["evaluation_passed"],
                "total_score": current_report["total_score"],
                "dimensions": current_report["dimensions"],
                "summary": current_report["summary"],
                "retry_round": retry_count,
            },
        })

    # Step 3: 返回最终结果
    retry_warning = not current_report["evaluation_passed"]

    if retry_warning:
        # 重试仍失败，广播警告
        await manager.broadcast(conversation_id, {
            "type": "message",
            "conversation_id": conversation_id,
            "sender": agent_id,
            "content": {
                "text": (
                    f"⚠️ 自动修复警示：该方案经过自动反思重试后，运行测试仍存在报错（{current_report['total_score']}分）。"
                    f"以下代码已强制放行，交由人类决策审查。"
                )
            },
            "stream": False,
        })

    return {
        "final_output": current_output,
        "evaluation_passed": current_report["evaluation_passed"],
        "total_score": current_report["total_score"],
        "retried": retry_count > 0,
        "retry_warning": retry_warning,
        "report": current_report,
    }
