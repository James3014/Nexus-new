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


def _sanitize_repo(value: Any) -> str:
    text = str(value or "")
    if text.startswith("fixture://"):
        return text
    return "fixture://sanitized"


def sanitize_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    tasks = []
    for row in payload.get("tasks", []) or []:
        if not isinstance(row, dict):
            continue
        task = {key: row[key] for key in sorted(ALLOWED_TASK_KEYS) if key in row}
        task["repo"] = _sanitize_repo(task.get("repo"))
        task.pop("allowed_files", None)
        task.pop("forbidden_files", None)
        tasks.append(task)
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a public/sanitized benchmark task manifest.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    src = Path(args.input)
    out = Path(args.output)
    sanitized = sanitize_manifest(json.loads(src.read_text(encoding="utf-8")))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sanitized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
