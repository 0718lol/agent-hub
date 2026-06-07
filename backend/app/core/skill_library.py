"""Skill library - agents accumulate reusable code skills.

Based on: Voyager (MineDojo) skill library pattern.
Uses ChromaDB for vector storage (already in project dependencies).

How it works:
1. Agent generates code -> quality check passes -> extract code snippet -> store as skill
2. Next generation -> search similar skills -> inject into prompt
3. Skills accumulate over time, agent gets better at similar tasks
"""
import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger("skill_library")

# Optional ChromaDB dependency
try:
    import chromadb
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False
    logger.info("ChromaDB not installed, skill library using keyword search only")


class SkillLibrary:
    """Agent skill library with optional vector search.

    Stores reusable code snippets extracted from successful agent outputs.
    Provides semantic search to find relevant skills for new tasks.
    """

    def __init__(self, max_skills: int = 100):
        self.skills: dict[str, dict] = {}
        self.max_skills = max_skills
        self._client = None
        self._collection = None

        if HAS_CHROMADB:
            try:
                self._client = chromadb.Client()
                self._collection = self._client.create_collection("agent_skills")
                logger.info("Skill library initialized with ChromaDB vector search")
            except Exception as e:
                logger.warning(f"ChromaDB init failed, using keyword search: {e}")

    def add_skill(
        self,
        skill_id: str,
        description: str,
        code: str,
        agent_id: str,
        language: str = "",
        success_rate: float = 1.0,
    ) -> bool:
        """Add a skill to the library."""
        try:
            self.skills[skill_id] = {
                "description": description,
                "code": code,
                "agent_id": agent_id,
                "language": language,
                "success_rate": success_rate,
                "use_count": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            # Enforce sliding window
            if len(self.skills) > self.max_skills:
                oldest = min(self.skills, key=lambda k: self.skills[k]["created_at"])
                self.skills.pop(oldest, None)
                if self._collection:
                    try:
                        self._collection.delete(ids=[oldest])
                    except Exception:
                        pass

            # Add to vector store
            if self._collection:
                try:
                    self._collection.upsert(
                        documents=[description],
                        metadatas=[{"skill_id": skill_id, "agent_id": agent_id, "language": language}],
                        ids=[skill_id],
                    )
                except Exception as e:
                    logger.warning(f"ChromaDB upsert failed: {e}")

            logger.info(f"Skill added: {skill_id} ({description[:50]})")
            return True
        except Exception as e:
            logger.warning(f"Failed to add skill: {e}")
            return False

    def search(self, query: str, agent_id: str = None, top_k: int = 3) -> list[dict]:
        """Search for relevant skills using vector similarity or keyword fallback."""
        if not self.skills:
            return []

        results = []

        # Try vector search first
        if self._collection and self._collection.count() > 0:
            try:
                where = {"agent_id": agent_id} if agent_id else None
                vec_results = self._collection.query(
                    query_texts=[query],
                    n_results=min(top_k, self._collection.count()),
                    where=where,
                )
                for skill_id in vec_results.get("ids", [[]])[0]:
                    if skill_id in self.skills:
                        skill = self.skills[skill_id].copy()
                        skill["id"] = skill_id
                        results.append(skill)
            except Exception as e:
                logger.debug(f"Vector search failed, falling back to keyword: {e}")

        # Fallback: keyword search
        if not results:
            query_lower = query.lower()
            for skill_id, skill in self.skills.items():
                if agent_id and skill.get("agent_id") != agent_id:
                    continue
                desc_lower = skill["description"].lower()
                code_lower = skill.get("code", "").lower()[:200]
                if any(word in desc_lower or word in code_lower for word in query_lower.split() if len(word) > 2):
                    s = skill.copy()
                    s["id"] = skill_id
                    results.append(s)

        # Sort by success rate, then by use count
        results.sort(key=lambda x: (x.get("success_rate", 0), x.get("use_count", 0)), reverse=True)
        return results[:top_k]

    def extract_skills_from_output(self, output: str, agent_id: str) -> list[dict]:
        """Extract reusable code snippets from agent output."""
        skills = []
        code_blocks = re.findall(r'```(\w*)\n(.*?)```', output, re.DOTALL)

        for lang, code in code_blocks:
            code = code.strip()
            if len(code) < 30:
                continue

            description = self._extract_description(code, lang)
            skill_id = f"skill_{agent_id}_{len(self.skills) + len(skills)}"

            skills.append({
                "id": skill_id,
                "description": description,
                "code": code,
                "language": lang,
                "agent_id": agent_id,
            })

        return skills

    def _extract_description(self, code: str, lang: str) -> str:
        """Extract a human-readable description from code."""
        if lang == "python":
            match = re.search(r'def (\w+)\(', code)
            if match:
                return f"Python function: {match.group(1)}"
            match = re.search(r'class (\w+)', code)
            if match:
                return f"Python class: {match.group(1)}"
        elif lang in ("html", "jsx", "vue"):
            match = re.search(r'<title>(.*?)</title>', code, re.IGNORECASE)
            if match:
                return f"HTML page: {match.group(1)}"
            match = re.search(r'<h[12][^>]*>(.*?)</h[12]>', code, re.IGNORECASE)
            if match:
                return f"HTML component: {match.group(1)}"
        elif lang == "css":
            match = re.search(r'\.([\w-]+)\s*\{', code)
            if match:
                return f"CSS class: {match.group(1)}"
        return f"{lang} code ({len(code)} chars)"

    def get_stats(self) -> dict:
        """Get library statistics."""
        return {
            "total_skills": len(self.skills),
            "vector_search": self._collection is not None,
            "agents": list(set(s["agent_id"] for s in self.skills.values())),
        }
