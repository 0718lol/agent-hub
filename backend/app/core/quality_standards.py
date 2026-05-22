"""
Industry Quality Standards Registry

Defines executable quality criteria per output type.
Each standard contains:
  - Rule-based checks (deterministic, fast, no LLM needed)
  - LLM-as-judge criteria (semantic evaluation prompt)
"""

import re
from dataclasses import dataclass, field


@dataclass
class RuleResult:
    passed: bool
    rule_id: str
    message: str
    severity: str = "error"  # "error" | "warning"


@dataclass
class QualityReport:
    output_type: str
    score: float  # 0.0 ~ 1.0
    passed: bool
    results: list[RuleResult] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "output_type": self.output_type,
            "score": round(self.score, 2),
            "passed": self.passed,
            "errors": [r.message for r in self.results if not r.passed and r.severity == "error"],
            "warnings": [r.message for r in self.results if not r.passed and r.severity == "warning"],
            "suggestions": self.suggestions,
        }

    def feedback_text(self) -> str:
        """Generate feedback for retry prompt."""
        issues = []
        for r in self.results:
            if not r.passed:
                issues.append(f"- [{r.severity.upper()}] {r.message}")
        if not issues:
            return ""
        return "以下质量问题需要修复：\n" + "\n".join(issues)


# ============================================================
# Rule-based Evaluators (deterministic, no LLM)
# ============================================================

def _check_no_placeholder(text: str) -> RuleResult:
    patterns = [
        r'\.\.\.',          # ellipsis used as placeholder
        r'\/\/ ?\.\.\.',    # // ...
        r'# ?\.\.\.',       # # ...
        r'TODO',
        r'FIXME',
        r'这里.*省略',
        r'此处.*省略',
        r'其余.*类似',
        r'以此类推',
    ]
    for p in patterns:
        if re.search(p, text):
            return RuleResult(False, "no_placeholder",
                              f"检测到占位符/省略标记 ({p})，代码必须完整可执行", "error")
    return RuleResult(True, "no_placeholder", "无占位符")


def _check_html_structure(text: str) -> RuleResult:
    checks = {
        r'<!DOCTYPE|<html': "缺少 HTML 文档结构 (DOCTYPE/html 标签)",
        r'<head': "缺少 <head> 标签",
        r'<body': "缺少 <body> 标签",
    }
    for pattern, msg in checks.items():
        if not re.search(pattern, text, re.IGNORECASE):
            return RuleResult(False, "html_structure", msg, "error")
    return RuleResult(True, "html_structure", "HTML 结构完整")


def _check_html_responsive(text: str) -> RuleResult:
    if not re.search(r'viewport', text, re.IGNORECASE):
        return RuleResult(False, "html_responsive",
                          "缺少 viewport meta 标签，页面不适配移动端", "warning")
    return RuleResult(True, "html_responsive", "包含 viewport")


def _check_html_has_style(text: str) -> RuleResult:
    has_style = (re.search(r'<style', text, re.IGNORECASE) or
                 re.search(r'style\s*=', text, re.IGNORECASE) or
                 re.search(r'class\s*=', text, re.IGNORECASE))
    if not has_style:
        return RuleResult(False, "html_style",
                          "HTML 无任何样式，输出为裸 HTML", "error")
    return RuleResult(True, "html_style", "包含样式")


def _check_code_not_empty(text: str) -> RuleResult:
    lines = [l.strip() for l in text.strip().split('\n') if l.strip() and not l.strip().startswith(('#', '//'))]
    if len(lines) < 3:
        return RuleResult(False, "code_not_empty",
                          "代码内容过少（有效行 < 3），疑似未完成", "error")
    return RuleResult(True, "code_not_empty", "代码量充足")


def _check_python_has_error_handling(text: str) -> RuleResult:
    if 'def ' in text and 'try' not in text and 'except' not in text:
        # Only flag if there are function definitions but zero error handling
        func_count = len(re.findall(r'^def ', text, re.MULTILINE))
        if func_count >= 2:
            return RuleResult(False, "python_error_handling",
                              "多个函数定义但缺少异常处理（try/except）", "warning")
    return RuleResult(True, "python_error_handling", "有异常处理")


def _check_api_has_status_codes(text: str) -> RuleResult:
    if re.search(r'(status_code|HTTPException|Response|@app\.|@router\.)', text):
        if not re.search(r'(400|401|403|404|422|500|HTTPException)', text):
            return RuleResult(False, "api_status_codes",
                              "API 代码缺少错误状态码处理（400/404/500）", "warning")
    return RuleResult(True, "api_status_codes", "包含状态码处理")


def _check_doc_has_structure(text: str) -> RuleResult:
    has_heading = bool(re.search(r'^#+\s', text, re.MULTILINE))
    has_list = bool(re.search(r'^[\-\*\d]\s', text, re.MULTILINE))
    if not has_heading and not has_list and len(text) > 200:
        return RuleResult(False, "doc_structure",
                          "文档缺少结构（无标题/列表），纯文本难以阅读", "warning")
    return RuleResult(True, "doc_structure", "文档有结构")


