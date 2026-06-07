"""BrowserAgent - specialized agent for web browsing and documentation lookup."""
from .base import BaseAgent


class BrowserAgent(BaseAgent):
    agent_id = "agent_browser"
    name = "浏览器助手"
    avatar = "🌐"
    role = "浏览器操作"
    style = "准确、高效"
    system_prompt = (
        "你是 AgentHub 的浏览器助手，头像是🌐。你的职责是查阅文档、搜索解决方案、验证网页效果。"
        "\n\n【工作流程】"
        "\n1. 分析任务，确定需要查什么文档"
        "\n2. 调用 browser_open_url 打开文档网站"
        "\n3. 调用 browser_get_content 提取关键内容"
        "\n4. 将结果返回给其他 Agent"
        "\n\n【调用格式】"
        '\n[tool_call:browser_open_url]{"url": "文档URL"}[/tool_call]'
        '\n[tool_call:browser_get_content]{"selector": "article"}[/tool_call]'
        '\n[tool_call:browser_screenshot]{}[/tool_call]'
        "\n\n【文档网站速查表】"
        "\n- FastAPI: https://fastapi.tiangolo.com/"
        "\n- React: https://react.dev/"
        "\n- Vue: https://vuejs.org/"
        "\n- SQLAlchemy: https://docs.sqlalchemy.org/"
        "\n- Pydantic: https://docs.pydantic.dev/"
        "\n- Python: https://docs.python.org/3/"
        "\n- StackOverflow: https://stackoverflow.com/search?q=问题"
    )

    def _generate_reply(self, message: str, context=None) -> str:
        msg = message.lower()
        if any(kw in msg for kw in ["文档", "document", "api", "查询"]):
            return self._doc_reply(message)
        elif any(kw in msg for kw in ["截图", "screenshot", "拍照"]):
            return self._screenshot_reply()
        elif any(kw in msg for kw in ["搜索", "search", "问题"]):
            return self._search_reply(message)
        return self._doc_reply(message)

    def _doc_reply(self, message: str) -> str:
        return (
            "[thinking]分析需求：需要查阅相关文档[/thinking]"
            "[thinking]选择文档源：根据技术栈选择对应官方文档[/thinking]"
            "\n正在查阅文档...🔍"
            '\n\n[tool_call:browser_open_url]{"url": "https://fastapi.tiangolo.com/"}[/tool_call]'
        )

    def _screenshot_reply(self) -> str:
        return (
            "[thinking]截取当前页面截图[/thinking]"
            "\n正在截图...📷"
            '\n\n[tool_call:browser_screenshot]{}[/tool_call]'
        )

    def _search_reply(self, message: str) -> str:
        query = message.replace("搜索", "").replace("search", "").strip()
        url = f"https://stackoverflow.com/search?q={query}"
        return (
            f"[thinking]搜索解决方案：{query}[/thinking]"
            f"\n正在搜索...🔍"
            f'\n\n[tool_call:browser_open_url]{{"url": "{url}"}}[/tool_call]'
        )
