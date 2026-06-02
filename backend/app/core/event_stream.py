import json
import time
from typing import List, Dict, Any
from app.core.database import save_event_item, get_event_items, clear_event_items

class BaseEvent:
    event_type = "base"

    def __init__(self, timestamp: float = None):
        self.timestamp = timestamp or time.time()

    def to_dict(self) -> dict:
        return {"timestamp": self.timestamp}

    @classmethod
    def from_dict(cls, d: dict):
        return cls(timestamp=d.get("timestamp"))


class MessageEvent(BaseEvent):
    event_type = "message"

    def __init__(self, sender: str, content: Any, timestamp: float = None):
        super().__init__(timestamp)
        self.sender = sender
        self.content = content

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"sender": self.sender, "content": self.content})
        return d

    @classmethod
    def from_dict(cls, d: dict):
        return cls(sender=d["sender"], content=d["content"], timestamp=d.get("timestamp"))


class ThoughtEvent(BaseEvent):
    event_type = "thought"

    def __init__(self, agent_id: str, content: str, timestamp: float = None):
        super().__init__(timestamp)
        self.agent_id = agent_id
        self.content = content

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"agent_id": self.agent_id, "content": self.content})
        return d

    @classmethod
    def from_dict(cls, d: dict):
        return cls(agent_id=d["agent_id"], content=d["content"], timestamp=d.get("timestamp"))


class ActionCallEvent(BaseEvent):
    event_type = "action_call"

    def __init__(self, tool_name: str, params: dict, call_id: str = "", timestamp: float = None):
        super().__init__(timestamp)
        self.tool_name = tool_name
        self.params = params
        self.call_id = call_id

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"tool_name": self.tool_name, "params": self.params, "call_id": self.call_id})
        return d

    @classmethod
    def from_dict(cls, d: dict):
        return cls(
            tool_name=d["tool_name"],
            params=d["params"],
            call_id=d.get("call_id", ""),
            timestamp=d.get("timestamp")
        )


class ObservationEvent(BaseEvent):
    event_type = "observation"

    def __init__(self, tool_name: str, success: bool, output: Any, images: list = None, timestamp: float = None):
        super().__init__(timestamp)
        self.tool_name = tool_name
        self.success = success
        self.output = output
        self.images = images or []

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "tool_name": self.tool_name,
            "success": self.success,
            "output": self.output,
            "images": self.images
        })
        return d

    @classmethod
    def from_dict(cls, d: dict):
        return cls(
            tool_name=d["tool_name"],
            success=d["success"],
            output=d["output"],
            images=d.get("images", []),
            timestamp=d.get("timestamp")
        )


EVENT_MAP = {
    "message": MessageEvent,
    "thought": ThoughtEvent,
    "action_call": ActionCallEvent,
    "observation": ObservationEvent
}


class EventStreamManager:
    """Manages appending, fetching and compiling temporal event stream."""

    def append_event(self, conversation_id: str, event: BaseEvent):
        """Append an event to SQLite stream."""
        if not conversation_id:
            return
        data_str = json.dumps(event.to_dict(), ensure_ascii=False)
        save_event_item(conversation_id, event.event_type, event.timestamp, data_str)

    def get_stream(self, conversation_id: str) -> List[BaseEvent]:
        """Fetch all events chronologically for conversation_id."""
        if not conversation_id:
            return []
        rows = get_event_items(conversation_id)
        events = []
        for row in rows:
            etype = row['event_type']
            data = json.loads(row['data'])
            cls = EVENT_MAP.get(etype)
            if cls:
                events.append(cls.from_dict(data))
        return events

    def clear_stream(self, conversation_id: str):
        """Clear all events for conversation_id."""
        if conversation_id:
            clear_event_items(conversation_id)

    def compile_to_messages(self, conversation_id: str) -> List[dict]:
        """Idempotent compiler translating temporal event list to OpenAI standard messages list."""
        events = self.get_stream(conversation_id)
        messages = []
        current_assistant_text = ""
        
        for ev in events:
            if isinstance(ev, MessageEvent):
                # Flush pending assistant text first
                if current_assistant_text:
                    messages.append({"role": "assistant", "content": current_assistant_text.strip()})
                    current_assistant_text = ""
                
                content = ev.content
                if isinstance(content, dict):
                    text = content.get("text", "")
                else:
                    text = str(content)
                
                role = "user" if ev.sender == "user" else "assistant"
                messages.append({"role": role, "content": text})

            elif isinstance(ev, ThoughtEvent):
                current_assistant_text += ev.content

            elif isinstance(ev, ActionCallEvent):
                # Format standard prompt-intercept format
                call_block = f"\n[tool_call:{ev.tool_name}]{json.dumps(ev.params, ensure_ascii=False)}[/tool_call]\n"
                current_assistant_text += call_block

            elif isinstance(ev, ObservationEvent):
                # Flush pending assistant text first
                if current_assistant_text:
                    messages.append({"role": "assistant", "content": current_assistant_text.strip()})
                    current_assistant_text = ""
                
                obs_data = ev.output
                if not ev.success:
                    if isinstance(obs_data, dict):
                        if "error" not in obs_data:
                            obs_data = {"error": obs_data.get("message", str(obs_data))}
                    else:
                        obs_data = {"error": str(obs_data)}
                
                obs_content = (
                    f"[工具结果: {ev.tool_name}]\n"
                    f"{json.dumps(obs_data, ensure_ascii=False, indent=2)}\n\n"
                    f"请基于以上工具结果继续回复用户。"
                )
                
                if ev.images:
                    content_list = [{"type": "text", "text": obs_content}]
                    for img in ev.images:
                        if img:
                            content_list.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{img}"}
                            })
                    messages.append({"role": "user", "content": content_list})
                else:
                    messages.append({"role": "user", "content": obs_content})

        # Flush trailing assistant text
        if current_assistant_text:
            messages.append({"role": "assistant", "content": current_assistant_text.strip()})

        return messages


event_stream_manager = EventStreamManager()
