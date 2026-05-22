import asyncio
from typing import AsyncGenerator


async def opencode_stream(
    messages: list[dict],
    system: str = "",
) -> AsyncGenerator[str, None]:
    """Stream responses from OpenCode CLI in non-interactive mode.

    Requires:
      - OpenCode installed: https://opencode.ai
        curl -fsSL https://opencode.ai/install | bash
        or: go install github.com/opencode-ai/opencode@latest
      - OpenCode configured with an LLM provider (run `opencode` to set up)
    """

    # Build prompt from the last user message
    prompt = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            prompt = msg["content"]
            break
    if not prompt and messages:
        prompt = messages[-1].get("content", "")

    # Prepend system prompt as context
    if system:
        full_prompt = f"[System Instructions]\n{system}\n\n[User Request]\n{prompt}"
    else:
        full_prompt = prompt

    # Run opencode in non-interactive quiet mode
    cmd = ["opencode", "-p", full_prompt, "-f", "text", "-q"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Stream stdout line by line
        buffer = ""
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace")
            if text:
                buffer += text
                yield text

        await proc.wait()

        if proc.returncode != 0:
            stderr_data = await proc.stderr.read()
            err_msg = stderr_data.decode("utf-8", errors="replace").strip()
            if err_msg:
                yield f"\n[OpenCode 错误 (exit {proc.returncode}): {err_msg[:300]}]"
            elif not buffer.strip():
                yield f"[OpenCode 退出码 {proc.returncode}，未返回内容]"

    except FileNotFoundError:
        yield (
            "[错误: OpenCode CLI 未安装。请执行以下命令安装：\n"
            "curl -fsSL https://opencode.ai/install | bash\n"
            "或: go install github.com/opencode-ai/opencode@latest\n"
            "安装后运行 opencode 完成初始配置]"
        )
    except Exception as e:
        yield f"\n[OpenCode 调用出错: {type(e).__name__}: {str(e)[:300]}]"
