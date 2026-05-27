"""
Prompt Engine — Structured Layered Prompt Injection Framework

Architecture:
  Layer 0: Identity     — 角色身份定义（不可变）
  Layer 1: Capability   — 工具能力声明（来自 tool 配置）
  Layer 2: Standard     — 质量标准与输出格式（来自 quality gate）
  Layer 3: Context      — 动态上下文（对话历史摘要、任务拆解）
  Layer 4: Task         — 当前任务增强（条件注入）
  Layer 5: Constraint   — 禁止行为（硬性约束，最高优先级）

Each layer:
  - Has a priority (lower number = earlier in prompt, higher authority)
  - Can be conditionally enabled/disabled
  - Supports template variables: {agent_name}, {role}, {style}, etc.
  - Is independently configurable per agent type or globally
"""

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class PromptLayer:
    """A single prompt layer with content and metadata."""
    id: str
    level: int          # 0-5
    content: str
    enabled: bool = True
    condition: Callable = None  # Optional: (context_dict) -> bool

    def render(self, variables: dict = None) -> str:
        """Render layer content with template variables."""
        if not self.enabled:
            return ""
        text = self.content
        if variables:
            for key, val in variables.items():
                text = text.replace(f"{{{key}}}", str(val))
        return text

    def should_inject(self, context: dict = None) -> bool:
        """Check if this layer should be injected given the context."""
        if not self.enabled:
            return False
        if self.condition and context:
            return self.condition(context)
        return True


# ============================================================
# Default Layer Definitions
# ============================================================

LAYER_IDENTITY = PromptLayer(
    id="identity",
    level=0,
    content=(
        "你是 AgentHub 平台中的「{agent_name}」。"
        "\n角色：{role}。"
        "\n说话风格：{style}。"
    ),
)

LAYER_CAPABILITY = PromptLayer(
    id="capability",
    level=1,
    content="",  # Dynamically filled from agent's tool config
)

LAYER_STANDARD_CODE = PromptLayer(
    id="standard_code",
    level=2,
    content=(
        "\n\n【输出标准 — 代码类】："
        "\n- 代码必须完整可执行，禁止使用 `...` 或 TODO 占位。"
        "\n- 使用 ```language 代码块包裹，language 后直接换行（如：```html）。"
        "\n- HTML 必须自包含（内联 CSS/JS），包含 <!DOCTYPE html>、<meta charset=\"utf-8\">、viewport meta。"
        "\n- HTML 页面必须完整可渲染，不依赖任何外部资源。"
        "\n- Python 代码需有异常处理，API 需有错误状态码。"
        "\n- 变量命名清晰，关键逻辑加注释。"
    ),
    condition=lambda ctx: ctx.get("task_type") in ("code", "html", "api", None),
)

LAYER_STANDARD_DOC = PromptLayer(
    id="standard_doc",
    level=2,
    content=(
        "\n\n【输出标准 — 文档类】："
        "\n- 使用 Markdown 格式，有层次标题。"
        "\n- 技术内容必须准确，附代码示例。"
        "\n- 段落精炼，不超过 5 行/段。"
    ),
    condition=lambda ctx: ctx.get("task_type") in ("document", "doc"),
)

LAYER_CONTEXT = PromptLayer(
    id="context",
    level=3,
    content="",  # Dynamically filled per request
)

LAYER_TASK_THINKING = PromptLayer(
    id="task_thinking",
    level=4,
    content=(
        "\n\n【思维过程】："
        "\n- 先用 [thinking]...[/thinking] 标签输出你的分析思路。"
        "\n- 思考完毕后再输出最终答案。"
    ),
)

LAYER_CONSTRAINT = PromptLayer(
    id="constraint",
    level=5,
    content=(
        "\n\n【硬性约束 — 违反则判定输出无效】："
        "\n- 禁止添加用户未要求的修饰词（高效、优雅、强大、极致等）。"
        "\n- 禁止使用套话、空洞总结、重复用户问题。"
        "\n- 禁止省略代码关键部分。"
        "\n- 直接给结果，不加铺垫。问代码给代码，问方案给方案。"
        "\n- 不要在回复开头重述用户的问题或需求。"
    ),
)


# ============================================================
# Prompt Engine
# ============================================================

