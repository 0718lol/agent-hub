"""Reflexion engine - zero-dependency agent self-improvement.

Based on: https://github.com/princeton-nlp/reflexion + ExpeL (Experience Learning)
No external dependencies. Pure Python implementation.

How it works:
1. Agent generates code -> quality check -> reflect on outcome
2. Success -> extract strategy -> store as positive lesson
3. Failure -> analyze cause -> store as negative lesson
4. Next generation -> inject relevant lessons -> better output
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger("reflexion_engine")


class ReflexionEngine:
    """Agent learns from both failures and successes via structured reflection."""

    def __init__(self, max_reflections: int = 20, max_retries: int = 1):
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
        success: bool = False,
        score: float = 0.0,
    ) -> str | None:
        """Reflect on outcome (success or failure). Returns lesson text or None."""
        if not llm_client:
            return None

        try:
            if success:
                prompt = (
                    "Analyze the following success and summarize the strategy in one sentence.\n\n"
                    f"Task: {task[:300]}\n"
                    f"Output: {output[:200]}\n"
                    f"Score: {score}\n\n"
                    "Format: [strategy] your summary"
                )
            else:
                prompt = (
                    "Analyze the following failure and summarize the lesson in one sentence.\n\n"
                    f"Task: {task[:300]}\n"
                    f"Output: {output[:200]}\n"
                    f"Error: {error[:200]}\n\n"
                    "Format: [lesson] your summary"
                )

            reflection = ""
            async for chunk in llm_client.chat_stream([{"role": "user", "content": prompt}]):
                reflection += chunk

            reflection = reflection.strip()
            if not reflection or len(reflection) < 5:
                return None

            # Ensure marker prefix
            if success and "[strategy]" not in reflection.lower():
                reflection = f"[strategy] {reflection}"
            elif not success and "[lesson]" not in reflection.lower():
                reflection = f"[lesson] {reflection}"

            entry = {
                "reflection": reflection,
                "task": task[:100],
                "success": success,
                "score": score,
                "ts": datetime.now(timezone.utc).isoformat(),
            }

            self.reflections.setdefault(agent_id, []).append(entry)

            # Sliding window
            if len(self.reflections[agent_id]) > self.max_reflections:
                self.reflections[agent_id] = self.reflections[agent_id][-self.max_reflections:]

            logger.info(f"Agent {agent_id} {'learned strategy' if success else 'learned lesson'}: {reflection}")
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

            # Separate strategies and lessons
            strategies = [e for e in entries if e.get("success")]
            lessons = [e for e in entries if not e.get("success")]

            parts = []
            if strategies:
                recent_strategies = strategies[-2:]
                parts.append("[successful strategies]")
                parts.extend(f"- {e['reflection']}" for e in recent_strategies)
            if lessons:
                recent_lessons = lessons[-2:]
                parts.append("[lessons from failures]")
                parts.extend(f"- {e['reflection']}" for e in recent_lessons)

            return "\n".join(parts) if parts else ""
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
