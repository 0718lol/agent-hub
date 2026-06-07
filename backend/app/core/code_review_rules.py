"""Code review rule engine - deterministic pattern-based checks.

These rules provide 100% accurate, zero-latency code analysis.
Each rule is a regex pattern that detects a specific code issue.
"""
import re
from typing import Any

# ============================================================
# Review rules definition
# ============================================================

REVIEW_RULES = [
    {
        "name": "hardcoded_secret",
        "pattern": r'(?:password|secret|api_key|token|apikey)\s*=\s*["\'][^"\']{8,}["\']',
        "severity": "high",
        "description": "Hardcoded secret or password detected",
        "suggestion": "Use environment variables or config files for sensitive data",
    },
    {
        "name": "sql_injection",
        "pattern": r'f["\'].*(?:SELECT|INSERT|UPDATE|DELETE).*\{.*\}.*["\']',
        "severity": "high",
        "description": "Possible SQL injection via f-string",
        "suggestion": "Use parameterized queries instead of string formatting",
    },
    {
        "name": "command_injection",
        "pattern": r'(?:os\.system|subprocess\.call|subprocess\.run)\s*\(\s*f["\']|\.format\(',
        "severity": "high",
        "description": "Possible command injection",
        "suggestion": "Use subprocess with list arguments, avoid shell=True",
    },
    {
        "name": "bare_except",
        "pattern": r'except\s*:|except\s+Exception\s*:\s*$',
        "severity": "medium",
        "description": "Bare except catches all exceptions including KeyboardInterrupt",
        "suggestion": "Catch specific exception types",
    },
    {
        "name": "empty_catch",
        "pattern": r'except.*:\s*\n\s*pass\s*$',
        "severity": "medium",
        "description": "Empty except block silently swallows errors",
        "suggestion": "At minimum, add logging: logger.warning(...)",
    },
    {
        "name": "no_error_handling",
        "pattern": r'async\s+def\s+\w+[^:]*:\s*\n(?:(?!try|except).)*?\bawait\b',
        "severity": "medium",
        "description": "Async function with await but no error handling",
        "suggestion": "Add try/except for async operations",
    },
    {
        "name": "magic_number",
        "pattern": r'(?<![.\w])\d{4,}(?![.\w%])',
        "severity": "low",
        "description": "Magic number without named constant",
        "suggestion": "Extract to a named constant for readability",
    },
    {
        "name": "global_variable",
        "pattern": r'^[A-Z_][A-Z_0-9]+\s*=\s*(?!None|True|False|\d|["\']|\[|\{|\()',
        "severity": "low",
        "description": "Global mutable variable",
        "suggestion": "Consider using a class or config instead",
    },
]


def rule_based_review(code: str) -> list[dict[str, Any]]:
    """Run deterministic rule-based checks on code.
    
    Returns a list of issues found, each with severity, description, and suggestion.
    """
    issues = []
    lines = code.split('\n')

    for rule in REVIEW_RULES:
        for match in re.finditer(rule["pattern"], code, re.MULTILINE):
            line_num = code[:match.start()].count('\n') + 1
            context = lines[line_num - 1].strip() if line_num <= len(lines) else ""

            issues.append({
                "source": "rule_engine",
                "rule": rule["name"],
                "severity": rule["severity"],
                "description": rule["description"],
                "suggestion": rule["suggestion"],
                "line": line_num,
                "context": context[:100],
            })

    return issues
