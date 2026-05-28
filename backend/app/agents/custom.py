from .base import BaseAgent

# Runtime executable tool IDs that can be assigned to custom agents
RUNTIME_TOOL_IDS = ["web_search", "http_request", "file_read", "file_write", "file_list", "safe_python_executor", "browser_action", "file_view_windowed", "file_edit_line", "run_stateful_command"]


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
    "safe_python_executor": {
        "id": "safe_python_executor",
        "name": "安全代码沙箱",
        "icon": "🛡️",
        "description": "安全执行 Python 脚本，以单步自愈和自校验的方式批量读写文件及运行测试",
        "prompt_addon": "\n- 你可以使用安全代码沙箱。使用 [tool_call:safe_python_executor]{\"code\": \"python代码\"}[/tool_call] 调用，允许单步多工具运行、循环自测与纠错。",
    },
    "browser_action": {
        "id": "browser_action",
        "name": "赛博浏览器",
        "icon": "🌐",
        "description": "以视觉验证和DOM元素扁平压缩的形式在浏览器内模拟页面交互与视觉自校验",
        "prompt_addon": "\n- 你可以使用赛博浏览器交互工具。使用 [tool_call:browser_action]{\"action\": \"goto\", \"url\": \"http://example.com\"}[/tool_call] 调用，支持 goto, click, type, scroll, screenshot 操作，结合网页截图及红底白字数字 ID 标签进行精确 of 坐标模拟和视觉校验自愈。",
    },
    "file_view_windowed": {
        "id": "file_view_windowed",
        "name": "窗口化查看器",
        "icon": "🔭",
        "description": "以视口式滑动窗口的形式精细滚动读取沙盒中大文件的特定行区间，节省 Token",
        "prompt_addon": "\n- 你可以使用窗口化查看器精细读取文件片段（不推荐全量 file_read 读大文件）。使用 [tool_call:file_view_windowed]{\"path\": \"文件路径\", \"start_line\": 1, \"line_count\": 100}[/tool_call] 调用，根据末尾提示的 [Scroll up/down available] 决定是否翻页滚动。",
    },
    "file_edit_line": {
        "id": "file_edit_line",
        "name": "行级微编辑器",
        "icon": "✂️",
        "description": "对沙盒中的文件执行高容错、省 Token 的行级微替换编辑，并自动触发静态编译语法自检校验",
        "prompt_addon": "\n- 你可以使用行级微编辑器来修改已有文件（强烈推荐代替 replace_file_content）。使用 [tool_call:file_edit_line]{\"path\": \"文件路径\", \"start_line\": 起始行, \"end_line\": 结束行, \"replacement_code\": \"新代码\"}[/tool_call] 调用，系统在物理保存前会自动执行 linter 静态编译校验，若语法损坏则会自动回滚防写烂。",
    },
    "run_stateful_command": {
        "id": "run_stateful_command",
        "name": "有状态命令行",
        "icon": "💻",
        "description": "在物理沙盒工作空间内持久地、有状态地执行指定的 Shell 命令行，支持多步环境状态继承",
        "prompt_addon": "\n- 你可以使用有状态命令行（比 workspace_run_command 更有状态）。使用 [tool_call:run_stateful_command]{\"command\": \"命令行指令\"}[/tool_call] 调用，支持跨步骤继承路径目录状态（如先 cd 后运行测试）与激活的环境变量状态，带 15 秒命令超时保护。",
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
        # Separate prompt-addon tools from executable runtime tools
        self.enabled_tools = [t for t in self.tools if t in RUNTIME_TOOL_IDS] or None
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
