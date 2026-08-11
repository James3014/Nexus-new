"""Run the bounded provider-free fixture smoke benchmark."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SMOKE_CASES_FILE = Path(__file__).with_name("smoke_cases.json")
MAX_OUTPUT = 4096


def load_cases(mode: str, catalog: Path = SMOKE_CASES_FILE) -> list[dict[str, object]]:
    if mode != "smoke":
        raise ValueError("lite mode is intentionally unavailable for deterministic smoke")
    payload = json.loads(catalog.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or len(cases) != 5:
        raise ValueError("smoke catalog must contain exactly five cases")
    required = {"task_id", "fixture_kind", "verifier", "patch"}
    if any(not isinstance(case, dict) or set(case) != required for case in cases):
        raise ValueError("smoke cases must use the exact deterministic schema")
    task_ids = [case["task_id"] for case in cases]
    if any(not isinstance(task_id, str) or not task_id for task_id in task_ids):
        raise ValueError("smoke task ids must be non-empty strings")
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("smoke task ids must be unique")
    return cases


def _valid_result(result: object, expected_id: str) -> bool:
    if not isinstance(result, dict) or result.get("task_id") != expected_id:
        return False
    if result.get("passed") is not True or result.get("status") != "passed":
        return False
    digest = r"[0-9a-f]{64}"
    hashes_valid = all(
        re.fullmatch(digest, str(result.get(field)))
        for field in ("fixture_sha256", "patch_sha256", "verifier_sha256")
    )
    output = result.get("verifier_output", "")
    return hashes_valid and isinstance(output, str) and len(output) <= MAX_OUTPUT


def _classify_process(
    process: subprocess.CompletedProcess[str], expected_id: str
) -> dict[str, object]:
    try:
        result = json.loads(process.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"task_id": expected_id, "status": "error", "passed": False}
    if process.returncode != 0 or not _valid_result(result, expected_id):
        if not isinstance(result, dict):
            return {"task_id": expected_id, "status": "error", "passed": False}
        result["passed"] = False
        result["status"] = "error"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["smoke"], default="smoke")
    parser.add_argument("--output", default="ci_benchmark_results.jsonl")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args(argv)
    cases = load_cases(args.mode)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="codex-dx-fixtures-") as temp_root:
        for case in cases:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).parent / "run_benchmark_case.py"),
                    "--case",
                    json.dumps(case),
                    "--root",
                    temp_root,
                    "--timeout",
                    str(args.timeout),
                ],
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
            result = _classify_process(proc, str(case["task_id"]))
            results.append(result)
            print(f"{result.get('task_id')}: {result.get('status')}", flush=True)
    with output.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, sort_keys=True) + "\n")
    passed = sum(bool(result.get("passed")) for result in results)
    print(f"Final: {passed}/{len(results)} passed")
    return 0 if passed == len(results) and results else 1


if __name__ == "__main__":
    raise SystemExit(main())
