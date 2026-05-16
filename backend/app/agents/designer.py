import random
from .base import BaseAgent


class DesignerAgent(BaseAgent):
    agent_id = "agent_designer"
    name = "设计顾问"
    avatar = "🎯"
    role = "UI/UX 设计"
    style = "审美感强"

    def _generate_reply(self, message: str, context: list = None) -> str:
        msg = message.lower()
        if any(kw in msg for kw in ["原型", "mockup", "线框", "草图", "页面设计"]):
            return self._mockup_reply(msg)
        elif any(kw in msg for kw in ["设计", "ui", "界面", "配色", "布局"]):
            return self._design_reply(msg)
        elif any(kw in msg for kw in ["好看", "丑", "改", "优化"]):
            return "我看了下现在的界面，建议做以下优化：\n\n1. 间距不统一，建议用 8px 网格系统\n2. 颜色对比度不够，文字可读性差\n3. 按钮圆角建议统一为 8px\n\n整体方向没问题，细节打磨一下就好了 🎨"
        return "收到！我来看看设计方案。需要我出 UI 原型图的话直接说～"

    def _detect_mockup_type(self, msg: str) -> str:
        if any(kw in msg for kw in ["登录", "login", "注册"]):
            return "login"
        elif any(kw in msg for kw in ["商品", "购物", "电商", "商城"]):
            return "ecommerce"
        elif any(kw in msg for kw in ["仪表", "dashboard", "数据", "统计", "后台"]):
            return "dashboard"
        return "todo"

    def _mockup_reply(self, msg: str) -> str:
        mockup_type = self._detect_mockup_type(msg)
        type_names = {
            "todo": "Todo 应用",
            "login": "登录页面",
            "dashboard": "数据仪表盘",
            "ecommerce": "商品列表页",
        }
        name = type_names.get(mockup_type, "页面")

        return (
            f"这是{name}的 UI 原型图 🎨\n\n"
            f"我用了线框图风格，方便快速确认布局结构。\n"
            f"主要包含：页面头部、内容区域、交互组件。\n\n"
            f"[mockup:{mockup_type}]\n\n"
            f"如果需要调整布局或换一种页面类型，告诉我就好～"
        )

    def _design_reply(self, msg: str) -> str:
        mockup_type = self._detect_mockup_type(msg)
        return (
            "设计方案来了 🎨\n\n"
            "**配色方案：**\n"
            "- 主色：#6366f1（靛蓝）\n"
            "- 辅色：#22d3ee（青色）\n"
            "- 背景：#0f172a（深蓝黑）\n"
            "- 卡片：rgba(255,255,255,0.05)\n"
            "- 文字：#f8fafc / #94a3b8\n\n"
            "**设计规范：**\n"
            "- 字体：Inter / PingFang SC\n"
            "- 基础间距：8px 网格系统\n"
            "- 圆角：小 4px / 中 8px / 大 16px\n\n"
            f"这是初步的 UI 原型：\n\n"
            f"[mockup:{mockup_type}]\n\n"
            "建议用 8px 网格系统保持一致性。有问题随时沟通～"
        )
