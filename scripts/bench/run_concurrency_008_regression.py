#!/usr/bin/env python3
"""concurrency_008 Live Regression Entrypoint.

Executes actual local regression fixture for concurrency_008.
Emits machine-readable result JSON.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "runtime" / "av_executable_benchmark_substrate_v0" / "execution_results" / "concurrency_008.json"

TASK_ID = "concurrency_008"
INSTANCE_ID = "nexus_internal_concurrency"
VERIFIER_COMMAND = "python -m pytest tests/unit/test_deepswe_tasks4_10.py::test_transaction_race -v"

def run_verifier() -> dict:
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

def main():
    parser = argparse.ArgumentParser(description="concurrency_008 Live Regression Entrypoint")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT), help="Output JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Only load fixture, do not run verifier")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "task_id": TASK_ID,
        "instance_id": INSTANCE_ID,
        "entrypoint_available": True,
        "fixture_status": "FIXTURE_LOADED",
        "verifier_command": VERIFIER_COMMAND,
        "source_hash": "local_restored_hash",
        "hardcoded_patch_used": False,
        "public_claim_allowed": False,
        "production_ready": False,
        "training_export_allowed": False,
        "internal_only": True,
    }

    if not args.dry_run:
        verifier = run_verifier()
        result.update(verifier)
    else:
        result["verifier_status"] = "DRY_RUN"
        result["tests_collected"] = 0
        result["tests_executed"] = 0

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))
    return 0 if result.get("verifier_status") in (
        "VERIFIER_EXECUTED_PASS", "DRY_RUN"
    ) else 1

if __name__ == "__main__":
    sys.exit(main())
