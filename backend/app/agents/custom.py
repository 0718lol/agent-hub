from .base import BaseAgent


AVAILABLE_TOOLS = {
    "code_gen": {
        "id": "code_gen",
        "name": "代码生成",
        "icon": "💻",
        "description": "生成代码片段和完整项目文件",
        "prompt_addon": "\n- 你可以生成代码。使用 ```language 代码块输出代码，系统会自动高亮展示并发送到代码面板。",
    },
    "web_preview": {
        "id": "web_preview",
        "name": "网页预览",
        "icon": "🌐",
        "description": "生成可实时预览的 HTML 页面",
        "prompt_addon": "\n- 你可以生成 HTML 页面。使用 ```html 代码块输出，系统会自动渲染到预览面板。HTML 必须是自包含的（内联 CSS/JS）。",
    },
    "data_analysis": {
        "id": "data_analysis",
        "name": "数据分析",
        "icon": "📊",
        "description": "分析数据、发现规律、给出可视化建议",
        "prompt_addon": "\n- 你擅长数据分析，能解读数据、发现规律、生成可视化方案。",
    },
    "api_design": {
        "id": "api_design",
        "name": "API 设计",
        "icon": "🔌",
        "description": "设计 RESTful API 接口和数据模型",
        "prompt_addon": "\n- 你擅长 API 设计，使用 RESTful 风格，输出接口文档和示例代码（```python 代码块）。",
    },
    "testing": {
        "id": "testing",
        "name": "测试用例",
        "icon": "🧪",
        "description": "生成测试代码和测试方案",
        "prompt_addon": "\n- 你擅长编写测试用例，使用 pytest 框架，注重边界情况和异常处理。用 ✅ 和 ❌ 标记通过/失败。",
    },
    "doc_writing": {
        "id": "doc_writing",
        "name": "文档撰写",
        "icon": "📝",
        "description": "撰写技术文档、README、注释",
        "prompt_addon": "\n- 你擅长撰写清晰的技术文档，包括 README、API 文档、使用指南等。",
    },
    "svg_mockup": {
        "id": "svg_mockup",
        "name": "SVG 原型图",
        "icon": "🎨",
        "description": "生成 SVG 线框图和 UI 原型设计",
        "prompt_addon": "\n- 你可以生成 SVG 原型图，输出 [mockup:type] 标记来展示线框图。",
    },
    "deploy": {
        "id": "deploy",
        "name": "部署配置",
        "icon": "🚀",
        "description": "生成 Docker、CI/CD、Nginx 配置",
        "prompt_addon": "\n- 你擅长部署配置，能生成 Dockerfile、docker-compose.yml、CI/CD 配置等。每条注意事项前加 ⚠️ 标记。",
    },
    "translation": {
        "id": "translation",
        "name": "多语言翻译",
        "icon": "🌍",
        "description": "中英日韩等多语言互译",
        "prompt_addon": "\n- 你擅长多语言翻译，能准确翻译中英日韩等语言，注重语境和术语的准确性。",
    },
    "creative_writing": {
        "id": "creative_writing",
        "name": "创意写作",
        "icon": "✍️",
        "description": "文案、故事、营销内容创作",
        "prompt_addon": "\n- 你擅长创意写作，包括广告文案、故事创作、营销内容等，文笔优美有感染力。",
    },
}


class CustomAgent(BaseAgent):
    """User-created custom agent with configurable system prompt and tools."""

    def __init__(self, agent_id: str, name: str, avatar: str, role: str,
                 style: str, system_prompt: str, tools: list[str] = None):
        self.agent_id = agent_id
        self.name = name
        self.avatar = avatar
        self.role = role
        self.style = style
        self.tools = tools or []
        # Build the final system prompt with tool capabilities
        self.system_prompt = self._build_full_prompt(system_prompt)

    def _build_full_prompt(self, base_prompt: str) -> str:
        if not self.tools:
            return base_prompt

        tool_addons = []
        for tool_id in self.tools:
            tool = AVAILABLE_TOOLS.get(tool_id)
            if tool:
                tool_addons.append(tool["prompt_addon"])

        if tool_addons:
            return (
                f"{base_prompt}"
                f"\n\n【你的工具能力】：{''.join(tool_addons)}"
            )
        return base_prompt

    def _generate_reply(self, message: str, context: list = None) -> str:
        return f"[{self.name}] 收到！我来处理你的请求。"
