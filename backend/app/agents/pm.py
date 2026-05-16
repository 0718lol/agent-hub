from .base import BaseAgent


class PMAgent(BaseAgent):
    agent_id = "agent_pm"
    name = "PM 小助手"
    avatar = "📋"
    role = "产品经理"
    style = "条理清晰，爱用数字列表"

    def _generate_reply(self, message: str, context: list = None) -> str:
        msg = message.lower()
        if any(kw in msg for kw in ["需求", "做一个", "开发", "项目", "帮我"]):
            return self._decompose_task(message)
        elif any(kw in msg for kw in ["进度", "状态", "怎么样"]):
            return "当前项目进展顺利！各模块任务已分配给对应工程师，预计很快就能看到产出。我会持续跟进每个环节的进度。"
        elif any(kw in msg for kw in ["谢谢", "感谢", "不错"]):
            return "不客气！有新的需求随时告诉我，我会帮你拆解和协调资源。"
        return "收到！我来帮你分析一下这个需求。\n\n请告诉我你具体想做什么功能，我会帮你拆解成可执行的任务分配给团队。"

    def _decompose_task(self, message: str) -> str:
        return (
            "好的，我来帮你拆解一下需求：\n\n"
            "**需求分析：**\n"
            f"根据你的描述「{message[:30]}...」，我梳理了以下任务：\n\n"
            "**任务拆解：**\n"
            "1. 🎨 **UI 设计** — 设计页面布局和交互方案\n"
            "2. 🖥️ **前端开发** — 实现页面组件和样式\n"
            "3. ⚙️ **后端开发** — 实现 API 接口和数据模型\n"
            "4. 🧪 **测试验证** — 编写测试用例并验证功能\n"
            "5. 🚀 **部署上线** — 配置部署方案并上线\n\n"
            "我会把任务分配给对应的工程师，大家开始协作吧！"
        )
