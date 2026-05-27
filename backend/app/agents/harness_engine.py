"""
Harness Engine — 人类在环多 Agent 辩论评估沙盒

三段式工作流：
  1. evaluate_interaction_need  — 意图拦截，判断是否需要辩论
  2. run_debate_arena           — 辩论沙盒，Proposer vs Reviewer 多轮对抗
  3. format_debate_response     — 结果打包，按前端协议输出 JSON

依赖：llm_client（统一 LLM 调用层）
"""

import json
import asyncio
from typing import Any


# ============================================================
# Prompt 模板
# ============================================================

EVALUATOR_SYSTEM_PROMPT = """\
你是一个任务复杂度评估器。你的唯一职责是判断用户输入是否属于"复杂任务"。

判断标准：
- 复杂任务 = 架构设计、技术选型、核心代码实现、存在多种可行方案的工程问题
- 简单任务 = 日常问候、简单问答、闲聊、纯信息查询

你必须严格且仅输出以下 JSON 格式，不要输出任何其他内容：
{"needs_interaction": true}

或者：
{"needs_interaction": false}

示例：
用户："你好" -> {"needs_interaction": false}
用户："帮我实现一个分布式消息队列" -> {"needs_interaction": true}
用户："用 React 还是 Vue 做商城" -> {"needs_interaction": true}
用户："今天天气怎么样" -> {"needs_interaction": false}
"""

PROPOSER_SYSTEM_PROMPT = """\
你是一个激进派极客工程师（Proposer）。你的风格：
- 拥抱新技术，追求极致性能和优雅抽象
- 代码大胆前卫，敢于使用最新特性
- 你相信"能用 10 行解决的问题绝不写 20 行"
- 你倾向于选择最前沿的方案，哪怕存在一定风险

你的任务：针对用户的需求，给出你认为最优的、最大胆的代码方案。
输出要求：
1. 先用 1-2 句话概括你的方案思路
2. 然后给出完整的代码实现
3. 代码必须用 ```language 代码块包裹
"""

REVIEWER_SYSTEM_PROMPT = """\
你是一个严苛的保守派架构师（Reviewer）。你的风格：
- 稳定性压倒一切，宁可冗余也不能有隐患
- 对代码的健壮性、可维护性、边界处理有极致追求
- 你专门审查别人代码中的激进设计，指出潜在风险
- 你相信"线上跑得稳的代码才是好代码"

你的任务：
1. 仔细审查 Proposer 的代码，逐条指出稳定性缺陷和潜在风险
2. 给出你自己的、截然不同的稳妥替代方案
3. 你的代码必须用 ```language 代码块包裹
"""

PROPOSER_REBUTTAL_PROMPT = """\
Reviewer 已经对你的代码提出了质疑和备选方案。
现在请你：
1. 逐条反驳 Reviewer 的意见（指出他误解的地方或过度保守的地方）
2. 吸收 Reviewer 意见中合理的部分，修正你的代码
3. 给出修正后的完整代码，用 ```language 代码块包裹

记住：你仍然要坚持你方案的核心优势，但要在细节上更加严谨。
"""

MAX_DEBATE_TURNS = 1  # 固定轮次，防死循环（每轮2次LLM调用）

# 明确的对比/选型关键词，命中即直接触发辩论，不依赖 LLM 判断
DEBATE_KEYWORDS = [
    "还是", "哪个好", "选什么", "对比", "比较", "vs", "VS",
    "应该用", "推荐用", "优缺点", "利弊", "trade-off",
    "选型", "方案对比", "哪种", "孰优孰劣",
]


# ============================================================
# 任务 1：意图拦截
# ============================================================

async def evaluate_interaction_need(user_input: str, llm_client: Any) -> dict:
    """
    分析用户输入，判断是否为复杂任务。

    优先用关键词兜底：如果包含明确的对比/选型关键词，直接触发辩论。
    否则调用 LLM 判断。

    Args:
        user_input: 用户原始输入文本
        llm_client: 统一 LLM 客户端实例（需实现 chat_stream 方法）

    Returns:
        {"needs_interaction": bool}
        异常时默认返回 {"needs_interaction": False}，保证主流程不阻塞
    """
    # ---- 关键词兜底：命中即触发 ----
    msg_lower = user_input.lower()
    for kw in DEBATE_KEYWORDS:
        if kw in msg_lower:
            return {"needs_interaction": True}

    try:
        # ---- LLM 判断（关键词未命中时的后备） ----
        messages = [{"role": "user", "content": user_input}]

        # 调用 LLM 进行判断（流式收集完整响应）
        response_text = ""
        async for chunk in llm_client.chat_stream(messages, system=EVALUATOR_SYSTEM_PROMPT):
            response_text += chunk

        # 清理响应，提取 JSON
        response_text = response_text.strip()

        # 尝试直接解析
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # 尝试从响应中提取 JSON 子串
            import re
            json_match = re.search(r'\{[^}]*"needs_interaction"\s*:\s*(true|false)[^}]*\}',
                                   response_text, re.IGNORECASE)
            if json_match:
                result = json.loads(json_match.group())
            else:
                raise ValueError(f"无法从响应中提取 JSON: {response_text[:200]}")

        # 校验返回格式
        if "needs_interaction" not in result:
            raise ValueError(f"返回缺少 needs_interaction 字段: {result}")

        return {"needs_interaction": bool(result["needs_interaction"])}

    except Exception as e:
        # 任何异常（超时、解析失败、网络错误）都默认放行
        print(f"[Harness] evaluate_interaction_need 异常，放行: {type(e).__name__}: {str(e)[:100]}")
        return {"needs_interaction": False}


