import json
import re
import uuid
from .base import BaseAgent
from .custom import AVAILABLE_TOOLS


class AgentBuilderAgent(BaseAgent):
    agent_id = "agent_builder"
    name = "Agent 工坊"
    avatar = "🔧"
    role = "Agent 创建助手"
    style = "友好引导，条理清晰"
    system_prompt = (
        "你是 AgentHub 的 Agent 工坊助手，头像是🔧。你的职责是帮助用户通过对话创建自定义 AI Agent。"
        "\n\n你必须通过对话收集以下信息来创建 Agent："
        "\n1. **名称**：Agent 的名字"
        "\n2. **角色**：Agent 负责什么"
        "\n3. **性格风格**：Agent 的说话方式"
        "\n4. **系统提示词**：Agent 的核心行为指令"
        "\n5. **工具能力**：从可用工具中选择"
        "\n\n可用工具列表："
        + "".join(f"\n- `{tid}`: {t['icon']} {t['name']} — {t['description']}" for tid, t in AVAILABLE_TOOLS.items())
        + "\n\n【重要规则】："
        "\n- 当你收集到足够信息后（至少有名称和角色），直接创建 Agent。"
        "\n- 创建时，在回复末尾输出标签："
        '\n  [create_agent:{"name":"名称","avatar":"emoji","role":"角色","style":"风格","system_prompt":"提示词","tools":["tool_id1","tool_id2"]}]'
        "\n- 如果用户的描述比较简单，你也要主动补全合理的 system_prompt，不要让它太短。"
        "\n- system_prompt 要写得详细专业，包含角色定位、行为规范、输出格式等。"
        "\n- avatar 使用一个贴切的 emoji。"
        "\n- 如果用户想查看已有工具，列出上面的工具列表。"
        "\n- 如果用户想删除 agent，输出 [delete_agent:agent_id] 标签。"
    )

    # --- Keyword → tool auto-mapping for mock mode ---
    _TOOL_KEYWORDS = {
        "code_gen": ["代码", "编程", "开发", "写代码", "code", "程序"],
        "web_preview": ["网页", "html", "页面", "前端", "web", "预览"],
        "data_analysis": ["数据", "分析", "统计", "图表", "可视化"],
        "api_design": ["api", "接口", "后端", "服务", "rest"],
        "testing": ["测试", "用例", "bug", "质量", "qa"],
        "doc_writing": ["文档", "readme", "文案", "写作", "注释", "说明"],
        "svg_mockup": ["原型", "设计", "ui", "线框", "mockup", "svg"],
        "deploy": ["部署", "docker", "运维", "cicd", "上线", "devops"],
        "translation": ["翻译", "translate", "英语", "日语", "多语言", "中英"],
        "creative_writing": ["创意", "故事", "文案", "营销", "广告", "小说"],
    }

    # --- Emoji auto-selection for mock mode ---
    _ROLE_EMOJIS = {
        "翻译": "🌍", "translate": "🌍",
        "代码": "💻", "编程": "💻", "开发": "💻",
        "设计": "🎨", "ui": "🎨",
        "数据": "📊", "分析": "📊",
        "测试": "🧪", "qa": "🧪",
        "写作": "✍️", "文案": "✍️", "文档": "📝",
        "运维": "🚀", "部署": "🚀",
        "客服": "💬", "助手": "🤖",
        "教学": "📚", "老师": "👨‍🏫",
        "安全": "🔒", "review": "🔍",
        "产品": "📋", "需求": "📋",
    }

    def _generate_reply(self, message: str, context: list = None) -> str:
        msg = message.lower().strip()

        # --- Show available tools ---
        if any(kw in msg for kw in ["工具", "能力", "tool", "有哪些工具", "工具列表"]):
            return self._list_tools()

        # --- Delete agent ---
        if any(kw in msg for kw in ["删除", "移除", "delete", "remove"]):
            return self._delete_guide(message)

        # --- Help / welcome ---
        if any(kw in msg for kw in ["帮助", "help", "怎么用", "你好", "hi"]):
            return self._welcome()

        # --- Creation request: try to parse and create ---
        if any(kw in msg for kw in [
            "创建", "新建", "添加", "做一个", "搞一个", "弄一个",
            "create", "build", "make", "自定义",
            "帮我", "我想要", "我需要",
        ]):
            return self._parse_and_create(message)

        # --- Default: treat as creation request too ---
        return self._parse_and_create(message)

    def _welcome(self) -> str:
        tool_list = "\n".join(
            f"  - `{tid}` {t['icon']} **{t['name']}** — {t['description']}"
            for tid, t in AVAILABLE_TOOLS.items()
        )
        return (
            "欢迎来到 **Agent 工坊** 🔧\n\n"
            "我可以帮你通过对话创建自定义 Agent！你只需要告诉我：\n\n"
            "1. 你想创建什么样的 Agent？（比如「翻译助手」、「代码审查员」）\n"
            "2. 它应该有什么性格？（严谨、活泼、幽默...）\n"
            "3. 需要哪些工具能力？\n\n"
            f"**可用工具：**\n{tool_list}\n\n"
            "💡 **快速开始**：直接说「创建一个翻译助手」试试！\n"
            "也可以详细描述：「创建一个代码审查 Agent，风格严谨，配备代码生成和测试工具」"
        )

    def _list_tools(self) -> str:
        lines = []
        for tid, t in AVAILABLE_TOOLS.items():
            lines.append(f"- `{tid}` {t['icon']} **{t['name']}** — {t['description']}")
        return (
            "**可用工具列表：**\n\n"
            + "\n".join(lines)
            + "\n\n创建 Agent 时告诉我需要哪些工具，我会自动配置！"
        )

    def _delete_guide(self, message: str) -> str:
        # Try to find agent id in the message
        match = re.search(r'agent_custom_\w+', message)
        if match:
            agent_id = match.group(0)
            return (
                f"确认删除 Agent `{agent_id}`？\n\n"
                f"[delete_agent:{agent_id}]"
            )
        return "请告诉我要删除哪个 Agent？你可以提供 Agent 的 ID（格式：agent_custom_xxx）。"

    def _parse_and_create(self, message: str) -> str:
        msg = message.lower()

        # --- Extract name ---
        name = self._extract_name(message)

        # --- Extract role ---
        role = self._extract_role(message)

        # --- Detect avatar ---
        avatar = self._detect_avatar(msg)

        # --- Extract style ---
        style = self._extract_style(message)

        # --- Auto-detect tools ---
        tools = self._detect_tools(msg)

        # --- Build system_prompt ---
        system_prompt = self._build_system_prompt(name, role, style, tools)

        # --- Generate agent ID ---
        short_id = uuid.uuid4().hex[:8]
        agent_id = f"agent_custom_{short_id}"

        # --- Build config ---
        config = {
            "agent_id": agent_id,
            "name": name,
            "avatar": avatar,
            "role": role,
            "style": style,
            "system_prompt": system_prompt,
            "tools": tools,
        }

        config_json = json.dumps(config, ensure_ascii=False)

        tool_names = "、".join(
            AVAILABLE_TOOLS[t]["icon"] + AVAILABLE_TOOLS[t]["name"]
            for t in tools if t in AVAILABLE_TOOLS
        ) or "无"

        return (
            f"好的！我为你创建了自定义 Agent ✨\n\n"
            f"**Agent 配置：**\n"
            f"- **名称**：{avatar} {name}\n"
            f"- **角色**：{role}\n"
            f"- **风格**：{style}\n"
            f"- **工具**：{tool_names}\n"
            f"- **ID**：`{agent_id}`\n\n"
            f"Agent 已创建成功！你可以在左侧对话列表中找到 **{name}**，开始和它对话了 🎉\n\n"
            f"[create_agent:{config_json}]"
        )

    # ---- Extraction helpers ----

    def _extract_name(self, message: str) -> str:
        # Try patterns like "名字叫X", "叫X", "名为X", "名称X"
        for pattern in [
            r'(?:名字|名称|名为|叫做?|命名为?)\s*[：:「]?\s*([^\s,，。！!？?、]{1,10})',
            r'(?:创建|新建|做|搞|弄|添加)(?:一个|个)?\s*[「]?([^\s,，。！!？?」]{2,8}?)(?:[」]?\s*(?:agent|助手|机器人|工具))',
        ]:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1).strip().rstrip("的")

        # Try to extract the main subject
        for pattern in [
            r'(?:创建|新建|做|搞|弄|添加)(?:一个|个)?\s*(.{2,8}?)(?:$|[,，。]|agent)',
        ]:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                name = match.group(1).strip().rstrip("的")
                if len(name) >= 2:
                    return name

        # Fallback
        return "自定义助手"

    def _extract_role(self, message: str) -> str:
        for pattern in [
            r'(?:擅长|负责|专注|专门|主要)\s*(.{2,30}?)(?:[,，。！!]|$)',
            r'(?:能力|功能|用途)[是为：:]\s*(.{2,30}?)(?:[,，。！!]|$)',
        ]:
            match = re.search(pattern, message)
            if match:
                return match.group(1).strip()

        # Infer from keywords
        msg = message.lower()
        if any(kw in msg for kw in ["翻译", "translate"]):
            return "多语言翻译"
        if any(kw in msg for kw in ["代码", "编程", "开发"]):
            return "代码开发"
        if any(kw in msg for kw in ["设计", "ui", "ux"]):
            return "UI/UX 设计"
        if any(kw in msg for kw in ["测试", "qa"]):
            return "软件测试"
        if any(kw in msg for kw in ["文档", "写作"]):
            return "文档撰写"
        if any(kw in msg for kw in ["数据", "分析"]):
            return "数据分析"

        return "智能助手"

    def _extract_style(self, message: str) -> str:
        for pattern in [
            r'(?:风格|性格|语气|态度)[是为：:]*\s*(.{2,15}?)(?:[,，。！!]|$)',
        ]:
            match = re.search(pattern, message)
            if match:
                return match.group(1).strip()

        msg = message.lower()
        if any(kw in msg for kw in ["严谨", "专业", "正式"]):
            return "严谨专业"
        if any(kw in msg for kw in ["活泼", "有趣", "幽默"]):
            return "活泼有趣"
        if any(kw in msg for kw in ["简洁", "精炼", "高效"]):
            return "简洁高效"

        return "友好专业"

    def _detect_avatar(self, msg: str) -> str:
        for keyword, emoji in self._ROLE_EMOJIS.items():
            if keyword in msg:
                return emoji
        return "🤖"

    def _detect_tools(self, msg: str) -> list[str]:
        tools = []
        for tool_id, keywords in self._TOOL_KEYWORDS.items():
            if any(kw in msg for kw in keywords):
                if tool_id not in tools:
                    tools.append(tool_id)
        return tools

    def _build_system_prompt(self, name: str, role: str, style: str, tools: list[str]) -> str:
        prompt = (
            f"你是 AgentHub 平台上的自定义 Agent「{name}」。"
            f"\n你的角色是：{role}。"
            f"\n你的说话风格：{style}。"
            f"\n\n行为规范："
            f"\n- 始终以 {name} 的身份回复，保持角色一致。"
            f"\n- 回复内容要专业、有深度、有实际帮助。"
            f"\n- 不要偏离自己的角色和专业领域。"
            f"\n- 保持 {style} 的说话风格。"
        )
        return prompt
