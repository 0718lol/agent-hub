import json
import re
import asyncio
from typing import Dict, Any, List, Optional
from app.core.websocket import manager

class StreamContext:
    """
    Context carrier for a single LLM response stream session.
    Provides session metadata and a shared state store across middlewares.
    """
    def __init__(self, conversation_id: str, agent_id: str, websocket_manager=manager):
        self.conversation_id: str = conversation_id
        self.agent_id: str = agent_id
        self.manager = websocket_manager
        self.state: Dict[str, Any] = {}


class StreamMiddleware:
    """
    Abstract Base Class for stream pipeline middlewares.
    Follows Single Responsibility Principle to intercept and transform text streams.
    """
    async def on_chunk(self, chunk: str, context: StreamContext) -> str:
        """
        Processes an incoming chunk of the LLM stream.
        Returns the processed text safe to yield to downstream/the user.
        """
        return chunk

    async def finalize(self, context: StreamContext) -> str:
        """
        Called when the LLM stream ends.
        Flushes and returns any remaining text in the internal buffer.
        """
        return ""


class StreamPipeline:
    """
    Pipeline Scheduler that manages and runs multiple middlewares in sequence.
    """
    def __init__(self, context: StreamContext):
        self.context = context
        self.middlewares: List[StreamMiddleware] = []

    def add_middleware(self, middleware: StreamMiddleware) -> "StreamPipeline":
        self.middlewares.append(middleware)
        return self

    async def process_chunk(self, chunk: str) -> str:
        """
        Sends the chunk through the middleware interceptor chain in order.
        """
        current_text = chunk
        for middleware in self.middlewares:
            current_text = await middleware.on_chunk(current_text, self.context)
        return current_text

    async def finalize(self) -> str:
        """
        Finalizes all middlewares in sequence. Ensures flushed tail text
        is processed sequentially by downstream middlewares.
        """
        final_parts = []
        for i, middleware in enumerate(self.middlewares):
            flushed = await middleware.finalize(self.context)
            if flushed:
                # Pass flushed text through subsequent middlewares
                for sub_mw in self.middlewares[i+1:]:
                    flushed = await sub_mw.on_chunk(flushed, self.context)
                final_parts.append(flushed)
        return "".join(final_parts)