# ============================================================
# 任务 2：辩论沙盒
# ============================================================

def _truncate(text: str, max_len: int = 150) -> str:
    """截取前 max_len 个字符，用于辩论日志摘要。"""
    text = text.strip()
    return text[:max_len] + "..." if len(text) > max_len else text


def _build_proposer_task(task: str, reviewer_feedback: str = "") -> str:
    """构造 Proposer 的 prompt。"""
    if reviewer_feedback:
        return (
            f"用户需求：{task}\n\n"
            f"Reviewer 的审查意见：\n{reviewer_feedback}\n\n"
            f"{PROPOSER_REBUTTAL_PROMPT}"
        )
    return f"用户需求：{task}"


def _build_reviewer_task(task: str, proposer_code: str) -> str:
    """构造 Reviewer 的 prompt。"""
    return (
        f"用户需求：{task}\n\n"
        f"Proposer 的代码方案：\n{proposer_code}\n\n"
        f"请审查以上代码并给出你的备选方案。"
    )


async def run_debate_arena(task: str, llm_client: Any) -> dict:
    """
    辩论沙盒：Proposer vs Reviewer 多轮对抗。

    Args:
        task: 用户原始任务描述
        llm_client: 统一 LLM 客户端实例

    Returns:
        {
            "debate_logs": { "round_1": {...}, "round_2": {...} },
            "final_proposer_output": str,   # Proposer 最终完整输出
            "final_reviewer_output": str,   # Reviewer 最终完整输出
        }
    """
    debate_logs: dict[str, dict[str, str]] = {}
    proposer_output = ""
    reviewer_output = ""

    for turn in range(1, MAX_DEBATE_TURNS + 1):
        round_key = f"round_{turn}"

        # ---- Proposer 发言 ----
        if turn == 1:
            proposer_prompt = _build_proposer_task(task)
        else:
            # 用 Reviewer 上一轮的完整输出作为反驳依据
            proposer_prompt = _build_proposer_task(task, reviewer_output)

        proposer_messages = [{"role": "user", "content": proposer_prompt}]

        proposer_response = ""
        async for chunk in llm_client.chat_stream(proposer_messages, system=PROPOSER_SYSTEM_PROMPT):
            proposer_response += chunk

        proposer_output = proposer_response

        # ---- Reviewer 发言 ----
        reviewer_prompt = _build_reviewer_task(task, proposer_output)
        reviewer_messages = [{"role": "user", "content": reviewer_prompt}]

        reviewer_response = ""
        async for chunk in llm_client.chat_stream(reviewer_messages, system=REVIEWER_SYSTEM_PROMPT):
            reviewer_response += chunk

        reviewer_output = reviewer_response

        # ---- 保存本轮辩论日志（截取前 150 字符） ----
        debate_logs[round_key] = {
            "proposer_agent": _truncate(proposer_output),
            "reviewer_agent": _truncate(reviewer_output),
        }

    return {
        "debate_logs": debate_logs,
        "final_proposer_output": proposer_output,
        "final_reviewer_output": reviewer_output,
    }


# ============================================================
# 任务 3：结果打包
# ============================================================

def _extract_code_snippet(text: str) -> str:
    """从 LLM 输出中提取第一个代码块。若无代码块，返回前 300 字符。"""
    import re
    match = re.search(r'```[\w]*\n(.*?)```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text[:300].strip()


def _extract_summary(text: str) -> str:
    """提取代码块前的描述文本作为摘要。若无，取前 100 字符。"""
    import re
    # 取代码块之前的文本
    before_code = re.split(r'```', text)[0].strip()
    if before_code:
        return before_code[:100]
    return text[:100].strip()


def format_debate_response(arena_result: dict) -> dict:
    """
    将辩论结果打包为前端要求的 JSON 协议格式。

    Args:
        arena_result: run_debate_arena 的返回值

    Returns:
        严格符合前端协议的 JSON dict
    """
    proposer_output = arena_result.get("final_proposer_output", "")
    reviewer_output = arena_result.get("final_reviewer_output", "")
    debate_logs = arena_result.get("debate_logs", {})

    return {
        "message_type": "harness_debate_interaction",
        "interaction_required": True,
        "debate_logs": debate_logs,
        "candidate_solutions": [
            {
                "id": "sol_A",
                "author": "激进派 (Proposer)",
                "summary": _extract_summary(proposer_output),
                "code_snippet": _extract_code_snippet(proposer_output),
            },
            {
                "id": "sol_B",
                "author": "审查派 (Reviewer)",
                "summary": _extract_summary(reviewer_output),
                "code_snippet": _extract_code_snippet(reviewer_output),
            },
        ],
        "required_actions": ["accept_a", "accept_b", "reject_all"],
    }


# ============================================================
# 顶层编排函数（供外部调用）
# ============================================================

async def run_harness(user_input: str, llm_client: Any) -> dict | None:
    """
    完整的 Harness 编排流程。如果不需要辩论，返回 None。

    Args:
        user_input: 用户原始输入
        llm_client: LLM 客户端实例

    Returns:
        辩论结果 dict（可直接发送给前端），或 None（放行给普通 Agent 处理）
    """
    # Step 1: 意图拦截
    evaluation = await evaluate_interaction_need(user_input, llm_client)
    if not evaluation["needs_interaction"]:
        return None

    # Step 2: 辩论沙盒
    arena_result = await run_debate_arena(user_input, llm_client)

    # Step 3: 结果打包
    response = format_debate_response(arena_result)
    return response
