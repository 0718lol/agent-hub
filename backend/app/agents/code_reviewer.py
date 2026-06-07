"""CodeReviewerAgent - specialized agent for code review and quality analysis."""
from .base import BaseAgent


class CodeReviewerAgent(BaseAgent):
    agent_id = "agent_reviewer"
    name = "代码审查员"
    avatar = "🔍"
    role = "代码审查"
    style = "严谨、专业"
    system_prompt = (
        "你是 AgentHub 的代码审查员，头像是🔍。你的职责是审查其他 Agent 生成的代码。"
        "\n\n【审查维度】"
        "\n1. 正确性：逻辑是否正确，边界条件是否处理"
        "\n2. 安全性：是否有注入风险、敏感信息泄露"
        "\n3. 性能：是否有 N+1 查询、内存泄漏、阻塞操作"
        "\n4. 可维护性：命名是否清晰、结构是否合理、是否有重复代码"
        "\n5. 规范性：是否符合项目编码规范"
        "\n\n【输出格式】"
        "\n先用 [thinking]...[/thinking] 标签写审查过程。"
        "\n然后输出 JSON 格式的审查报告："
        '\n```json'
        '\n{"issues": [{"severity": "high/medium/low", "line": "行号或代码片段", "description": "问题描述", "suggestion": "修复建议"}],'
        '\n "score": {"correctness": 8, "security": 7, "performance": 9, "maintainability": 8},'
        '\n "summary": "总体评价"}'
        '\n```'
        "\n\n【调用工具】"
        "\n如果需要查看文件内容，使用浏览器工具："
        '\n[tool_call:browser_open_url]{"url": "文件URL"}[/tool_call]'
        '\n[tool_call:browser_get_content]{"selector": "pre"}[/tool_call]'
    )

    def _generate_reply(self, message: str, context=None) -> str:
        msg = message.lower()
        if any(kw in msg for kw in ["审查", "review", "检查", "代码质量"]):
            return self._review_reply(message)
        elif any(kw in msg for kw in ["谢谢", "感谢"]):
            return "不客气！代码质量是项目成功的基石，随时可以找我审查代码。🔍"
        return self._review_reply(message)

    def _review_reply(self, message: str) -> str:
        return (
            "[thinking]分析代码结构，检查安全性、性能、可维护性...[/thinking]"
            "\n正在审查代码... 🔍"
            '\n\n```json'
            '\n{"issues": [], "score": {"correctness": 9, "security": 9, "performance": 9, "maintainability": 9}, "summary": "代码质量良好"}'
            '\n```'
        )
