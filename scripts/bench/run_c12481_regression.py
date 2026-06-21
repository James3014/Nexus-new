#!/usr/bin/env python3
"""C_12481 Live Regression Entrypoint.

Executes actual local regression fixture for C_12481 (sympy__sympy-12481).
Does not depend on hardcoded expected patch.
Emits machine-readable result JSON.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
FIXTURE_DIR = REPO_ROOT / "artifacts" / "runtime" / "c4_7b_repair_v0" / "C_12481"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "runtime" / "ao2_live_regression_entrypoints_v0" / "c12481_regression_result.json"

TASK_ID = "C_12481"
INSTANCE_ID = "sympy__sympy-12481"
VERIFIER_COMMAND = "python -m pytest tests/unit/local_heal/test_runtime_evidence_graph.py::TestRegression::test_c_12481_still_passes -v"


def load_fixture() -> dict:
    """Load fixture data from existing artifact directory."""
    receipt_path = FIXTURE_DIR / "receipt.json"
    if not receipt_path.exists():
        return {"status": "LIVE_FIXTURE_UNAVAILABLE", "reason": f"receipt.json not found at {receipt_path}"}

    with open(receipt_path) as f:
        receipt = json.load(f)

    return {
        "status": "FIXTURE_LOADED",
        "task_id": receipt.get("task_id", TASK_ID),
        "instance_id": receipt.get("instance_id", INSTANCE_ID),
        "model": receipt.get("model", "unknown"),
        "gate_passed": receipt.get("gate_passed", False),
        "attempts": receipt.get("attempts", 0),
    }


def run_verifier() -> dict:
    """Run the verifier command and capture results."""
    import re
    start = time.monotonic()
    try:
        result = subprocess.run(
            VERIFIER_COMMAND,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(REPO_ROOT),
        )
        elapsed = time.monotonic() - start

        # Parse pytest output for test counts
        stdout = result.stdout or ""
        tests_collected = 0
        tests_executed = 0

        collected_match = re.search(r"collected (\d+)", stdout)
        if collected_match:
            tests_collected = int(collected_match.group(1))

        passed_match = re.search(r"(\d+) passed", stdout)
        if passed_match:
            tests_executed = int(passed_match.group(1))

        failed_match = re.search(r"(\d+) failed", stdout)
        if failed_match:
            tests_executed += int(failed_match.group(1))

        # Classify verifier status
        if tests_collected == 0:
            verifier_status = "NO_TESTS_MATCHED"
        elif result.returncode == 0:
            verifier_status = "VERIFIER_EXECUTED_PASS"
        else:
            verifier_status = "VERIFIER_EXECUTED_FAIL"

        return {
            "verifier_status": verifier_status,
            "return_code": result.returncode,
            "tests_collected": tests_collected,
            "tests_executed": tests_executed,
            "stdout_tail": stdout[-500:] if stdout else "",
            "stderr_tail": (result.stderr or "")[-500:],
            "elapsed_sec": round(elapsed, 2),
        }
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return {
            "verifier_status": "TIMEOUT",
            "return_code": -1,
            "tests_collected": 0,
            "tests_executed": 0,
            "stdout_tail": "",
            "stderr_tail": "Verifier command timed out after 60s",
            "elapsed_sec": round(elapsed, 2),
        }
    except Exception as exc:
        elapsed = time.monotonic() - start
        return {
            "verifier_status": "ERROR",
            "return_code": -2,
            "tests_collected": 0,
            "tests_executed": 0,
            "stdout_tail": "",
            "stderr_tail": str(exc)[:500],
            "elapsed_sec": round(elapsed, 2),
        }


def compute_source_hash() -> str:
    """Compute source hash of the fixture receipt."""
    import hashlib
    receipt_path = FIXTURE_DIR / "receipt.json"
    if receipt_path.exists():
        content = receipt_path.read_bytes()
        return hashlib.sha256(content).hexdigest()[:16]
    return ""


def main():
    parser = argparse.ArgumentParser(description="C_12481 Live Regression Entrypoint")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT), help="Output JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Only load fixture, do not run verifier")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load fixture
    fixture = load_fixture()

    result = {
        "task_id": TASK_ID,
        "instance_id": INSTANCE_ID,
        "entrypoint_available": True,
        "fixture_status": fixture["status"],
        "verifier_command": VERIFIER_COMMAND,
        "source_hash": compute_source_hash(),
        "hardcoded_patch_used": False,
        "public_claim_allowed": False,
        "production_ready": False,
        "training_export_allowed": False,
        "internal_only": True,
    }

    if fixture["status"] == "LIVE_FIXTURE_UNAVAILABLE":
        result["verifier_status"] = "SKIPPED"
        result["verifier_detail"] = fixture["reason"]
        result["tests_collected"] = 0
        result["tests_executed"] = 0
    else:
        result["fixture_detail"] = fixture
        if not args.dry_run:
            verifier = run_verifier()
            result.update(verifier)
        else:
            result["verifier_status"] = "DRY_RUN"
            result["tests_collected"] = 0
            result["tests_executed"] = 0

    # Write result
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    return 0 if result.get("verifier_status") in (
        "VERIFIER_EXECUTED_PASS", "DRY_RUN", "SKIPPED"
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
