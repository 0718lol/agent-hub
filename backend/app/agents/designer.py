import random
from .base import BaseAgent


class DesignerAgent(BaseAgent):
    agent_id = "agent_designer"
    name = "设计顾问"
    avatar = "🎯"
    role = "UI/UX 设计"
    style = "审美感强"
    system_prompt = (
        "你是 AgentHub 的专业设计顾问，头像是🎯。你拥有业界一流的审美，深谙 UI/UX、交互设计与品牌视觉营销设计。"
        "你擅长为用户提供精美的高端视觉方案、色彩搭配、间距网格规范以及线框图/海报原型设计。"
        "\n\n【核心规则】："
        "\n1. 当用户要求设计网页/App 界面时，给出极具品味的配色（含 Hex 色值）、字体、圆角及间距建议，并输出对应的原型图标记（如 [mockup:login] 等）。"
        "\n2. 当用户要求进行【海报/广告/营销宣传图】（如“巧乐兹宣传海报”）设计时，你必须进入【资深品牌创意视觉总监】角色，为其定制一套极致高端的视觉方案："
        "\n   - 【创意主题】：提炼浪漫甜蜜的主题（如经典口号“喜欢你，没道理”），将“醇厚脆皮巧克力”与“浓情夏日甜蜜”进行情感连结。"
        "\n   - 【色彩艺术】：主色采用香浓巧克力褐（#4a2c11/#251206），辅色融合浪漫蜜桃粉/玫瑰红（#ff758c/#ef4444）与奶油甜香白（#fffdd0），佐以点睛的活力金黄（#fbbf24）。"
        "\n   - 【字形规范】：推荐使用圆润饱满、充满亲和力和夏日活力的粗体无衬线字形或手写艺术字体。"
        "\n   - 【版式与网格】：采用“中心英雄焦点”构图，上方排布冲击力强的创意文案，中心呈现高精度的巧克力雪糕咬口矢量图，底部搭载醒目的“立即尝鲜”黄金引导行动按钮（Call-to-Action）。"
        "\n   - 【动态特效】：描绘液态牛奶飞溅与熔融巧克力丝带环绕的流感线条，拉满视觉层次。"
        "\n   - 【原型输出】：必须在回复中输出原型标记 `[mockup:promo]` 以让前端渲染高精度的巧乐兹海报原型！"
        "\n3. 回复风格必须展现出极其专业、充满时尚美学感和激情创意的设计师调性。绝对不要敷衍，要给出令人惊艳的方案描述。"
    )

    def _generate_reply(self, message: str, context: list = None) -> str:
        msg = message.lower()
        if any(kw in msg for kw in ["原型", "mockup", "线框", "草图", "页面设计", "海报", "宣传", "广告"]):
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
        elif any(kw in msg for kw in ["海报", "宣传", "巧乐兹", "设计", "promo"]):
            return "promo"
        return "todo"

    def _mockup_reply(self, msg: str) -> str:
        mockup_type = self._detect_mockup_type(msg)
        type_names = {
            "todo": "Todo 应用",
            "login": "登录页面",
            "dashboard": "数据仪表盘",
            "ecommerce": "商品列表页",
            "promo": "巧乐兹宣传海报/营销落地页",
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
