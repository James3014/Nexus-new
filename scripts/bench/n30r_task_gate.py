"""N30R task eligibility gate.

Deterministically verifies each task: 3× original FAIL, 3× golden PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _run_verifier(source_code: str, verifier_command: tuple[str, ...], tmp_dir: str) -> int:
    """Write source to f.py and run verifier, return exit code."""
    src = os.path.join(tmp_dir, "f.py")
    with open(src, "w") as fh:
        fh.write(source_code)
    result = subprocess.run(
        list(verifier_command),
        capture_output=True,
        text=True,
        cwd=tmp_dir,
        timeout=30,
    )
    return result.returncode


def gate_task(task: dict, repetitions: int = 3) -> dict:
    """Run gate checks on a single task."""
    fixture_path = Path(task["fixture_path"])
    mod = {}
    exec(fixture_path.read_text(), mod)

    original_code = mod["ORIGINAL"]
    golden_code = mod["GOLDEN"]
    verifier = tuple(mod["VERIFIER"])
    expected_failure = mod["EXPECTED_FAILURE"]

    original_exit_codes = []
    original_failure_sigs = []
    golden_exit_codes = []

    all_pass = True

    for _ in range(repetitions):
        with tempfile.TemporaryDirectory() as td:
            ec = _run_verifier(original_code, verifier, td)
            original_exit_codes.append(ec)
            if ec == 0:
                all_pass = False
            original_failure_sigs.append(expected_failure if ec != 0 else "none")

    for _ in range(repetitions):
        with tempfile.TemporaryDirectory() as td:
            ec = _run_verifier(golden_code, verifier, td)
            golden_exit_codes.append(ec)
            if ec != 0:
                all_pass = False

    source_sha = _sha256(original_code)
    golden_sha = _sha256(golden_code)
    verifier_sha = _sha256(json.dumps(list(verifier)))
    env_sha = _sha256(f"python3:{sys.version}")
    bundle_sha = _sha256(f"{source_sha}:{verifier_sha}:{env_sha}")

    ineligibility = []
    if not all(original_exit_codes):
        ineligibility.append("original_does_not_fail")
    if not all(ec == 0 for ec in golden_exit_codes):
        ineligibility.append("golden_does_not_pass")
    if len(set(original_exit_codes)) > 1:
        ineligibility.append("flaky_original")
    if len(set(golden_exit_codes)) > 1:
        ineligibility.append("flaky_golden")

    return {
        "task_id": task["task_id"],
        "original_exit_codes": original_exit_codes,
        "original_failure_signatures": original_failure_sigs,
        "golden_exit_codes": golden_exit_codes,
        "source_sha256": source_sha,
        "golden_patch_sha256": golden_sha,
        "verifier_contract_sha256": verifier_sha,
        "environment_sha256": env_sha,
        "task_bundle_sha256": bundle_sha,
        "eligible": len(ineligibility) == 0,
        "ineligibility_reasons": ineligibility,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    receipts = []
    for task in manifest["tasks"]:
        receipt = gate_task(task, repetitions=args.repetitions)
        receipts.append(receipt)
        status = "ELIGIBLE" if receipt["eligible"] else f"INELIGIBLE: {receipt['ineligibility_reasons']}"
        print(f"  {receipt['task_id']}: {status}")

    Path(args.output).write_text(
        json.dumps(receipts, indent=2) if args.output.endswith(".json")
        else "\n".join(json.dumps(r) for r in receipts)
    )
    eligible = sum(1 for r in receipts if r["eligible"])
    print(f"\n  Eligible: {eligible}/{len(receipts)}")


if __name__ == "__main__":
    main()
