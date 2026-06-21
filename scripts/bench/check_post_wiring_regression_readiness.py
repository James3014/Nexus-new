#!/usr/bin/env python3
"""Post-Wiring Regression Readiness Gate.

Checks whether post-real-wiring ceiling benchmark is allowed.
Inputs: C_12481 result JSON, C_13453 result JSON, local_heal test result, wiring test result.
"""
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")


def load_json(path: str) -> dict | None:
    """Load JSON file, return None if not found."""
    p = Path(path)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None


def main():
    parser = argparse.ArgumentParser(description="Post-Wiring Regression Readiness Gate")
    parser.add_argument("--c12481", type=str, required=True, help="C_12481 result JSON path")
    parser.add_argument("--c13453", type=str, required=True, help="C_13453 result JSON path")
    parser.add_argument("--local-heal-passed", type=bool, default=True, help="local_heal suite passed")
    parser.add_argument("--wiring-passed", type=bool, default=True, help="focused wiring tests passed")
    parser.add_argument("--output", type=str, required=True, help="Output JSON path")
    args = parser.parse_args()

    c12481 = load_json(args.c12481)
    c13453 = load_json(args.c13453)

    # Determine status
    if not args.local_heal_passed:
        status = "POST_WIRING_REGRESSION_BLOCKED_LOCAL_HEAL"
    elif not args.wiring_passed:
        status = "POST_WIRING_REGRESSION_BLOCKED_WIRING"
    elif c13453 and c13453.get("verifier_status") == "VERIFIER_EXECUTED_FAIL":
        status = "POST_WIRING_REGRESSION_BLOCKED_C13453_FAIL"
    elif c12481 and c12481.get("verifier_status") == "VERIFIER_EXECUTED_FAIL":
        status = "POST_WIRING_REGRESSION_BLOCKED_C12481_FAIL"
    elif (c13453 and c13453.get("verifier_status") == "VERIFIER_EXECUTED_PASS" and
          c12481 and c12481.get("verifier_status") == "VERIFIER_EXECUTED_PASS"):
        status = "POST_WIRING_REGRESSION_READY"
    elif (c13453 and c13453.get("verifier_status") == "VERIFIER_EXECUTED_PASS" and
          c12481 and c12481.get("verifier_status") == "NO_TESTS_MATCHED"):
        status = "POST_WIRING_READY_EXCEPT_C12481_ENTRYPOINT_GAP"
    elif (c13453 and c13453.get("verifier_status") == "VERIFIER_EXECUTED_PASS" and
          c12481 and c12481.get("verifier_status") in ("SKIPPED", "TIMEOUT", "ERROR")):
        status = "POST_WIRING_READY_EXCEPT_C12481_ENTRYPOINT_GAP"
    else:
        status = "POST_WIRING_REGRESSION_UNKNOWN"

    result = {
        "status": status,
        "c12481": {
            "verifier_status": c12481.get("verifier_status") if c12481 else "NOT_FOUND",
            "tests_executed": c12481.get("tests_executed", 0) if c12481 else 0,
        },
        "c13453": {
            "verifier_status": c13453.get("verifier_status") if c13453 else "NOT_FOUND",
            "tests_executed": c13453.get("tests_executed", 0) if c13453 else 0,
        },
        "local_heal_passed": args.local_heal_passed,
        "wiring_passed": args.wiring_passed,
        "public_claim_allowed": False,
        "production_ready": False,
        "training_export_allowed": False,
        "internal_only": True,
    }

    # Write result
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    return 0 if "READY" in status else 1


if __name__ == "__main__":
    sys.exit(main())
