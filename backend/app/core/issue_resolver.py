"""GitHub Issue auto-resolution engine."""
import logging
import os
import re

logger = logging.getLogger("issue_resolver")
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def parse_issue(issue):
    return {
        "title": issue.get("title", ""),
        "body": issue.get("body", "")[:2000],
        "labels": [l.get("name", "") if isinstance(l, dict) else str(l) for l in issue.get("labels", [])],
        "number": issue.get("number", 0),
        "url": issue.get("html_url", ""),
    }


def _keyword_localize(text):
    keywords = [w for w in text.lower().split() if len(w) >= 4]
    results = []
    for root, dirs, files in os.walk(PROJECT_ROOT):
        if any(s in root for s in ["node_modules", ".git", "__pycache__"]):
            continue
        for f in files:
            if not f.endswith((".py", ".jsx", ".js")):
                continue
            fp = os.path.join(root, f)
            try:
                with open(fp, "r", encoding="utf-8") as fh:
                    txt = fh.read(5000).lower()
                score = sum(1 for k in keywords if k in txt)
                if score >= 3:
                    results.append({"file": os.path.relpath(fp, PROJECT_ROOT), "function": None, "line": 1, "context": txt[:2000], "score": score})
            except Exception:
                pass
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results[:5]


async def localize_fault(text, llm_client=None):
    if not llm_client:
        return _keyword_localize(text)
    try:
        prompt = "Analyze this Issue, list relevant source files (max 5). Issue: " + text[:500] + ". Output file paths only, one per line."
        resp = ""
        async for c in llm_client.chat_stream([{"role": "user", "content": prompt}]):
            resp += c
        files = [f.strip() for f in resp.strip().split(chr(10)) if f.strip().endswith((".py", ".jsx", ".js"))]
        results = []
        for fp in files[:5]:
            full = os.path.join(PROJECT_ROOT, fp)
            if not os.path.exists(full):
                continue
            with open(full, "r", encoding="utf-8") as f:
                content = f.read()
            prompt2 = "In file " + fp + ", find function(s) related to: " + text[:200] + ". Output function names only, one per line."
            r2 = ""
            async for c in llm_client.chat_stream([{"role": "user", "content": prompt2}]):
                r2 += c
            funcs = [l.strip() for l in r2.strip().split(chr(10)) if l.strip() and not l.startswith("#")]
            for fn in funcs[:3]:
                for i, line in enumerate(content.split(chr(10)), 1):
                    if "def " + fn in line or "class " + fn in line:
                        lines_list = content.split(chr(10))
                        ctx = chr(10).join(lines_list[max(0, i - 21):min(len(lines_list), i + 20)])
                        results.append({"file": fp, "function": fn, "line": i, "context": ctx})
                        break
        return results if results else _keyword_localize(text)
    except Exception as e:
        logger.warning("Localization failed: " + str(e))
        return _keyword_localize(text)


async def resolve_issue(issue, llm_client=None):
    """Main entry: resolve a GitHub Issue automatically."""
    parsed = parse_issue(issue)
    text = parsed["title"] + chr(10) + parsed["body"]
    locations = await localize_fault(text, llm_client)
    if not locations:
        return {"status": "no_files_found", "message": "Cannot locate files"}
    fixes = []
    for loc in locations:
        fp = os.path.join(PROJECT_ROOT, loc["file"])
        if not os.path.exists(fp):
            continue
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        if not llm_client:
            continue
        prompt = "Issue: " + text[:500] + "\n\nFile: " + loc.get("file", "") + "\nContext:\n" + loc.get("context", "")[:2000] + "\n\nFix this issue. Output the complete fixed function code in a code block."
        resp = ""
        async for c in llm_client.chat_stream([{"role": "user", "content": prompt}]):
            resp += c
        code_match = re.search(r"```(?:python|jsx|js)?\n(.*?)```", resp, re.DOTALL)
        if code_match:
            fixed = code_match.group(1).strip()
            fixes.append({"file": loc.get("file"), "original": content, "fixed": fixed})
    if not fixes:
        return {"status": "no_fixes", "message": "Cannot generate fixes"}
    verified = []
    for fix in fixes:
        try:
            compile(fix["fixed"], fix["file"], "exec")
            verified.append(fix)
        except SyntaxError as e:
            logger.warning("Fix syntax error: " + str(e))
    if not verified:
        return {"status": "all_invalid", "message": "Fixes have syntax errors"}
    for fix in verified:
        fp = os.path.join(PROJECT_ROOT, fix["file"])
        with open(fp, "w", encoding="utf-8") as f:
            f.write(fix["fixed"])
    return {"status": "resolved", "issue": parsed, "fixes": len(verified), "files": [f["file"] for f in verified]}