class PromptEngine:
    """Assembles structured prompts from layered components."""

    def __init__(self):
        # Global layers applied to all agents (can be overridden)
        self.global_layers: list[PromptLayer] = [
            LAYER_IDENTITY,
            LAYER_CAPABILITY,
            LAYER_STANDARD_CODE,
            LAYER_STANDARD_DOC,
            LAYER_CONTEXT,
            LAYER_TASK_THINKING,
            LAYER_CONSTRAINT,
        ]
        # Per-agent layer overrides: agent_id -> list[PromptLayer]
        self.agent_overrides: dict[str, list[PromptLayer]] = {}

    def build(self, agent, context: dict = None) -> str:
        """
        Build the final system prompt for an agent.

        Args:
            agent: Agent instance (has agent_id, name, role, style, system_prompt, tools)
            context: Runtime context dict with keys like:
                - task_type: "code" | "html" | "api" | "document" | None
                - pm_breakdown: str (PM's task analysis)
                - user_intent: str (parsed intent from user message)

        Returns:
            Fully assembled system prompt string.
        """
        if context is None:
            context = {}

        # Template variables
        variables = {
            "agent_name": getattr(agent, 'name', '助手'),
            "role": getattr(agent, 'role', '智能助手'),
            "style": getattr(agent, 'style', '友好专业'),
            "agent_id": getattr(agent, 'agent_id', ''),
        }

        # Collect layers: agent overrides > global
        layers = self.agent_overrides.get(agent.agent_id, self.global_layers)

        # Build each layer
        sections = []

        for layer in sorted(layers, key=lambda l: l.level):
            if not layer.should_inject(context):
                continue

            # Special handling for dynamic layers
            if layer.id == "identity":
                # Use agent's own system_prompt as the identity layer if it exists
                own_prompt = getattr(agent, 'system_prompt', '')
                if own_prompt:
                    sections.append(own_prompt)
                else:
                    rendered = layer.render(variables)
                    if rendered:
                        sections.append(rendered)

            elif layer.id == "capability":
                # Inject tool capability descriptions
                tools = getattr(agent, 'tools', [])
                if tools:
                    from app.agents.custom import AVAILABLE_TOOLS
                    addons = []
                    for tid in tools:
                        tool = AVAILABLE_TOOLS.get(tid)
                        if tool:
                            addons.append(tool["prompt_addon"])
                    if addons:
                        sections.append("\n【工具能力】：" + "".join(addons))

            elif layer.id == "context":
                # Inject dynamic context (PM breakdown, etc.)
                pm_breakdown = context.get("pm_breakdown", "")
                if pm_breakdown:
                    sections.append(f"\n\n【任务上下文】：\nPM 的任务拆解：{pm_breakdown}")

            else:
                rendered = layer.render(variables)
                if rendered:
                    sections.append(rendered)

        return "\n".join(sections)

    def set_layer_enabled(self, layer_id: str, enabled: bool):
        """Enable/disable a global layer by id."""
        for layer in self.global_layers:
            if layer.id == layer_id:
                layer.enabled = enabled
                break

    def get_layers_info(self) -> list[dict]:
        """Return info about all global layers for API exposure."""
        return [
            {
                "id": layer.id,
                "level": layer.level,
                "enabled": layer.enabled,
                "has_condition": layer.condition is not None,
                "content_preview": layer.content[:80] + "..." if len(layer.content) > 80 else layer.content,
            }
            for layer in sorted(self.global_layers, key=lambda l: l.level)
        ]

    def detect_task_type(self, message: str, agent_id: str = "") -> str:
        """Infer task type from message content and agent."""
        import re
        msg = message.lower()

        if agent_id in ("agent_frontend", "agent_designer"):
            return "html"
        if agent_id == "agent_backend":
            return "api"
        if agent_id == "agent_tester":
            return "code"

        if any(kw in msg for kw in ["代码", "函数", "实现", "编程", "code", "编写"]):
            return "code"
        if any(kw in msg for kw in ["页面", "网页", "html", "ui", "界面", "组件"]):
            return "html"
        if any(kw in msg for kw in ["接口", "api", "后端", "服务"]):
            return "api"
        if any(kw in msg for kw in ["文档", "readme", "说明", "教程"]):
            return "document"

        return None  # Unknown — all standard layers apply


# Global singleton
prompt_engine = PromptEngine()
