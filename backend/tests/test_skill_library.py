"""Tests for skill library."""
import pytest

from app.core.skill_library import SkillLibrary


class TestSkillLibraryInit:
    def test_initial_state(self):
        lib = SkillLibrary()
        assert lib.skills == {}
        assert lib.max_skills == 100


class TestAddSkill:
    def test_add_skill_success(self):
        lib = SkillLibrary()
        result = lib.add_skill("test_001", "FastAPI error handling", "try: pass except: return error", "agent_backend", "python")
        assert result is True
        assert "test_001" in lib.skills

    def test_add_skill_sliding_window(self):
        lib = SkillLibrary(max_skills=3)
        for i in range(5):
            lib.add_skill(f"skill_{i}", f"desc {i}", "code", "agent_test")
        assert len(lib.skills) == 3

    def test_add_skill_with_zero_success_rate(self):
        lib = SkillLibrary()
        result = lib.add_skill("test_001", "desc", "code", "agent_test", success_rate=0.0)
        assert result is True
        assert lib.skills["test_001"]["success_rate"] == 0.0


class TestSearch:
    def test_search_empty_library(self):
        lib = SkillLibrary()
        results = lib.search("test query")
        assert results == []

    def test_search_keyword_match(self):
        lib = SkillLibrary()
        lib.add_skill("s1", "FastAPI error handling", "try: pass", "agent_backend")
        lib.add_skill("s2", "React component", "function App() {}", "agent_frontend")
        results = lib.search("FastAPI error")
        assert len(results) >= 1
        assert "FastAPI" in results[0]["description"]

    def test_search_with_agent_filter(self):
        lib = SkillLibrary()
        lib.add_skill("s1", "FastAPI error", "code", "agent_backend")
        lib.add_skill("s2", "React error", "code", "agent_frontend")
        results = lib.search("error", agent_id="agent_backend")
        assert all(s.get("agent_id") == "agent_backend" for s in results)

    def test_search_top_k_limit(self):
        lib = SkillLibrary()
        for i in range(10):
            lib.add_skill(f"s{i}", f"skill {i} code", "code", "agent_test")
        results = lib.search("code", top_k=3)
        assert len(results) <= 3


class TestExtractSkills:
    def test_extract_no_blocks(self):
        lib = SkillLibrary()
        output = "Just some text without code blocks"
        skills = lib.extract_skills_from_output(output, "agent_test")
        assert len(skills) == 0

    def test_extract_ignores_short_blocks(self):
        lib = SkillLibrary()
        output = "```python\nx = 1\n```"
        skills = lib.extract_skills_from_output(output, "agent_test")
        assert len(skills) == 0


class TestGetStats:
    def test_empty_library(self):
        lib = SkillLibrary()
        stats = lib.get_stats()
        assert stats["total_skills"] == 0

    def test_with_skills(self):
        lib = SkillLibrary()
        lib.add_skill("s1", "desc", "code", "agent_backend")
        lib.add_skill("s2", "desc", "code", "agent_frontend")
        stats = lib.get_stats()
        assert stats["total_skills"] == 2
        assert len(stats["agents"]) == 2
