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


# ============================================================
# Tool 5: UserInteractionJudgeTool
# Interactive choice tool (Yes/No/Else or specific options)
# ============================================================

_pending_interactions: dict[str, Any] = {}


class UserInteractionJudgeTool:
    """像 Claude Code 一样交互式询问用户哪种方案合适，支持 Yes/No/Else"""

    name = "user_interaction_judge"
    description = "人工交互评测工具，提示用户进行方案选择或反馈"

    async def run(self, input_data: dict, llm_client: Any = None) -> JudgeResult:
        import asyncio
        from app.core.websocket import manager

        question = input_data.get("question", "请问哪种方案合适？")
        options_raw = input_data.get("options", ["*Yes::接受此方案", "No::拒绝此方案", "Else::自定义输入其他反馈"])
        conversation_id = input_data.get("conversation_id")

        # 格式化选项 (处理 * 推荐标记和 :: 描述)
        # 例如: ["*Yes::描述", "No::描述"]
        parsed_options = []
        for opt in options_raw:
            label_part = opt
            desc_part = ""
            if "::" in opt:
                label_part, desc_part = opt.split("::", 1)
            
            recommended = False
            label = label_part.strip()
            if label.startswith("*"):
                recommended = True
                label = label[1:].strip()
            
            parsed_options.append({
                "label": label,
                "description": desc_part.strip(),
                "recommended": recommended
            })

        # CLI / Terminal 模式 (如果没有活跃连接或者没有 conversation_id)
        is_cli = not conversation_id or not hasattr(manager, "active_connections") or conversation_id not in manager.active_connections
        
        if is_cli:
            # 打印类似 claude code 风格的提示
            print("\n" + "="*50)
            print(f"[?] \033[1;35m[用户交互确认]\033[0m {question}")
            print("-"*50)
            for i, opt in enumerate(parsed_options, 1):
                rec_str = " \033[1;32m(Recommended)\033[0m" if opt["recommended"] else ""
                desc_str = f" - {opt['description']}" if opt["description"] else ""
                print(f"  {i}. \033[1m{opt['label']}\033[0m{rec_str}{desc_str}")
            print(f"  {len(parsed_options)+1}. \033[1mElse / Other\033[0m - 输入自定义回答")
            print("="*50)

            # 获取用户输入
            def get_cli_input():
                try:
                    while True:
                        ans = input(f"请输入选择 (1-{len(parsed_options)+1}): ").strip()
                        if not ans:
                            # 默认选择第一个推荐项或第一个选项
                            rec_idx = next((idx for idx, o in enumerate(parsed_options) if o["recommended"]), 0)
                            return parsed_options[rec_idx]["label"]
                        try:
                            idx = int(ans)
                            if 1 <= idx <= len(parsed_options):
                                return parsed_options[idx - 1]["label"]
                            elif idx == len(parsed_options) + 1:
                                return input("请输入你的自定义回答 / 反馈: ").strip()
                        except ValueError:
                            # 如果直接输入文字，则作为自定义回答
                            return ans
                except EOFError:
                    # Headless or non-interactive environment fallback to recommended option
                    rec_idx = next((idx for idx, o in enumerate(parsed_options) if o["recommended"]), 0)
                    return parsed_options[rec_idx]["label"]

            # 在线程池中异步等待输入，避免阻塞事件循环
            loop = asyncio.get_running_loop()
            answer = await loop.run_in_executor(None, get_cli_input)
        
        # WebSocket 模式
        else:
            # 构造前端 [ask_user:...] 标记格式
            # 格式: [ask_user: Question | Option1::Description1 | *Option2::Description2]
            opt_segments = []
            for opt in parsed_options:
                prefix = "*" if opt["recommended"] else ""
                desc = f"::{opt['description']}" if opt["description"] else ""
                opt_segments.append(f"{prefix}{opt['label']}{desc}")
            
            tag = f"[ask_user: {question} | {' | '.join(opt_segments)}]"

            # 广播给前端
            await manager.broadcast(conversation_id, {
                "type": "message",
                "conversation_id": conversation_id,
                "sender": "user_interaction_judge",
                "content": {"text": tag},
                "stream": False,
            })

            # 同时派发给多渠道异步协同网关 (Slack/Telegram)
            try:
                from app.services.webhook_gateway import webhook_gateway
                # Format to run non-blockingly or await
                await webhook_gateway.send_hil_notification(conversation_id, question, parsed_options)
            except Exception as ex:
                import logging
                logging.getLogger("user_interaction_judge").error(f"Failed to dispatch HIL Webhook notification: {ex}")

            # 注册 Future 挂起等待
            fut = asyncio.get_running_loop().create_future()
            _pending_interactions[conversation_id] = fut
            
            try:
                # 等待用户回复（通过 websocket 触发的 set_result）
                answer = await fut
            finally:
                _pending_interactions.pop(conversation_id, None)

        # 整理输出决策和评分
        decision = answer.strip()
        score = 100.0 if decision.lower() in ("yes", "y", "pass", "approve") or any(decision.lower() == o["label"].lower() and o["recommended"] for o in parsed_options) else 50.0
        
        return JudgeResult(
            decision=decision,
            score=score,
            reason=f"用户确认回答: {answer}",
            signals={"answer": answer},
            raw={"options": parsed_options, "user_answer": answer}
        )

