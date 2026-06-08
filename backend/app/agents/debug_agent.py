"""DebugAgent - automatic code debugging and repair.

Based on: SWE-agent (Princeton) + Aider minimal-change philosophy.
Automatically analyzes errors, generates minimal fixes, verifies results.
"""
from .base import BaseAgent


class DebugAgent(BaseAgent):
    agent_id = "agent_debugger"
    name = "Debug 助手"
    avatar = "🔧"
    role = "代码调试"
    style = "冷静、专业、精准"
    system_prompt = (
        "你是 AgentHub 的 Debug 助手，头像是🔧。你的职责是分析代码错误并提供最小化修复。"
        "\n\n【核心原则】"
        "\n1. 只修改出错的行，不重写整个代码"
        "\n2. 保持原有逻辑和结构不变"
        "\n3. 输出修复后的完整代码"
        "\n\n【输出格式】"
        "\n[thinking]分析错误原因...[/thinking]"
        "\n[thinking]确定修复方案...[/thinking]"
        "\n```python"
        "\n# 修复后的完整代码"
        "\n```"
        "\n\n【修复规则】"
        "\n- 缺少 import → 在文件顶部添加"
        "\n- 语法错误 → 只修正错误行"
        "\n- 类型错误 → 修正参数或类型转换"
        "\n- 属性错误 → 修正方法名或添加属性检查"
        "\n- 索引错误 → 添加边界检查"
        "\n- 不要添加注释或重构，只修 bug"
    )

    def _generate_reply(self, message: str, context=None) -> str:
        msg = message.lower()
        if any(kw in msg for kw in ["error", "错误", "bug", "crash", "failed"]):
            return self._debug_reply(message)
        elif any(kw in msg for kw in ["谢谢", "thanks"]):
            return "不客气！有任何代码问题随时找我 🔧"
        return self._debug_reply(message)

    def _debug_reply(self, message: str) -> str:
        return (
            "[thinking]分析错误类型和根本原因...[/thinking]"
            "[thinking]确定最小化修复方案...[/thinking]"
            "\n已定位问题，正在修复... 🔧"
        )
