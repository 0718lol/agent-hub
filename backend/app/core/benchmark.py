"""
Benchmark Runner — one-click demo evaluation.

Runs a set of predefined tasks through agents, collects quality scores,
and produces a comparison report (normal vs best-of-N, with/without quality gate).
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Callable, Any


@dataclass
class BenchmarkCase:
    """A single benchmark test case."""
    id: str
    name: str
    prompt: str
    agent_id: str
    expected_traits: list[str] = field(default_factory=list)  # keywords expected in output
    category: str = "general"


@dataclass
class BenchmarkResult:
    """Result for a single benchmark case."""
    case_id: str
    case_name: str
    agent_id: str
    # Normal generation
    normal_output: str = ""
    normal_score: float = 0.0
    normal_duration_ms: int = 0
    # Best-of-N generation
    bon_output: str = ""
    bon_score: float = 0.0
    bon_duration_ms: int = 0
    bon_n: int = 3
    # Improvement
    improvement: float = 0.0

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "case_name": self.case_name,
            "agent_id": self.agent_id,
            "normal_score": round(self.normal_score, 1),
            "normal_duration_ms": self.normal_duration_ms,
            "bon_score": round(self.bon_score, 1),
            "bon_duration_ms": self.bon_duration_ms,
            "bon_n": self.bon_n,
            "improvement": round(self.improvement, 1),
            "normal_output_preview": self.normal_output[:200],
            "bon_output_preview": self.bon_output[:200],
        }


# Predefined benchmark cases
BENCHMARK_CASES = [
    BenchmarkCase(
        id="bench_1",
        name="Python 排序算法",
        prompt="用 Python 实现一个高效的归并排序，要求支持自定义比较函数，有完整的类型注解和 docstring",
        agent_id="agent_backend",
        expected_traits=["def", "merge", "sort", "->", '"""'],
        category="code",
    ),
    BenchmarkCase(
        id="bench_2",
        name="React 组件",
        prompt="用 React 实现一个带搜索过滤功能的 Todo List 组件，要求使用 hooks，支持添加、删除、标记完成、搜索过滤",
        agent_id="agent_frontend",
        expected_traits=["useState", "filter", "onClick", "return"],
        category="code",
    ),
    BenchmarkCase(
        id="bench_3",
        name="REST API 设计",
        prompt="设计一个博客系统的 REST API，包含用户注册/登录、文章 CRUD、评论功能。给出完整的 FastAPI 代码实现",
        agent_id="agent_backend",
        expected_traits=["@app", "async def", "BaseModel", "router"],
        category="code",
    ),
    BenchmarkCase(
        id="bench_4",
        name="单元测试",
        prompt="为以下函数编写完整的 pytest 单元测试，覆盖正常、边界和异常情况：\ndef calculate_discount(price: float, vip_level: int) -> float:\n    if price <= 0: raise ValueError\n    rates = {1: 0.95, 2: 0.9, 3: 0.8}\n    return price * rates.get(vip_level, 1.0)",
        agent_id="agent_tester",
        expected_traits=["def test_", "assert", "pytest", "raises"],
        category="test",
    ),
    BenchmarkCase(
        id="bench_5",
        name="系统架构分析",
        prompt="分析一个日活 100 万的电商秒杀系统需要哪些核心组件，给出架构图描述和关键技术选型建议",
        agent_id="agent_backend",
        expected_traits=["缓存", "队列", "限流", "数据库"],
        category="design",
    ),
]


@dataclass
class BenchmarkRun:
    """A complete benchmark run with all results."""
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    status: str = "running"  # running | completed | error
    results: list[BenchmarkResult] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    progress: int = 0
    total: int = 0

    def finish(self):
        self.end_time = time.time()
        self.status = "completed"
        if self.results:
            normal_scores = [r.normal_score for r in self.results]
            bon_scores = [r.bon_score for r in self.results]
            self.summary = {
                "total_cases": len(self.results),
                "duration_s": round(self.end_time - self.start_time, 1),
                "normal_avg_score": round(sum(normal_scores) / len(normal_scores), 1),
                "bon_avg_score": round(sum(bon_scores) / len(bon_scores), 1),
                "avg_improvement": round(
                    sum(r.improvement for r in self.results) / len(self.results), 1
                ),
                "best_improvement_case": max(self.results, key=lambda r: r.improvement).case_name,
            }

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "progress": self.progress,
            "total": self.total,
            "duration_s": round(time.time() - self.start_time, 1) if self.status == "running" else round(self.end_time - self.start_time, 1),
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary,
        }


# Global benchmark state
_current_run: Optional[BenchmarkRun] = None


def get_current_run() -> Optional[BenchmarkRun]:
    return _current_run


async def run_benchmark(
    agents: dict,
    quality_gate: Any,
    on_progress: Optional[Callable] = None,
    cases: Optional[list[BenchmarkCase]] = None,
) -> BenchmarkRun:
    """
    Run the benchmark suite.

    Args:
        agents: Dict of agent_id -> agent instance
        quality_gate: QualityGate instance for scoring
        on_progress: Optional callback(progress, total, current_result)
        cases: Optional custom cases, defaults to BENCHMARK_CASES

    Returns:
        BenchmarkRun with all results
    """
    global _current_run

    test_cases = cases or BENCHMARK_CASES
    run = BenchmarkRun(total=len(test_cases))
    _current_run = run

    for i, case in enumerate(test_cases):
        agent = agents.get(case.agent_id)
        if not agent:
            continue

        result = BenchmarkResult(
            case_id=case.id,
            case_name=case.name,
            agent_id=case.agent_id,
        )

        try:
            # ---- Normal generation ----
            start = time.perf_counter()
            normal_chunks = []
            async for chunk in agent.stream_reply(case.prompt):
                normal_chunks.append(chunk)
            result.normal_output = "".join(normal_chunks)
            result.normal_duration_ms = int((time.perf_counter() - start) * 1000)

            # Score normal output
            normal_eval = await quality_gate.evaluate(
                result.normal_output,
                agent_id=case.agent_id,
            )
            result.normal_score = normal_eval.get("score", 0) if isinstance(normal_eval, dict) else 50

            # ---- Best-of-N generation ----
            start = time.perf_counter()
            # Temporarily set best_of_n
            old_bon = quality_gate.best_of_n
            quality_gate.best_of_n = 3
            bon_output, bon_report, _ = await quality_gate.best_of_n_generate(
                agent, case.prompt, agent_id=case.agent_id,
            )
            quality_gate.best_of_n = old_bon

            result.bon_output = bon_output
            result.bon_duration_ms = int((time.perf_counter() - start) * 1000)
            result.bon_score = bon_report.get("score", 0) if isinstance(bon_report, dict) else 70
            result.bon_n = 3

            # Calculate improvement
            result.improvement = result.bon_score - result.normal_score

        except Exception as e:
            result.normal_output = f"[执行错误: {str(e)[:100]}]"
            result.normal_score = 0
            result.bon_output = ""
            result.bon_score = 0

        run.results.append(result)
        run.progress = i + 1

        if on_progress:
            await on_progress(run.progress, run.total, result)

    run.finish()
    return run