class UnifiedTagMiddleware(StreamMiddleware):
    """
    Unified Tag Interceptor for all square bracket tags starting with '['.
    Handles [thinking], [tool_execution], [assign], [create_agent], and [delete_agent].
    Solves pipeline tag interference using an incremental prefix-aware scan.
    """
    def __init__(self):
        super().__init__()
        self.buffer = ""
        self.inside_tag = None  # None, "thinking", or "tool_execution"
        self.captured = ""

    def is_potential_tag(self, text: str) -> bool:
        """
        Determines if the text starting with '[' could grow into an intercepted tag.
        Handles both static tag prefixes and dynamic tag prefixes.
        """
        if not text.startswith("["):
            return False

        # Static tags and their close tags
        for t in ["[thinking]", "[tool_execution]", "[/thinking]", "[/tool_execution]"]:
            if t.startswith(text):
                return True

        # Dynamic lifecycle tags
        for prefix in ["[assign:", "[create_agent:", "[delete_agent:"]:
            if prefix.startswith(text):
                return True
            if text.startswith(prefix) and "]" not in text:
                return True

        return False

    async def on_chunk(self, chunk: str, context: StreamContext) -> str:
        self.buffer += chunk
        output_parts = []

        while True:
            if self.inside_tag is None:
                # 1. Searching for tags from outside state
                # Check thinking tag
                think_idx = self.buffer.find("[thinking]")
                if think_idx != -1:
                    output_parts.append(self.buffer[:think_idx])
                    self.inside_tag = "thinking"
                    self.captured = ""
                    self.buffer = self.buffer[think_idx + len("[thinking]"):]
                    continue

                # Check tool_execution tag
                tool_idx = self.buffer.find("[tool_execution]")
                if tool_idx != -1:
                    output_parts.append(self.buffer[:tool_idx])
                    self.inside_tag = "tool_execution"
                    self.captured = ""
                    self.buffer = self.buffer[tool_idx + len("[tool_execution]"):]
                    continue

                # Check assign tag
                assign_match = re.search(r'\[assign:(\w+)\]', self.buffer)
                if assign_match:
                    agent_id = assign_match.group(1)
                    if "assigned_agents" not in context.state:
                        context.state["assigned_agents"] = []
                    if agent_id not in context.state["assigned_agents"]:
                        context.state["assigned_agents"].append(agent_id)
                    output_parts.append(self.buffer[:assign_match.start()])
                    self.buffer = self.buffer[assign_match.end():]
                    continue

                # Check create_agent tag
                ca_match = re.search(r'\[create_agent:(.*?)\]', self.buffer, re.DOTALL)
                if ca_match:
                    try:
                        agent_config = json.loads(ca_match.group(1))
                        from app.main import _register_custom_agent
                        _register_custom_agent(agent_config)
                        await context.manager.broadcast(context.conversation_id, {
                            "type": "agent_created",
                            "conversation_id": context.conversation_id,
                            "agent": agent_config,
                        })
                    except Exception:
                        pass
                    output_parts.append(self.buffer[:ca_match.start()])
                    self.buffer = self.buffer[ca_match.end():]
                    continue

                # Check delete_agent tag
                da_match = re.search(r'\[delete_agent:(agent_custom_\w+)\]', self.buffer)
                if da_match:
                    del_id = da_match.group(1)
                    from app.main import _remove_custom_agent
                    _remove_custom_agent(del_id)
                    await context.manager.broadcast(context.conversation_id, {
                        "type": "agent_deleted",
                        "conversation_id": context.conversation_id,
                        "agent_id": del_id,
                    })
                    output_parts.append(self.buffer[:da_match.start()])
                    self.buffer = self.buffer[da_match.end():]
                    continue

                # No complete tags matched. Look for a potential tag prefix at the end of the buffer
                bracket_idx = self.buffer.rfind("[")
                if bracket_idx != -1:
                    potential = self.buffer[bracket_idx:]
                    if self.is_potential_tag(potential):
                        # Hold the partial tag in buffer, yield preceding text
                        output_parts.append(self.buffer[:bracket_idx])
                        self.buffer = potential
                    else:
                        # False positive, yield entire buffer
                        output_parts.append(self.buffer)
                        self.buffer = ""
                else:
                    output_parts.append(self.buffer)
                    self.buffer = ""
                break
            else:
                # 2. Inside a thinking or tool execution block, searching for closing tag
                end_tag = "[/thinking]" if self.inside_tag == "thinking" else "[/tool_execution]"
                idx = self.buffer.find(end_tag)
                if idx != -1:
                    full_content = self.captured + self.buffer[:idx]

                    # Broadcast completed thoughts or tool execution logs
                    await context.manager.broadcast(context.conversation_id, {
                        "type": "thinking",
                        "conversation_id": context.conversation_id,
                        "agent_id": context.agent_id,
                        "text": full_content.strip(),
                    })
                    if self.inside_tag == "thinking":
                        # Send empty thinking event to close frontend bubble
                        await context.manager.broadcast(context.conversation_id, {
                            "type": "thinking",
                            "conversation_id": context.conversation_id,
                            "agent_id": context.agent_id,
                            "text": "",
                        })

                    self.captured = ""
                    self.inside_tag = None
                    self.buffer = self.buffer[idx + len(end_tag):]
                    continue
                else:
                    # Tag end not found. Check if the buffer ends with a prefix of the closing tag
                    bracket_idx = self.buffer.rfind("[")
                    if bracket_idx != -1:
                        potential = self.buffer[bracket_idx:]
                        if end_tag.startswith(potential):
                            # Hold prefix, consume preceding text
                            self.captured += self.buffer[:bracket_idx]
                            self.buffer = potential
                        else:
                            # Not a prefix of end tag, consume all
                            self.captured += self.buffer
                            self.buffer = ""
                    else:
                        self.captured += self.buffer
                        self.buffer = ""

                    # Stream incremental text to WS thinking bubble
                    if self.captured.strip():
                        await context.manager.broadcast(context.conversation_id, {
                            "type": "thinking",
                            "conversation_id": context.conversation_id,
                            "agent_id": context.agent_id,
                            "text": self.captured.strip(),
                        })
                    break

        return "".join(output_parts)

    async def finalize(self, context: StreamContext) -> str:
        res = ""
        if self.inside_tag is not None:
            # Tag never closed, flush it back
            start_tag = "[thinking]" if self.inside_tag == "thinking" else "[tool_execution]"
            res = start_tag + self.captured + self.buffer
        else:
            res = self.buffer
        self.buffer = ""
        self.captured = ""
        self.inside_tag = None
        return res


