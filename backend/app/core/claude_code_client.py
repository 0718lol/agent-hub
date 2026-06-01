import os
import asyncio
from typing import AsyncGenerator

_api_key_lock = asyncio.Lock()


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
      - ANTHROPIC_API_KEY set (or passed via api_key param)
    """
    try:
        from claude_code_sdk import query, ClaudeCodeOptions
        from anthropic.types import TextBlock, ToolUseBlock
    except ImportError:
        yield (
            "[错误: Claude Code SDK 未安装。请执行以下命令：\n"
            "1. pip install claude-code-sdk\n"
            "2. npm install -g @anthropic-ai/claude-code]"
        )
        return

    # Build prompt: use the last user message as the primary prompt
    prompt = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            prompt = msg["content"]
            break
    if not prompt and messages:
        prompt = messages[-1].get("content", "")

    # Build options
    options = ClaudeCodeOptions(max_turns=10)
    if system:
        options.system_prompt = system
    if model:
        options.model = model

    # Hold the lock for the ENTIRE operation (set env -> query -> restore env).
    # This prevents another coroutine from overwriting ANTHROPIC_API_KEY between
    # set and the actual query() call (TOCTOU race).
    # Trade-off: concurrent requests with different API keys are serialized.
    # Python 3.9+: CancelledError inherits BaseException, so finally always runs.
    if api_key:
        async with _api_key_lock:
            original_key = os.environ.get("ANTHROPIC_API_KEY", "")
            os.environ["ANTHROPIC_API_KEY"] = api_key
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
                                        tool_info += f": {str(cmd)[:120]}"
                                yield f"\n[thinking]🔧 {tool_info}[/thinking]\n"
                    elif message.role == "result":
                        for block in message.content:
                            if isinstance(block, TextBlock) and block.text:
                                yield block.text
            except Exception as e:
                yield f"\n[Claude Code 调用出错: {type(e).__name__}: {str(e)[:300]}]"
            finally:
                os.environ["ANTHROPIC_API_KEY"] = original_key
    else:
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
                                    tool_info += f": {str(cmd)[:120]}"
                            yield f"\n[thinking]🔧 {tool_info}[/thinking]\n"
                elif message.role == "result":
                    for block in message.content:
                        if isinstance(block, TextBlock) and block.text:
                            yield block.text
        except Exception as e:
            yield f"\n[Claude Code 调用出错: {type(e).__name__}: {str(e)[:300]}]"
