import logging
from collections.abc import AsyncGenerator

logger = logging.getLogger("claude_code_client")


async def claude_code_stream(
    messages: list[dict],
    system: str = "",
    api_key: str = "",
    model: str = "",
) -> AsyncGenerator[str, None]:
    """Stream responses from Claude Code SDK.

    Requires:
      - pip install claude-code-sdk
      - npm install -g @anthropic-ai/claude-code

    Uses ClaudeCodeOptions(api_key=...) for per-request key injection.
    No global os.environ mutation -- safe for concurrent use.
    """
    try:
        from anthropic.types import TextBlock, ToolUseBlock
        from claude_code_sdk import ClaudeCodeOptions, query
    except ImportError:
        yield "[Error: Claude Code SDK not installed. Run: pip install claude-code-sdk && npm install -g @anthropic-ai/claude-code]"
        return

    prompt = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            prompt = msg["content"]
            break
    if not prompt and messages:
        prompt = messages[-1].get("content", "")

    options = ClaudeCodeOptions(max_turns=10)
    if api_key:
        options.api_key = api_key
    if system:
        options.system_prompt = system
    if model:
        options.model = model

    try:
        async for message in query(prompt=prompt, options=options):
            if message.role == "assistant":
                for block in message.content:
                    if isinstance(block, TextBlock) and block.text:
                        yield block.text
                    elif isinstance(block, ToolUseBlock):
                        tool_info = block.name
                        if hasattr(block, "input") and isinstance(block.input, dict):
                            cmd = block.input.get("command", block.input.get("content", ""))
                            if cmd:
                                tool_info += ": " + str(cmd)[:120]
                        yield "\n[thinking] " + tool_info + " [/thinking]\n"
            elif message.role == "result":
                for block in message.content:
                    if isinstance(block, TextBlock) and block.text:
                        yield block.text
    except Exception as e:
        yield "\n[Claude Code error: " + type(e).__name__ + ": " + str(e)[:300] + "]"
