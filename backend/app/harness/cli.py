"""CLI entry point for the eval harness.

Usage:
    python -m app.harness.cli run --suite all
    python -m app.harness.cli run --suite interaction_judge
    python -m app.harness.cli list
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure backend/ is on sys.path so `app.*` imports work
_backend_dir = Path(__file__).resolve().parent.parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from app.harness.runner import HarnessRunner, list_suites, load_suite
from app.harness.reporter import print_report, write_json_report, write_html_report


async def cmd_run(args):
    """Run a test suite."""
    from app.core.llm_client import llm_client

    # Auto-configure LLM: prefer data/llm_config.json (same as main app), fallback to .env
    import json as _json
    import os
    config_path = _backend_dir / "data" / "llm_config.json"
    if not llm_client.is_configured() and config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = _json.load(f)
        llm_client.configure(
            provider=cfg.get("provider", "openai"),
            api_key=cfg.get("api_key", ""),
            base_url=cfg.get("base_url", ""),
            model=cfg.get("model", ""),
            temperature=cfg.get("temperature"),
            max_tokens=cfg.get("max_tokens"),
        )

    if not llm_client.is_configured():
        try:
            from dotenv import load_dotenv
            load_dotenv(_backend_dir / ".env")
        except ImportError:
            pass
        if not llm_client.is_configured():
            llm_client.configure(
                provider=os.getenv("LLM_PROVIDER", "openai"),
                api_key=os.getenv("LLM_API_KEY", ""),
                base_url=os.getenv("LLM_BASE_URL", ""),
                model=os.getenv("LLM_MODEL", ""),
            )

    runner = HarnessRunner(llm_client=llm_client)

    suite_name = args.suite
    if suite_name == "all":
        results = await runner.run_all()
        all_reports = []
        for name, reports in results.items():
            print_report(reports, suite_name=name)
            print()
            all_reports.extend(reports)
        if args.output:
            write_json_report(all_reports, args.output)
            print(f"\nJSON report saved to: {args.output}")
        if args.html:
            write_html_report(all_reports, args.html, suite_name="all")
            print(f"HTML report saved to: {args.html}")
    else:
        reports = await runner.run_suite(suite_name)
        print_report(reports, suite_name=suite_name)
        if args.output:
            write_json_report(reports, args.output)
            print(f"\nJSON report saved to: {args.output}")
        if args.html:
            write_html_report(reports, args.html, suite_name=suite_name)
            print(f"HTML report saved to: {args.html}")


def cmd_list(args):
    """List available test suites."""
    suites = list_suites()
    if not suites:
        print("No test suites found in backend/app/harness/samples/")
        return
    print(f"Available test suites ({len(suites)}):")
    for name in suites:
        cases = load_suite(name)
        print(f"  {name}  ({len(cases)} cases)")


def main():
    parser = argparse.ArgumentParser(description="AgentHub Eval Harness CLI")
    sub = parser.add_subparsers(dest="command")

    # run
    run_parser = sub.add_parser("run", help="Run test suite(s)")
    run_parser.add_argument("--suite", required=True, help="Suite name or 'all'")
    run_parser.add_argument("--output", "-o", help="JSON report output path")
    run_parser.add_argument("--html", help="HTML report output path")

    # list
    sub.add_parser("list", help="List available test suites")

    args = parser.parse_args()

    if args.command == "run":
        asyncio.run(cmd_run(args))
    elif args.command == "list":
        cmd_list(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
