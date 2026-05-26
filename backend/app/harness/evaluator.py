"""Evaluator — 4-dimension scoring for judge tool results."""

from dataclasses import dataclass, field
from typing import Any

from app.tools.base import JudgeResult


@dataclass
class EvalDimension:
    name: str
    weight: float
    score: float = 0.0
    detail: str = ""


@dataclass
class EvalReport:
    tool_name: str
    input_summary: str
    total_score: float = 0.0
    dimensions: list[EvalDimension] = field(default_factory=list)
    signals: dict = field(default_factory=dict)
    passed: bool = False
    raw_result: Any = None

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "input_summary": self.input_summary,
            "total_score": round(self.total_score, 2),
            "passed": self.passed,
            "dimensions": [
                {"name": d.name, "weight": d.weight, "score": round(d.score, 2), "detail": d.detail}
                for d in self.dimensions
            ],
            "signals": self.signals,
        }


# Weights for the 4 evaluation dimensions
DIMENSION_WEIGHTS = {
    "correctness": 0.40,
    "confidence": 0.20,
    "signals": 0.20,
    "semantic": 0.20,
}


def evaluate_result(
    tool_name: str,
    input_summary: str,
    result: JudgeResult,
    expected_decision: str = "",
    expected_score_range: tuple[float, float] = (0, 100),
    pass_threshold: float = 60.0,
) -> EvalReport:
    """Score a JudgeResult across 4 dimensions.

    Dimensions:
        correctness (40%): Does the decision match expected?
        confidence  (20%): How confident is the score (extreme scores = high confidence)?
        signals     (20%): Are structured signals present and valid?
        semantic    (20%): Is the reason text non-empty and meaningful?
    """
    dims = []

    # 1. Correctness (40%) — decision matches expected, or score in expected range
    if expected_decision:
        correct = result.decision == expected_decision
        correctness_score = 100.0 if correct else 0.0
        detail = f"expected={expected_decision}, got={result.decision}"
    else:
        lo, hi = expected_score_range
        in_range = lo <= result.score <= hi
        correctness_score = 100.0 if in_range else max(0, 100 - abs(result.score - (lo + hi) / 2))
        detail = f"score={result.score:.1f}, range=[{lo},{hi}]"
    dims.append(EvalDimension("correctness", DIMENSION_WEIGHTS["correctness"], correctness_score, detail))

    # 2. Confidence (20%) — extreme scores indicate high confidence
    # score near 0 or 100 = high confidence; near 50 = low confidence
    dist_from_mid = abs(result.score - 50) / 50  # 0..1
    confidence_score = dist_from_mid * 100
    dims.append(EvalDimension("confidence", DIMENSION_WEIGHTS["confidence"], confidence_score,
                              f"score={result.score:.1f}, dist_from_mid={dist_from_mid:.2f}"))

    # 3. Signals (20%) — presence and count of structured signals
    if result.signals:
        non_error_signals = {k: v for k, v in result.signals.items() if k != "error" and v is not None}
        signal_score = min(100, len(non_error_signals) * 25)  # 4+ signals = full marks
        detail = f"{len(non_error_signals)} signals: {list(non_error_signals.keys())}"
    else:
        signal_score = 0.0
        detail = "no signals"
    dims.append(EvalDimension("signals", DIMENSION_WEIGHTS["signals"], signal_score, detail))

    # 4. Semantic (20%) — reason text quality
    reason_len = len(result.reason.strip())
    if reason_len >= 20:
        semantic_score = 100.0
    elif reason_len >= 5:
        semantic_score = 60.0
    elif reason_len > 0:
        semantic_score = 30.0
    else:
        semantic_score = 0.0
    dims.append(EvalDimension("semantic", DIMENSION_WEIGHTS["semantic"], semantic_score,
                              f"reason_len={reason_len}"))

    # Weighted total
    total = sum(d.weight * d.score for d in dims)

    return EvalReport(
        tool_name=tool_name,
        input_summary=input_summary,
        total_score=total,
        dimensions=dims,
        signals=result.signals,
        passed=total >= pass_threshold,
        raw_result=result,
    )
