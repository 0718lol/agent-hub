"""Run with: python -m app.scripts.preflight --profile deployment"""

import argparse
import asyncio
import json

from app.core.preflight import run_preflight


def main() -> int:
    parser = argparse.ArgumentParser(description="Check AgentHub deployment readiness")
    parser.add_argument(
        "--profile", choices=("core", "deployment", "production"), default="core"
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    result = asyncio.run(run_preflight(args.profile))
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        labels = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
        print(f"AgentHub preflight ({result['profile']}): {'READY' if result['ready'] else 'BLOCKED'}")
        for check in result["checks"]:
            print(f"[{labels[check['status']]}] {check['label']}: {check['detail']}")
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
