"""
Quality Gate — Executable output evaluation framework.

Pipeline:
  1. Extract code blocks from agent output
  2. Auto-detect output type (html/python/api/document)
  3. Run rule-based checks (instant, deterministic)
  4. Optionally run LLM-as-judge (semantic evaluation)
  5. If failed: auto-retry with feedback injected into prompt
  6. Best-of-N: parallel generate N candidates, pick highest score
  7. Broadcast quality report to frontend

Usage:
  gate = QualityGate(enabled=True, max_retries=1, best_of_n=3)
  final_output = await gate.evaluate_and_improve(agent, message, raw_output, conversation_id)
"""

import re
import asyncio
from typing import AsyncGenerator

from app.core.quality_standards import (
    QualityReport, detect_output_type, run_rules, STANDARDS
)
from app.core.llm_client import llm_client


class QualityGate:
    def __init__(self, enabled: bool = True, max_retries: int = 1,
                 use_llm_judge: bool = False, best_of_n: int = 1,
                 max_concurrent_generations: int = 3):
        self.enabled = enabled
        self.max_retries = max_retries
        self.use_llm_judge = use_llm_judge
        self.best_of_n = best_of_n  # 1 = disabled, 3 = generate 3 candidates pick best
        # Semaphore to limit concurrent LLM generation calls and protect API quota
        self._generation_semaphore = asyncio.Semaphore(max_concurrent_generations)

    def evaluate(self, text: str, agent_id: str = "") -> QualityReport:
        """Run rule-based evaluation on output text. Fast and deterministic."""
        if not self.enabled or not text.strip():
            return QualityReport(output_type="general", score=1.0, passed=True)

        # Extract code blocks for targeted evaluation
        code_blocks = re.findall(r'```(\w*)\n(.*?)```', text, re.DOTALL)

        if code_blocks:
            # Evaluate the largest code block
            lang, code = max(code_blocks, key=lambda x: len(x[1]))
            output_type = self._lang_to_type(lang) or detect_output_type(code, agent_id)
            return run_rules(code, output_type)
        else:
            # Evaluate the full text as document/general
            output_type = detect_output_type(text, agent_id)
            return run_rules(text, output_type)

    async def evaluate_with_llm_judge(self, text: str, output_type: str) -> QualityReport:
        """Run LLM-as-judge evaluation. Slower but semantically deeper."""
        standard = STANDARDS.get(output_type, STANDARDS["general"])
        judge_prompt = standard.get("judge_prompt")

        if not judge_prompt or not llm_client.is_configured():
            return run_rules(text, output_type)

        # Run rules first
        report = run_rules(text, output_type)

        # Then run LLM judge for semantic assessment
        try:
            judge_messages = [{"role": "user", "content": f"{judge_prompt}\n\n---\n{text[:6000]}"}]
            judge_response = ""
            async for chunk in llm_client.chat_stream(
                judge_messages,
                "你是代码质量评审员。只输出评分和问题，不要多余内容。"
            ):
                judge_response += chunk

            # Parse score from response
            score_match = re.search(r'SCORE:\s*(\d+)', judge_response)
            if score_match:
                llm_score = int(score_match.group(1)) / 10.0
                # Blend rule score and LLM score (60% rules, 40% LLM)
                report.score = report.score * 0.6 + llm_score * 0.4
                report.passed = report.passed and llm_score >= standard["pass_threshold"]

            # Parse issues
            issues_match = re.search(r'ISSUES:(.*)', judge_response, re.DOTALL)
            if issues_match:
                suggestions = [s.strip() for s in issues_match.group(1).strip().split('\n') if s.strip()]
                report.suggestions = suggestions[:5]

        except Exception:
            pass  # LLM judge failure is non-fatal, keep rule-based result

        return report

    async def evaluate_and_improve(
        self, agent, message: str, raw_output: str,
        agent_id: str = "", history: list = None,
    ) -> tuple[str, QualityReport]:
        """
        Evaluate output. If failed, retry with quality feedback.
        Returns (final_output, final_report).
        """
        if not self.enabled:
            return raw_output, QualityReport(output_type="general", score=1.0, passed=True)

        report = self.evaluate(raw_output, agent_id)

        if report.passed:
            return raw_output, report

        # Failed — attempt retry with feedback
        retries = 0
        current_output = raw_output

        while not report.passed and retries < self.max_retries:
            retries += 1
            feedback = report.feedback_text()
            if not feedback:
                break

            # Construct retry prompt with quality feedback
            retry_message = (
                f"{message}\n\n"
                f"【质量检查未通过，请修复以下问题后重新输出】：\n{feedback}\n"
                f"请直接输出修复后的完整内容，不要解释修复了什么。"
            )

            # Re-run agent
            retry_output = ""
            async for chunk in agent.stream_reply(retry_message, history=history):
                retry_output += chunk

            if retry_output.strip():
                current_output = retry_output
                report = self.evaluate(current_output, agent_id)

        # Optionally run LLM judge on final output
        if self.use_llm_judge and llm_client.is_configured():
            code_blocks = re.findall(r'```(\w*)\n(.*?)```', current_output, re.DOTALL)
            if code_blocks:
                lang, code = max(code_blocks, key=lambda x: len(x[1]))
                output_type = self._lang_to_type(lang) or detect_output_type(code, agent_id)
                report = await self.evaluate_with_llm_judge(code, output_type)

        return current_output, report

    async def best_of_n_generate(
        self, agent, message: str, agent_id: str = "",
        history: list = None, n: int = None,
        on_progress: callable = None,
    ) -> tuple[str, QualityReport, list[dict]]:
        """
        Generate N candidates in parallel, evaluate each, return the best.

        Args:
            agent: Agent instance
            message: User message
            agent_id: Agent ID for type detection
            history: Conversation history
            n: Number of candidates (overrides self.best_of_n)
            on_progress: Optional async callback(candidate_index, status)

        Returns:
            (best_output, best_report, all_candidates_summary)
        """
        n = n or self.best_of_n
        if n <= 1:
            # Single generation, no parallel candidates
            output = ""
            async for chunk in agent.stream_reply(message, history=history):
                output += chunk
            report = self.evaluate(output, agent_id)
            return output, report, [{"index": 0, "score": report.score, "selected": True}]

        # Parallel generation of N candidates
        async def _generate_one(index: int) -> tuple[int, str]:
            async with self._generation_semaphore:
                text = ""
                async for chunk in agent.stream_reply(message, history=history):
                    text += chunk
                return index, text

        if on_progress:
            await on_progress(-1, f"并行生成 {n} 个候选方案...")

        # Run all N generations concurrently
        tasks = [_generate_one(i) for i in range(n)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Evaluate each candidate
        candidates = []
        for result in results:
            if isinstance(result, Exception):
                continue
            idx, text = result
            if not text.strip():
                continue
            report = self.evaluate(text, agent_id)
            candidates.append({
                "index": idx,
                "text": text,
                "report": report,
                "score": report.score,
            })

        if not candidates:
            # All failed — return empty
            empty_report = QualityReport(output_type="general", score=0.0, passed=False)
            return "", empty_report, []

        # Sort by score descending, pick the best
        candidates.sort(key=lambda c: c["score"], reverse=True)
        best = candidates[0]

        # Build summary for all candidates
        summary = []
        for c in candidates:
            summary.append({
                "index": c["index"],
                "score": c["score"],
                "passed": c["report"].passed,
                "selected": c["index"] == best["index"],
                "preview": c["text"][:100].replace("\n", " "),
            })

        if on_progress:
            await on_progress(best["index"], f"已选择候选 #{best['index']+1}（得分 {best['score']:.2f}）")

        return best["text"], best["report"], summary

    @staticmethod
    def _lang_to_type(lang: str) -> str:
        lang = lang.lower().strip()
        mapping = {
            "html": "html", "htm": "html",
            "python": "python", "py": "python",
            "javascript": "html", "js": "html",  # JS in HTML context
            "css": "html",
            "typescript": "python",  # similar rules apply
            "": "",
        }
        return mapping.get(lang, "")


# Global instance — configurable via API
quality_gate = QualityGate(enabled=True, max_retries=1, use_llm_judge=False, best_of_n=1)
