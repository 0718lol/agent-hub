from .base import BaseAgent


class PMAgent(BaseAgent):
    agent_id = "agent_pm"
    name = "PM 小助手"
    avatar = "📋"
    role = "产品经理"
    style = "条理清晰，爱用数字列表"
    system_prompt = (
        "你是 AgentHub 的产品经理（PM 小助手），头像是📋。"
        "你说话条理清晰，喜欢用数字列表组织内容，擅长需求分析和任务拆解。"
        "\n\n最重要的规则：永远不要问用户问题！直接干活！"
        "\n\n规则："
        "\n- 不管用户说什么，直接拆解任务并分配给团队。不要问'需要什么功能'、'目标用户是谁'等任何问题。"
        "\n- 即使用户说得很简单（比如'做个网站'），你也直接按照最常见的方案拆解任务。"
        "\n- 回复简洁：2-3 句话描述方案 + 任务列表 + 分配标记。总共不超过 8 行。"
        "\n- 不要使用 markdown 标题（#），用加粗和数字列表即可。"
        "\n- 任务分配后，必须在末尾输出分配标记：[assign:agent_frontend] [assign:agent_backend] 等，让系统自动启动对应 agent。"
        "\n- 根据任务内容选择合适的 agent：前端页面→agent_frontend，后端接口→agent_backend，测试→agent_tester，部署→agent_devops，设计→agent_designer，海报/宣传图/网页交互设计→同时分配给设计 agent_designer 和前端 agent_frontend，以便设计视觉方案并由前端生成高精度的交互预览与代码。"
        "\n- 绝对不要输出 [clarify:...] 标记。永远不要问问题。"
        "\n\n【唯一例外 — ask_user 工具】遇到影响整个技术方案走向的关键分歧（如：用户说'做个 App'但没说平台；'做商城'但没说品类），可以用一次 ask_user 问一个关键问题："
        "\n  [ask_user:简短问题?|选项A::一句话说明|*推荐项加星::说明|选项C::说明]"
        "\n  最多 4 个选项，description 不能含 `|` 或 `]`，一次回复最多一个 ask_user。"
        "\n  若用户消息以 [ask_user_reply] 开头，是对上一个 ask_user 的回答，直接基于答案拆任务，不要重复提问。"
    )

    VAGUE_KEYWORDS = ["做个", "搞个", "写个", "弄个", "开发一个", "做一个", "来个", "整一个"]

    SPECIFIC_KEYWORDS = [
        "登录", "注册", "todo", "待办", "博客", "商城", "电商", "聊天", "后台",
        "管理", "dashboard", "仪表盘", "api", "接口", "数据库", "表单",
    ]

    def _is_vague(self, message: str) -> bool:
        msg = message.lower()
        has_vague = any(kw in msg for kw in self.VAGUE_KEYWORDS)
        has_specific = any(kw in msg for kw in self.SPECIFIC_KEYWORDS)
        # Only truly vague if it's vague AND has no specific keywords AND is very short
        return has_vague and not has_specific and len(message) < 15

    def _detect_category(self, message: str) -> str:
        msg = message.lower()
        if any(kw in msg for kw in ["app", "应用", "移动端", "小程序"]):
            return "app"
        elif any(kw in msg for kw in ["网站", "网页", "web", "前端", "页面"]):
            return "web"
        elif any(kw in msg for kw in ["api", "接口", "后端", "服务", "数据"]):
            return "api"
        return "default"

    def _generate_reply(self, message: str, context: list | None = None) -> str:
        msg = message.lower()

        if message.startswith("[clarified]") or message.startswith("[ask_user_reply]"):
            return self._handle_clarified(message)

        if any(kw in msg for kw in ["需求", "做一个", "开发", "项目", "帮我"]):
            if self._is_vague(message):
                return self._ask_clarification(message)
            return self._decompose_task(message)

        if any(kw in msg for kw in ["进度", "状态", "怎么样"]):
            return "当前项目进展顺利！各模块任务已分配给对应工程师，预计很快就能看到产出。我会持续跟进每个环节的进度。"

        if any(kw in msg for kw in ["谢谢", "感谢", "不错"]):
            return "不客气！有新的需求随时告诉我，我会帮你拆解和协调资源。"

        return "收到！我来帮你拆解需求并安排团队协作。有什么具体要做的随时说！"

    def _ask_clarification(self, message: str) -> str:
        category = self._detect_category(message)
        templates = {
            "app": "做什么平台?|*Web 应用::浏览器访问，开发最快|小程序::微信生态，用户基础大|移动 App::iOS/Android 原生体验",
            "web": "需要后端吗?|*纯前端展示::静态页面，快速上线|前后端分离::需要数据存储和用户系统|全栈一体::后端渲染，SEO 友好",
            "api": "管理什么数据?|*用户系统::注册登录权限|商品订单::电商核心数据|内容管理::文章评论媒体",
            "default": "能说得更具体吗?|*告诉我核心功能::最重要的 1-2 个功能点|参考哪个产品::类似某个已有产品|描述使用场景::谁在什么情况下用",
        }
        return f"[ask_user:{templates[category]}]"

    def _handle_clarified(self, message: str) -> str:
        answers_text = message.replace("[clarified]", "").replace("[ask_user_reply]", "").strip()
        return (
            "太好了，需求已经明确了！根据你的回答，我整理如下：\n\n"
            "---\n\n"
            f"{answers_text}\n\n"
            "---\n\n"
            "**需求规格确认：**\n"
            "1. 功能范围已明确\n"
            "2. 技术方向已确定\n"
            "3. UI 风格已确认\n\n"
            "**接下来的任务拆解：**\n"
            "1. 🎨 **设计顾问** — 输出 UI 设计稿和配色方案\n"
            "2. 🖥️ **前端工程师** — 开发页面组件和交互\n"
            "3. ⚙️ **后端工程师** — 设计 API 和数据模型\n"
            "4. 🧪 **测试工程师** — 编写测试用例\n"
            "5. 🚀 **运维工程师** — 配置部署方案\n\n"
            "任务已分配，各 Agent 即将开始工作！"
            "[assign:agent_frontend][assign:agent_backend]"
        )

    def _decompose_task(self, message: str) -> str:
        msg = message.lower()
        if any(kw in msg for key_list in [["海报", "宣传", "设计", "广告", "画", "图", "promo"]] for kw in key_list):
            return (
                "好的，收到巧乐兹海报的设计需求！我已经为你规划好了海报的设计工作：\n\n"
                "**任务拆解：**\n"
                "1. 🎨 **视觉风格** — 确立巧克力浓郁与清凉夏日的视觉碰撞\n"
                "2. 🖥️ **海报排版** — 规划主要视觉焦点、大字标题与行动按钮位置\n"
                "3. ⚙️ **背景融合** — 配备高品质巧克力脆皮冰淇淋素材\n"
                "4. 🧪 **细节规范** — 配色微调与字体排版规范设计\n\n"
                "现在把任务同时移交给设计顾问与前端开发顾问，马上为你输出精美宣传海报并生成前端代码！"
                "[assign:agent_designer][assign:agent_frontend]"
            )

        return (
            "好的，我来帮你拆解一下需求：\n\n"
            "**需求分析：**\n"
            f"根据你的描述「{message[:30]}...」，我梳理了以下任务：\n\n"
            "**任务拆解：**\n"
            "1. 🎨 **UI 设计** — 设计页面布局和交互方案\n"
            "2. 🖥️ **前端开发** — 实现页面组件 and 样式\n"
            "3. ⚙️ **后端开发** — 实现 API 接口 and 数据模型\n"
            "4. 🧪 **测试验证** — 编写测试用例并验证功能\n"
            "5. 🚀 **部署上线** — 配置部署方案并上线\n\n"
            "任务已分配，各 Agent 即将开始工作！"
            "[assign:agent_frontend][assign:agent_backend]"
        )
