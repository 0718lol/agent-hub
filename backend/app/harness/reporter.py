"""Reporter — outputs evaluation results as JSON or console summary."""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO

from app.harness.evaluator import EvalReport


def format_console(reports: list[EvalReport], suite_name: str = "") -> str:
    """Format reports as a human-readable console summary."""
    lines = []
    header = f"=== Harness Eval: {suite_name} ===" if suite_name else "=== Harness Eval Report ==="
    lines.append(header)
    lines.append(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Cases: {len(reports)}")
    lines.append("")

    total_passed = 0
    total_score = 0.0

    for i, r in enumerate(reports, 1):
        status = "PASS" if r.passed else "FAIL"
        total_score += r.total_score
        if r.passed:
            total_passed += 1

        lines.append(f"  [{i}] {r.tool_name} | {status} | {r.total_score:.1f}/100")
        lines.append(f"      {r.input_summary}")
        for d in r.dimensions:
            bar = "=" * int(d.score / 10) + "-" * (10 - int(d.score / 10))
            lines.append(f"      {d.name:12s} [{bar}] {d.score:.1f} (x{d.weight:.0%}) {d.detail}")
        lines.append("")

    avg = total_score / len(reports) if reports else 0
    lines.append(f"Summary: {total_passed}/{len(reports)} passed, avg score: {avg:.1f}/100")
    return "\n".join(lines)


def reports_to_json(reports: list[EvalReport]) -> dict:
    """Convert reports to a JSON-serializable dict."""
    total_score = sum(r.total_score for r in reports) / len(reports) if reports else 0
    return {
        "timestamp": datetime.now().isoformat(),
        "total_cases": len(reports),
        "passed": sum(1 for r in reports if r.passed),
        "failed": sum(1 for r in reports if not r.passed),
        "average_score": round(total_score, 2),
        "cases": [r.to_dict() for r in reports],
    }


def write_json_report(reports: list[EvalReport], output_path: str | Path) -> Path:
    """Write reports to a JSON file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = reports_to_json(reports)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def print_report(reports: list[EvalReport], suite_name: str = "", file: TextIO = None):
    """Print console report to stdout or a file."""
    output = format_console(reports, suite_name)
    print(output, file=file or sys.stdout)


# ============================================================
# HTML Report
# ============================================================

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Harness Eval Report</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    background: #0f172a; color: #e2e8f0;
    margin: 0; padding: 24px;
    line-height: 1.5;
  }}
  .container {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{ color: #818cf8; margin-bottom: 4px; }}
  .meta {{ color: #94a3b8; font-size: 13px; margin-bottom: 24px; }}
  .summary {{
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
    margin-bottom: 24px;
  }}
  .stat {{
    background: #1e293b; border: 1px solid #334155;
    border-radius: 8px; padding: 16px;
  }}
  .stat-label {{ font-size: 12px; color: #94a3b8; text-transform: uppercase; }}
  .stat-value {{ font-size: 28px; font-weight: 700; color: #f1f5f9; margin-top: 4px; }}
  .stat-value.pass {{ color: #10b981; }}
  .stat-value.fail {{ color: #ef4444; }}
  .case {{
    background: #1e293b; border: 1px solid #334155;
    border-radius: 8px; padding: 16px; margin-bottom: 12px;
  }}
  .case-header {{
    display: flex; align-items: center; gap: 12px;
    margin-bottom: 12px;
  }}
  .badge {{
    padding: 2px 10px; border-radius: 4px; font-size: 12px; font-weight: 600;
  }}
  .badge.pass {{ background: rgba(16,185,129,0.15); color: #10b981; }}
  .badge.fail {{ background: rgba(239,68,68,0.15); color: #ef4444; }}
  .case-title {{ flex: 1; font-weight: 600; }}
  .case-score {{ font-size: 18px; font-weight: 700; }}
  .case-summary {{ color: #94a3b8; font-size: 13px; margin-bottom: 12px; }}
  .dim {{ margin: 6px 0; font-size: 13px; }}
  .dim-name {{ display: inline-block; width: 110px; color: #cbd5e1; }}
  .dim-bar {{
    display: inline-block; width: 200px; height: 8px;
    background: #0f172a; border-radius: 4px; vertical-align: middle;
    overflow: hidden; margin: 0 8px;
  }}
  .dim-bar-fill {{ height: 100%; background: linear-gradient(90deg, #6366f1, #818cf8); }}
  .dim-score {{ color: #f1f5f9; font-weight: 600; }}
  .dim-detail {{ color: #64748b; font-size: 11px; margin-left: 8px; }}
  .signals {{
    background: #0f172a; border-radius: 4px;
    padding: 8px 12px; font-size: 12px; color: #94a3b8;
    margin-top: 8px; font-family: Consolas, monospace;
  }}
</style>
</head>
<body>
<div class="container">
  <h1>Harness Eval Report</h1>
  <div class="meta">
    {meta}
  </div>
  <div class="summary">
    <div class="stat"><div class="stat-label">Total Cases</div><div class="stat-value">{total}</div></div>
    <div class="stat"><div class="stat-label">Passed</div><div class="stat-value pass">{passed}</div></div>
    <div class="stat"><div class="stat-label">Failed</div><div class="stat-value fail">{failed}</div></div>
    <div class="stat"><div class="stat-label">Avg Score</div><div class="stat-value">{avg}</div></div>
  </div>
  {cases_html}
</div>
</body>
</html>"""


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def format_html(reports: list[EvalReport], suite_name: str = "") -> str:
    """Render reports as an HTML page."""
    total = len(reports)
    passed = sum(1 for r in reports if r.passed)
    failed = total - passed
    avg = sum(r.total_score for r in reports) / total if total else 0

    meta = f"Suite: {_html_escape(suite_name)} | Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    case_blocks = []
    for r in reports:
        badge_class = "pass" if r.passed else "fail"
        badge_text = "PASS" if r.passed else "FAIL"

        dim_html = []
        for d in r.dimensions:
            bar_pct = max(0, min(100, d.score))
            dim_html.append(
                f'<div class="dim">'
                f'<span class="dim-name">{_html_escape(d.name)}</span>'
                f'<span class="dim-bar"><span class="dim-bar-fill" style="width:{bar_pct:.0f}%"></span></span>'
                f'<span class="dim-score">{d.score:.1f}</span>'
                f'<span class="dim-detail">x{d.weight:.0%} | {_html_escape(d.detail)}</span>'
                f'</div>'
            )

        signals_str = ", ".join(f"{k}={v}" for k, v in r.signals.items()) if r.signals else "(none)"

        case_blocks.append(
            f'<div class="case">'
            f'<div class="case-header">'
            f'<span class="badge {badge_class}">{badge_text}</span>'
            f'<span class="case-title">{_html_escape(r.tool_name)}</span>'
            f'<span class="case-score">{r.total_score:.1f}/100</span>'
            f'</div>'
            f'<div class="case-summary">{_html_escape(r.input_summary)}</div>'
            f'{"".join(dim_html)}'
            f'<div class="signals">signals: {_html_escape(signals_str)}</div>'
            f'</div>'
        )

    return _HTML_TEMPLATE.format(
        meta=meta, total=total, passed=passed, failed=failed,
        avg=f"{avg:.1f}", cases_html="".join(case_blocks),
    )


def write_html_report(reports: list[EvalReport], output_path: str | Path, suite_name: str = "") -> Path:
    """Write reports as an HTML file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    html = format_html(reports, suite_name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
