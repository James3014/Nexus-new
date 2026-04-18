#!/usr/bin/env python3
import sys
import json
import argparse
import subprocess
from pathlib import Path
from typing import Dict, Any, List

# 🛡️ Nexus Closeout Guard (Hard-Gate Enforcement)
# [NEXUS CONFIG: FAIL-CLOSED RELEASE CONTRACT]

def _git_head_short(cwd: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(cwd)).decode().strip()
    except Exception:
        return ""


def validate_contract(contract_path: Path, *, require_head_match: bool = True) -> Dict[str, Any]:
    if not contract_path.exists():
        return {
            "ok": False,
            "error": f"Contract file missing: {contract_path}",
            "details": {}
        }
    
    try:
        with open(contract_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return {
            "ok": False,
            "error": f"Invalid JSON in contract: {str(e)}",
            "details": {}
        }

    required_fields = [
        "linter_exit_code",
        "ci_gate_exit_code",
        "required_tests_passed",
        "commit_sha",
        "changed_files"
    ]
    
    missing = [f for f in required_fields if f not in data]
    if missing:
        return {
            "ok": False,
            "error": f"Missing required fields: {', '.join(missing)}",
            "details": data
        }

    expected_sha = str(data.get("commit_sha") or "").strip()
    current_sha = _git_head_short(contract_path.parent)

    checks = {
        "linter_ok": data.get("linter_exit_code") == 0,
        "ci_gate_ok": data.get("ci_gate_exit_code") == 0,
        "tests_ok": data.get("required_tests_passed") is True,
        "commit_ok": bool(expected_sha) if not require_head_match else (bool(current_sha) and current_sha == expected_sha),
        "files_ok": isinstance(data.get("changed_files"), list) and len(data.get("changed_files")) > 0
    }
    
    all_ok = all(checks.values())
    
    if require_head_match and not checks["commit_ok"]:
        print(f"❌ SHA MISMATCH: current={current_sha or 'unknown'}, expected={expected_sha}", file=sys.stderr)

    return {
        "ok": all_ok,
        "checks": checks,
        "details": {
            **data,
            "current_head_sha": current_sha,
            "require_head_match": require_head_match,
        },
    }

def main():
    parser = argparse.ArgumentParser(description="Nexus Closeout Hard-Gate Guard")
    parser.add_argument("--contract", type=str, default=".nexus/reports/done_contract.json",
                        help="Path to the done contract JSON file")
    parser.add_argument(
        "--require-head-match",
        dest="require_head_match",
        action="store_true",
        help="Require contract commit_sha to match current git HEAD.",
    )
    parser.add_argument(
        "--no-require-head-match",
        dest="require_head_match",
        action="store_false",
        help="Disable contract commit_sha to git HEAD enforcement.",
    )
    parser.set_defaults(require_head_match=True)
    args = parser.parse_args()

    contract_path = Path(args.contract)
    result = validate_contract(contract_path, require_head_match=bool(args.require_head_match))
    
    # Output machine-readable JSON
    print(json.dumps(result, indent=2))
    
    if result["ok"]:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
