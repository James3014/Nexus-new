#!/usr/bin/env python3
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List

# 🛡️ Nexus Closeout Guard (Hard-Gate Enforcement)
# [NEXUS CONFIG: FAIL-CLOSED RELEASE CONTRACT]

def validate_contract(contract_path: Path) -> Dict[str, Any]:
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

    # Validation logic
    checks = {
        "linter_ok": data.get("linter_exit_code") == 0,
        "ci_gate_ok": data.get("ci_gate_exit_code") == 0,
        "tests_ok": data.get("required_tests_passed") is True,
        "commit_ok": bool(data.get("commit_sha") and str(data.get("commit_sha")).strip()),
        "files_ok": isinstance(data.get("changed_files"), list) and len(data.get("changed_files")) > 0
    }
    
    all_ok = all(checks.values())
    
    return {
        "ok": all_ok,
        "checks": checks,
        "details": data
    }

def main():
    parser = argparse.ArgumentParser(description="Nexus Closeout Hard-Gate Guard")
    parser.add_argument("--contract", type=str, default=".nexus/reports/done_contract.json",
                        help="Path to the done contract JSON file")
    args = parser.parse_args()

    contract_path = Path(args.contract)
    result = validate_contract(contract_path)
    
    # Output machine-readable JSON
    print(json.dumps(result, indent=2))
    
    if result["ok"]:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