class CodeBlockMiddleware(StreamMiddleware):
    """
    Markdown Code Block Interceptor.
    Captures ` ```[language]\n[code]``` ` blocks, broadcasts real-time code/preview
    updates to Canvas panel, and substitutes it in user stream with a nice `\n[code_generated]\n` card.
    """
    def __init__(self):
        super().__init__()
        self.buffer = ""
        self.inside = False
        self.captured = ""
        self.language = None
        self.backtick_prefixes = ["`", "``", "```"]

    async def on_code_streaming(self, code: str, context: StreamContext):
        # Send streaming code to the DiffViewer panel
        await context.manager.broadcast(context.conversation_id, {
            "type": "code",
            "conversation_id": context.conversation_id,
            "agent_id": context.agent_id,
            "language": self.language or "html",
            "code": code,
        })
        # If language is HTML or HTM, also update WebPreview
        if self.language and self.language.lower() in ("html", "htm"):
            await context.manager.broadcast(context.conversation_id, {
                "type": "preview",
                "conversation_id": context.conversation_id,
                "agent_id": context.agent_id,
                "html": code,
            })

    async def on_code_matched(self, code: str, context: StreamContext):
        stripped_code = code.strip()
        # Final update
        await context.manager.broadcast(context.conversation_id, {
            "type": "code",
            "conversation_id": context.conversation_id,
            "agent_id": context.agent_id,
            "language": self.language or "html",
            "code": stripped_code,
        })
        if self.language and self.language.lower() in ("html", "htm"):
            await context.manager.broadcast(context.conversation_id, {
                "type": "preview",
                "conversation_id": context.conversation_id,
                "agent_id": context.agent_id,
                "html": stripped_code,
            })

    async def on_chunk(self, chunk: str, context: StreamContext) -> str:
        self.buffer += chunk
        output_parts = []

        while True:
            if not self.inside:
                # Search for starting ```
                idx = self.buffer.find("```")
                if idx != -1:
                    # Match found! Switch to inside code block state
                    output_parts.append(self.buffer[:idx])
                    self.inside = True
                    self.captured = ""
                    self.language = None
                    self.buffer = self.buffer[idx + 3:]
                    continue
                else:
                    # Check partial start prefix at buffer end
                    longest_prefix_len = 0
                    for pref in self.backtick_prefixes:
                        if self.buffer.endswith(pref):
                            longest_prefix_len = max(longest_prefix_len, len(pref))

                    if longest_prefix_len > 0:
                        safe_text = self.buffer[:-longest_prefix_len]
                        self.buffer = self.buffer[-longest_prefix_len:]
                        output_parts.append(safe_text)
                    else:
                        output_parts.append(self.buffer)
                        self.buffer = ""
                    break
            else:
                # Inside code block. Extract language if not yet resolved
                if self.language is None:
                    nl_idx = self.buffer.find("\n")
                    if nl_idx != -1:
                        self.language = self.buffer[:nl_idx].strip() or "html"
                        self.buffer = self.buffer[nl_idx + 1:]
                        continue
                    else:
                        # Language not resolved yet. Check if code block ends before a newline (e.g. ```html```)
                        end_idx = self.buffer.find("```")
                        if end_idx != -1:
                            self.language = self.buffer[:end_idx].strip() or "text"
                            self.inside = False
                            self.buffer = self.buffer[end_idx + 3:]
                            await self.on_code_matched("", context)
                            # Yield card in the typewriter stream
                            output_parts.append("\n[code_generated]\n")
                            continue
                        else:
                            # Keep buffering language line
                            break

                # Searching for ending ```
                idx = self.buffer.find("```")
                if idx != -1:
                    full_code = self.captured + self.buffer[:idx]
                    self.inside = False
                    self.buffer = self.buffer[idx + 3:]
                    await self.on_code_matched(full_code, context)
                    self.captured = ""
                    self.language = None
                    # Yield code generated card to trigger React card rendering
                    output_parts.append("\n[code_generated]\n")
                    continue
                else:
                    # Check partial end prefix at buffer end
                    longest_prefix_len = 0
                    for pref in self.backtick_prefixes:
                        if self.buffer.endswith(pref):
                            longest_prefix_len = max(longest_prefix_len, len(pref))

                    if longest_prefix_len > 0:
                        safe_code = self.buffer[:-longest_prefix_len]
                        self.buffer = self.buffer[-longest_prefix_len:]
                        self.captured += safe_code
                        await self.on_code_streaming(self.captured, context)
                    else:
                        self.captured += self.buffer
                        self.buffer = ""
                        await self.on_code_streaming(self.captured, context)
                    break

        return "".join(output_parts)

    async def finalize(self, context: StreamContext) -> str:
        res = ""
        if self.inside:
            # Unclosed code block! Flush as complete code block and emit card
            code = self.captured + self.buffer
            if self.language is None:
                self.language = "html"
            await self.on_code_matched(code, context)
            res = "\n[code_generated]\n"
        else:
            res = self.buffer
        self.buffer = ""
        self.captured = ""
        self.inside = False
        self.language = None
        return res
