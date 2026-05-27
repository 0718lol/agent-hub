"""
Harness WebSocket Handler — 辩论沙盒的 WebSocket 集成层

职责：
  1. 在用户消息分发前拦截，调用 harness_engine 评估
  2. 辩论结果直接通过 WebSocket 下发给前端
  3. 处理前端用户发回的裁决指令（accept_a / accept_b / reject_all）

main.py 只需调用本模块的两个函数，不改动原有逻辑。
"""

import json
from typing import Any

from app.agents.harness_engine import evaluate_interaction_need, run_debate_arena, format_debate_response
from app.core.websocket import ConnectionManager
from app.core.database import save_message


async def try_intercept_with_harness(
    conversation_id: str,
    user_text: str,
    llm_client: Any,
    manager: ConnectionManager,
) -> bool:
    """
    尝试用 Harness 拦截用户消息。

    如果判定为复杂任务，执行辩论并将结果下发给前端，返回 True。
    如果判定为简单任务，返回 False，由 main.py 继续原有流程。

    Args:
        conversation_id: 当前会话 ID
        user_text: 用户输入文本
        llm_client: LLM 客户端实例
        manager: WebSocket 连接管理器

    Returns:
        True = 已拦截（辩论结果已下发），False = 放行（继续原有逻辑）
    """
    try:
        # Step 1: 快速判断是否需要辩论（关键词匹配 + LLM 判断）
        evaluation = await evaluate_interaction_need(user_text, llm_client)

        if not evaluation["needs_interaction"]:
            return False

        # Step 2: 通知前端辩论已启动
        await manager.broadcast(conversation_id, {
            "type": "message",
            "conversation_id": conversation_id,
            "sender": "harness_engine",
            "content": {"text": "🎭 检测到复杂任务，启动多 Agent 辩论沙盒（Proposer vs Reviewer）..."},
            "stream": False,
        })

        # Step 3: 执行辩论沙盒
        arena_result = await run_debate_arena(user_text, llm_client)

        # Step 4: 打包结果
        result = format_debate_response(arena_result)
        result["type"] = "harness_debate_result"
        result["conversation_id"] = conversation_id

        # Step 5: 保存辩论结果到数据库
        save_message(
            conversation_id,
            "harness_engine",
            {"text": json.dumps(result, ensure_ascii=False)},
            streaming=False,
        )

        # Step 6: 通过 WebSocket 下发辩论结果
        await manager.broadcast(conversation_id, result)

        return True

    except Exception as e:
        # Harness 异常不影响主流程，降级为普通处理
        import traceback
        print(f"[Harness] 拦截异常，降级放行: {type(e).__name__}: {str(e)[:200]}")
        traceback.print_exc()
        return False


async def handle_verdict(
    conversation_id: str,
    msg: dict,
    manager: ConnectionManager,
) -> bool:
    """
    处理前端用户发回的裁决指令。

    消息格式：
    {
        "type": "harness_verdict",
        "action": "accept_a" | "accept_b" | "reject_all",
        "content": "采纳激进派方案"  // 可选，用户补充说明
    }

    Returns:
        True = 已处理，False = 不是裁决消息，交给后续逻辑
    """
    if msg.get("type") != "harness_verdict":
        return False

    action = msg.get("action", "")
    content = msg.get("content", "")
    valid_actions = {"accept_a", "accept_b", "reject_all"}

    if action not in valid_actions:
        return False

    # 构造裁决上下文消息
    action_labels = {
        "accept_a": "采纳激进派 (Proposer) 方案",
        "accept_b": "采纳审查派 (Reviewer) 方案",
        "reject_all": "拒绝所有方案，重新讨论",
    }

    verdict_text = f"[Harness 裁决] {action_labels.get(action, action)}"
    if content:
        verdict_text += f"\n用户说明：{content}"

    # 保存裁决到数据库
    save_message(
        conversation_id,
        "user",
        {"text": verdict_text},
        streaming=False,
    )

    # 广播裁决结果给所有连接的客户端
    await manager.broadcast(conversation_id, {
        "type": "harness_verdict",
        "conversation_id": conversation_id,
        "action": action,
        "verdict_text": verdict_text,
        "stream": False,
    })

    return True