def _check_no_fluff(text: str) -> RuleResult:
    """Detect excessive filler/buzzword density."""
    fluff_words = [
        '高效', '优雅', '强大', '完美', '卓越', '一流', '顶级', '极致',
        '无缝', '革命性', '颠覆', '赋能', '抓手', '闭环', '打法',
    ]
    count = sum(text.count(w) for w in fluff_words)
    if count >= 4:
        return RuleResult(False, "no_fluff",
                          f"修饰词密度过高（{count}个空洞形容词），请精简", "warning")
    return RuleResult(True, "no_fluff", "修饰词密度正常")


# ============================================================
# Standards Registry
# ============================================================

# Each standard: (output_type, list_of_rule_functions, llm_judge_prompt)
STANDARDS = {
    "html": {
        "name": "Web 前端页面",
        "rules": [
            _check_no_placeholder,
            _check_html_structure,
            _check_html_responsive,
            _check_html_has_style,
            _check_code_not_empty,
        ],
        "judge_prompt": (
            "评估这段 HTML 代码的工业质量。判断标准："
            "\n1. 视觉完成度：是否有完整的布局、配色、间距"
            "\n2. 交互完整性：按钮/链接是否有对应行为"
            "\n3. 可维护性：代码是否清晰有组织"
            "\n4. 响应式：是否适配不同屏幕"
            "\n给出 0-10 分和具体改进点。格式：SCORE:X\nISSUES:..."
        ),
        "pass_threshold": 0.7,
    },
    "python": {
        "name": "Python 代码",
        "rules": [
            _check_no_placeholder,
            _check_code_not_empty,
            _check_python_has_error_handling,
        ],
        "judge_prompt": (
            "评估这段 Python 代码的工业质量。判断标准："
            "\n1. 功能完整性：是否实现了所有声明的功能"
            "\n2. 健壮性：异常处理、边界条件、输入验证"
            "\n3. 可读性：命名规范、注释适当"
            "\n4. 最佳实践：是否遵循 PEP8 和 Python 惯用法"
            "\n给出 0-10 分和具体改进点。格式：SCORE:X\nISSUES:..."
        ),
        "pass_threshold": 0.6,
    },
    "api": {
        "name": "API 接口设计",
        "rules": [
            _check_no_placeholder,
            _check_code_not_empty,
            _check_api_has_status_codes,
        ],
        "judge_prompt": (
            "评估这段 API 代码/设计的工业质量。判断标准："
            "\n1. RESTful 规范：资源命名、HTTP 方法使用正确"
            "\n2. 错误处理：完整的错误码和错误信息"
            "\n3. 输入验证：参数校验和类型检查"
            "\n4. 安全性：认证、权限、注入防护"
            "\n给出 0-10 分和具体改进点。格式：SCORE:X\nISSUES:..."
        ),
        "pass_threshold": 0.6,
    },
    "document": {
        "name": "技术文档",
        "rules": [
            _check_no_placeholder,
            _check_doc_has_structure,
            _check_no_fluff,
        ],
        "judge_prompt": (
            "评估这段技术文档的质量。判断标准："
            "\n1. 结构清晰：有层次的标题和分段"
            "\n2. 内容准确：技术描述无误"
            "\n3. 实用性：有代码示例或具体操作步骤"
            "\n4. 简洁性：无废话和空洞修饰"
            "\n给出 0-10 分和具体改进点。格式：SCORE:X\nISSUES:..."
        ),
        "pass_threshold": 0.6,
    },
    "general": {
        "name": "通用输出",
        "rules": [
            _check_no_placeholder,
            _check_no_fluff,
        ],
        "judge_prompt": None,  # No LLM judge for general
        "pass_threshold": 0.8,
    },
}


def detect_output_type(text: str, agent_id: str = "") -> str:
    """Auto-detect output type from content and agent."""
    if agent_id in ("agent_frontend", "agent_designer"):
        if re.search(r'<html|<body|<div|<style', text, re.IGNORECASE):
            return "html"
    if agent_id == "agent_backend":
        return "api" if re.search(r'@app\.|@router\.|FastAPI|flask', text) else "python"
    if agent_id == "agent_tester":
        return "python"
    if agent_id == "agent_devops":
        return "python"

    # Content-based detection
    if re.search(r'<!DOCTYPE|<html|<head.*<body', text, re.IGNORECASE | re.DOTALL):
        return "html"
    if re.search(r'^(import |from |def |class |async def )', text, re.MULTILINE):
        return "python"
    if re.search(r'^#+\s', text, re.MULTILINE) and len(text) > 300:
        return "document"

    return "general"


def run_rules(text: str, output_type: str) -> QualityReport:
    """Run deterministic rule checks. Returns QualityReport."""
    standard = STANDARDS.get(output_type, STANDARDS["general"])
    rules = standard["rules"]
    threshold = standard["pass_threshold"]

    results = [rule(text) for rule in rules]
    total = len(results)
    passed_count = sum(1 for r in results if r.passed)
    error_count = sum(1 for r in results if not r.passed and r.severity == "error")

    score = passed_count / total if total > 0 else 1.0
    overall_passed = score >= threshold and error_count == 0

    return QualityReport(
        output_type=output_type,
        score=score,
        passed=overall_passed,
        results=results,
    )
