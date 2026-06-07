"""Reflexion engine - zero-dependency agent self-improvement.

Based on: https://github.com/princeton-nlp/reflexion
No external dependencies. Pure Python implementation.

How it works:
1. Agent generates code -> quality check fails -> auto-reflect -> store lesson
2. Next generation -> inject lessons -> better output
3. Repeat: agent learns from every failure automatically
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger("reflexion_engine")


class ReflexionEngine:
    """Agent learns from failures via structured reflection."""

    def __init__(self, max_reflections: int = 10, max_retries: int = 1):
        self.reflections: dict[str, list[dict]] = {}
        self.max_reflections = max_reflections
        self.max_retries = max_retries

    async def reflect(
        self,
        agent_id: str,
        task: str,
        output: str,
        error: str,
        llm_client=None,
    ) -> str | None:
        """Reflect on failure. Returns lesson text or None."""
        if not llm_client:
            return None

        try:
            prompt = (
                "Analyze the following failure and summarize the lesson in one sentence.\n\n"
                f"Task: {task[:300]}\n"
                f"Output: {output[:300]}\n"
                f"Error: {error[:300]}\n\n"
                "Format: [lesson] your summary"
            )

            reflection = ""
            async for chunk in llm_client.chat_stream([{"role": "user", "content": prompt}]):
                reflection += chunk

            reflection = reflection.strip()
            if not reflection or len(reflection) < 5:
                return None

            if "[lesson]" not in reflection.lower():
                reflection = f"[lesson] {reflection}"

            entry = {
                "reflection": reflection,
                "task": task[:100],
                "ts": datetime.now(timezone.utc).isoformat(),
            }

            self.reflections.setdefault(agent_id, []).append(entry)

            if len(self.reflections[agent_id]) > self.max_reflections:
                self.reflections[agent_id] = self.reflections[agent_id][-self.max_reflections:]

            logger.info(f"Agent {agent_id} learned: {reflection}")
            return reflection

        except Exception as e:
            logger.warning(f"Reflexion failed for {agent_id}: {e}")
            return None

    def get_context(self, agent_id: str) -> str:
        """Get recent lessons for prompt injection."""
        try:
            entries = self.reflections.get(agent_id, [])
            if not entries:
                return ""
            recent = entries[-3:]
            lines = [f"- {e['reflection']}" for e in recent]
            return "\n".join(["[history]"] + lines)
        except Exception:
            return ""

    def get_reflections(self, agent_id: str) -> list[dict]:
        """Get all reflections for an agent."""
        return self.reflections.get(agent_id, [])

    def should_retry(self, agent_id: str, attempt: int) -> bool:
        """Check if retry should be attempted."""
        return attempt < self.max_retries

    def clear(self, agent_id: str):
        """Clear all reflections for an agent."""
        self.reflections.pop(agent_id, None)
