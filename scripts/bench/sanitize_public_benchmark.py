from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ALLOWED_TASK_KEYS = {
    "id",
    "category",
    "difficulty",
    "repo_kind",
    "repo",
    "repo_ref",
    "task_desc",
    "fixture_kind",
    "success_criteria",
    "mutation_required",
    "setup_command",
    "verification_command",
    "expected_capabilities",
    "capability_activation_contract",
    "hidden_oracle_kind",
    "public_claim_allowed_metrics",
}

EXECUTION_TASK_KEYS = ALLOWED_TASK_KEYS | {
    "cost_budget",
    "token_budget",
    "wall_time_budget_sec",
}


def _sanitize_repo(value: Any) -> str:
    text = str(value or "")
    if text.startswith("fixture://"):
        return text
    return "fixture://sanitized"


def _base_task(row: dict[str, Any], *, allowed_keys: set[str]) -> dict[str, Any]:
    task = {key: row[key] for key in sorted(allowed_keys) if key in row}
    task["repo"] = _sanitize_repo(task.get("repo"))
    return task


def sanitize_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    tasks = []
    for row in payload.get("tasks", []) or []:
        if not isinstance(row, dict):
            continue
        tasks.append(_base_task(row, allowed_keys=ALLOWED_TASK_KEYS))
    return {
        "schema": "nexus_public_benchmark_sanitized_manifest_v1",
        "source_schema": payload.get("schema", ""),
        "sanitization": {
            "removed_fields": ["allowed_files", "forbidden_files"],
            "local_paths_removed": True,
            "workspace_paths_removed": True,
            "fixture_only": True,
        },
        "tasks": tasks,
    }


def sanitize_execution_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    tasks = []
    for row in payload.get("tasks", []) or []:
        if not isinstance(row, dict):
            continue
        task = _base_task(row, allowed_keys=EXECUTION_TASK_KEYS)
        task["allowed_files"] = ["target.py", "test_target.py"]
        if "README.md" in row.get("allowed_files", []) or "README.md" in str(row.get("task_desc", "")):
            task["allowed_files"].insert(1, "README.md")
        task["forbidden_files"] = []
        tasks.append(task)
    return {
        "version": payload.get("version", "public-execution-v1"),
        "frozen": True,
        "benchmark_id": str(payload.get("benchmark_id", "nexus-public-benchmark")) + "-execution-safe",
        "description": str(payload.get("description", "")),
        "schema": "nexus_public_benchmark_execution_safe_manifest_v1",
        "source_schema": payload.get("schema", ""),
        "sanitization": {
            "local_paths_removed": True,
            "workspace_paths_removed": True,
            "fixture_only": True,
            "file_scope": "public_fixture_files_only",
        },
        "tasks": tasks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a public/sanitized benchmark task manifest.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", choices=["disclosure", "execution"], default="disclosure")
    args = parser.parse_args()
    src = Path(args.input)
    out = Path(args.output)
    payload = json.loads(src.read_text(encoding="utf-8"))
    sanitized = sanitize_execution_manifest(payload) if args.mode == "execution" else sanitize_manifest(payload)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sanitized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
