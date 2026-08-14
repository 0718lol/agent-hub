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

import asyncio
import re

from app.core.llm_client import llm_client
from app.core.quality_standards import STANDARDS, QualityReport, detect_output_type, run_rules


class QualityGate:
    def __init__(self, enabled: bool = True, max_retries: int = 1,
                 use_llm_judge: bool = False, best_of_n: int = 2,
                 max_concurrent_generations: int = 3):
        self.enabled = enabled
        self.max_retries = max_retries
        self.use_llm_judge = use_llm_judge
        self.best_of_n = best_of_n  # 2 = generate 2 candidates pick best (default)
        # Semaphore to limit concurrent LLM generation calls and protect API quota
        self._generation_semaphore = asyncio.Semaphore(max_concurrent_generations)

    def evaluate(self, text: str, agent_id: str = "") -> QualityReport:
        """Run rule-based evaluation on output text. Fast and deterministic."""
        if not self.enabled or not text.strip():
            return QualityReport(output_type="general", score=1.0, passed=True)

        # Extract code blocks for targeted evaluation
        code_blocks = re.findall(r'```(\w*)\n(.*?)```', text, re.DOTALL)

        if code_blocks:
            reports = []
            for lang, code in code_blocks:
                if not code.strip():
                    continue
                output_type = self._lang_to_type(lang) or detect_output_type(code, agent_id)
                r = run_rules(code, output_type)
                reports.append(r)

            if not reports:
                return QualityReport(output_type="general", score=1.0, passed=True)

            # Find the worst report by score
            worst_report = min(reports, key=lambda r: r.score)

            # Combine all results, suggestions, and calculate overall passed
            all_results = []
            all_suggestions = []
            for r in reports:
                all_results.extend(r.results)
                all_suggestions.extend(r.suggestions)

            all_passed = all(r.passed for r in reports)

            return QualityReport(
                output_type=worst_report.output_type,
                score=worst_report.score,
                passed=all_passed,
                results=all_results,
                suggestions=all_suggestions
            )
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

        except Exception as e:
            import logging
            logging.getLogger("quality_gate").warning(f"LLM judge failed: {e}", exc_info=True)

        return report

    async def evaluate_and_improve(
        self, agent, message: str, raw_output: str,
        agent_id: str = "", history: list | None = None,
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
                reports = []
                for lang, code in code_blocks:
                    if not code.strip():
                        continue
                    output_type = self._lang_to_type(lang) or detect_output_type(code, agent_id)
                    r = await self.evaluate_with_llm_judge(code, output_type)
                    reports.append(r)

                if reports:
                    worst_report = min(reports, key=lambda r: r.score)
                    all_results = []
                    all_suggestions = []
                    for r in reports:
                        all_results.extend(r.results)
                        all_suggestions.extend(r.suggestions)
                    all_passed = all(r.passed for r in reports)
                    report = QualityReport(
                        output_type=worst_report.output_type,
                        score=worst_report.score,
                        passed=all_passed,
                        results=all_results,
                        suggestions=all_suggestions
                    )

        return current_output, report

    async def best_of_n_generate(
        self, agent, message: str, agent_id: str = "",
        history: list | None = None, n: int | None = None,
        on_progress: object | None = None,
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


class TenantAwareQualityGate:
    """Resolve mutable quality settings per active tenant."""

    def __init__(self):
        object.__setattr__(self, "_default", QualityGate(enabled=True, max_retries=1, use_llm_judge=False, best_of_n=1))
        object.__setattr__(self, "_gates", {})

    def _gate(self) -> QualityGate:
        from app.core.tenancy import current_tenant_id

        tenant_id = current_tenant_id()
        if not tenant_id:
            return self._default
        gate = self._gates.get(tenant_id)
        if gate is None:
            from app.core.tenant_config import get_tenant_json

            config = get_tenant_json(tenant_id, "quality_gate", {}) or {}
            gate = QualityGate(
                enabled=config.get("enabled", True),
                max_retries=config.get("max_retries", 1),
                use_llm_judge=config.get("use_llm_judge", False),
                best_of_n=config.get("best_of_n", 1),
            )
            self._gates[tenant_id] = gate
        return gate

    def __getattr__(self, name):
        return getattr(self._gate(), name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._gate(), name, value)


quality_gate = TenantAwareQualityGate()
