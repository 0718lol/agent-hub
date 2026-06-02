"""Unit tests for quality_gate.evaluate and quality_standards rules.

Pure logic tests: no LLM calls, no database, no network.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.quality_gate import QualityGate
from app.core.quality_standards import (
    _check_code_not_empty,
    _check_doc_has_structure,
    _check_html_structure,
    _check_no_fluff,
    _check_no_placeholder,
    _check_python_has_error_handling,
    detect_output_type,
    run_rules,
)


class TestCheckNoPlaceholder:
    def test_clean_code_passes(self):
        result = _check_no_placeholder("def foo():\n    return 42")
        assert result.passed is True

    def test_ellipsis_fails(self):
        result = _check_no_placeholder("def foo():\n    ...")
        assert result.passed is False

    def test_todo_fails(self):
        result = _check_no_placeholder("# TODO: implement this")
        assert result.passed is False

    def test_fixme_fails(self):
        result = _check_no_placeholder("# FIXME: broken")
        assert result.passed is False

    def test_chinese_placeholder_fails(self):
        result = _check_no_placeholder("here is ... placeholder")
        assert result.passed is False


class TestCheckHtmlStructure:
    def test_valid_html_passes(self):
        html = "<!DOCTYPE html><html><head></head><body></body></html>"
        result = _check_html_structure(html)
        assert result.passed is True

    def test_missing_body_fails(self):
        html = "<!DOCTYPE html><html><head></head></html>"
        result = _check_html_structure(html)
        assert result.passed is False

    def test_bare_div_fails(self):
        html = "<div>just a div</div>"
        result = _check_html_structure(html)
        assert result.passed is False


class TestCheckCodeNotEmpty:
    def test_substantial_code_passes(self):
        code = "line1\nline2\nline3\nline4\nline5"
        result = _check_code_not_empty(code)
        assert result.passed is True

    def test_too_few_lines_fails(self):
        code = "# comment\n// another"
        result = _check_code_not_empty(code)
        assert result.passed is False

    def test_empty_string_fails(self):
        result = _check_code_not_empty("")
        assert result.passed is False


class TestCheckPythonErrorHandling:
    def test_no_functions_passes(self):
        code = "x = 1\ny = 2\nprint(x + y)"
        result = _check_python_has_error_handling(code)
        assert result.passed is True

    def test_multiple_functions_no_try_fails(self):
        code = "def foo():\n    return 1\ndef bar():\n    return 2"
        result = _check_python_has_error_handling(code)
        assert result.passed is False

    def test_multiple_functions_with_try_passes(self):
        code = "def foo():\n    try:\n        return 1\n    except:\n        pass\ndef bar():\n    return 2"
        result = _check_python_has_error_handling(code)
        assert result.passed is True


class TestCheckNoFluff:
    def test_clean_text_passes(self):
        result = _check_no_fluff("A simple technical description.")
        assert result.passed is True


class TestCheckDocStructure:
    def test_structured_doc_passes(self):
        doc = "# Title\n\nSome text.\n\n- Item 1\n- Item 2"
        result = _check_doc_has_structure(doc)
        assert result.passed is True

    def test_long_unstructured_text_fails(self):
        text = "A" * 300
        result = _check_doc_has_structure(text)
        assert result.passed is False


class TestDetectOutputType:
    def test_html_content(self):
        text = "<!DOCTYPE html><html><body><h1>Hello</h1></body></html>"
        assert detect_output_type(text) == "html"

    def test_python_content(self):
        text = "import os\ndef main():\n    pass"
        assert detect_output_type(text) == "python"

    def test_document_content(self):
        text = "# Title\n\n" + "Paragraph. " * 50
        assert detect_output_type(text) == "document"

    def test_general_fallback(self):
        text = "Just some plain text"
        assert detect_output_type(text) == "general"

    def test_frontend_agent_with_html(self):
        text = "<div>x</div>"
        assert detect_output_type(text, "agent_frontend") == "html"

    def test_backend_agent_with_fastapi(self):
        text = "from fastapi import APIRouter\n@router.get('/')"
        assert detect_output_type(text, "agent_backend") == "api"

    def test_tester_agent(self):
        assert detect_output_type("any text", "agent_tester") == "python"


class TestRunRules:
    def test_good_html_scores_high(self):
        html = (
            "<!DOCTYPE html>\n<html>\n<head>\n"
            '<meta name="viewport" content="width=device-width">\n'
            "<style>body{margin:0}</style>\n"
            "</head>\n<body>\n<div>Hello</div>\n</body>\n</html>"
        )
        report = run_rules(html, "html")
        assert report.score >= 0.7
        assert report.passed is True

    def test_bad_html_fails(self):
        html = "<div>...</div>"
        report = run_rules(html, "html")
        assert report.passed is False

    def test_good_python_passes(self):
        code = "import os\nimport sys\nimport json\ndef main():\n    try:\n        pass\n    except:\n        pass"
        report = run_rules(code, "python")
        assert report.passed is True

    def test_placeholder_code_fails(self):
        code = "def foo():\n    ...\ndef bar():\n    # TODO"
        report = run_rules(code, "python")
        assert report.passed is False

    def test_general_type(self):
        text = "Some general text without fluff"
        report = run_rules(text, "general")
        assert report.output_type == "general"
        assert report.score > 0

    def test_report_has_results(self):
        code = "x = 1\ny = 2\nz = 3"
        report = run_rules(code, "python")
        assert len(report.results) > 0

    def test_empty_type_defaults_to_general(self):
        report = run_rules("test text", "unknown_type")
        assert report.output_type == "unknown_type"


class TestQualityGateEvaluate:
    def setup_method(self):
        self.gate = QualityGate(enabled=True)

    def test_disabled_gate_returns_pass(self):
        gate = QualityGate(enabled=False)
        report = gate.evaluate("anything")
        assert report.passed is True
        assert report.score == 1.0

    def test_empty_text_passes(self):
        report = self.gate.evaluate("")
        assert report.passed is True

    def test_code_block_evaluation(self):
        html_code = (
            "<!DOCTYPE html>\n<html>\n<head>\n"
            '<meta name="viewport" content="width=device-width">\n'
            "<style>body{}</style>\n</head>\n"
            "<body>\n<div>Hello</div>\n</body>\n</html>"
        )
        text = "`html\n" + html_code + "\n`"
        report = self.gate.evaluate(text, "agent_frontend")
        assert report.passed is True

    def test_bad_code_block_fails(self):
        text = "`html\n<div>...</div>\n`"
        report = self.gate.evaluate(text)
        assert report.passed is False

    def test_multiple_code_blocks_worst_score(self):
        html_good = (
            "<!DOCTYPE html>\n<html>\n<head>\n"
            '<meta name="viewport" content="width=device-width">\n'
            "<style>a{}</style>\n</head>\n"
            "<body>\n<div>x</div>\n</body>\n</html>"
        )
        text = "`html\n" + html_good + "\n`\n`python\n...\n`"
        report = self.gate.evaluate(text)
        assert report.score < 1.0

    def test_plain_text_evaluated_as_general(self):
        text = "This is plain text output without code blocks"
        report = self.gate.evaluate(text)
        assert report.output_type == "general"

    def test_lang_to_type_mapping(self):
        assert QualityGate._lang_to_type("html") == "html"
        assert QualityGate._lang_to_type("python") == "python"
        assert QualityGate._lang_to_type("py") == "python"
        assert QualityGate._lang_to_type("unknown") == ""
