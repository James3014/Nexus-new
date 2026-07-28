#!/usr/bin/env python3
"""
CueLine-to-Nexus Process Worker Entrypoint.

Reads exactly one JSON object from stdin representing a CueLine controller job task
and executes the canonical Nexus self-hosted CLI command (`nexus self-hosted ...`) via subprocess.
"""

import json
import os
import sys
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Set


ALLOWED_OPERATIONS = {
    "submit",
    "status",
    "wait",
    "list-actionable",
    "list_actionable",
    "approve",
    "integrate",
    "dispose",
    "cancel",
}


OPERATION_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "submit": {
        "allowed": {
            "op", "operation", "task_id", "what", "why",
            "controller_revision", "target_base_revision",
            "controller_repo_root", "target_repo_root", "target_worktree_root",
            "allowed_files", "forbidden_files", "verifier_commands", "protected_contracts",
            "worker", "state_dir",
        },
        "required": set(),
    },
    "status": {
        "allowed": {"op", "operation", "task_id", "state_dir"},
        "required": {"task_id"},
    },
    "wait": {
        "allowed": {"op", "operation", "task_id", "timeout", "timeout_seconds", "poll_interval", "poll_interval_seconds", "state_dir"},
        "required": {"task_id"},
    },
    "list-actionable": {
        "allowed": {"op", "operation", "state_dir"},
        "required": set(),
    },
    "list_actionable": {
        "allowed": {"op", "operation", "state_dir"},
        "required": set(),
    },
    "approve": {
        "allowed": {
            "op", "operation", "task_id",
            "candidate_commit_sha", "candidate_tree_sha",
            "candidate_state_hash", "verified_receipt_hash",
            "state_dir",
        },
        "required": {
            "task_id", "candidate_commit_sha", "candidate_tree_sha",
            "candidate_state_hash", "verified_receipt_hash",
        },
    },
    "integrate": {
        "allowed": {"op", "operation", "task_id", "integration_branch", "state_dir"},
        "required": {"task_id"},
    },
    "dispose": {
        "allowed": {"op", "operation", "task_id", "disposition", "superseded_by", "state_dir"},
        "required": {"task_id", "disposition"},
    },
    "cancel": {
        "allowed": {"op", "operation", "task_id", "state_dir"},
        "required": {"task_id"},
    },
}


def resolve_repo_root() -> Path:
    env_root = os.environ.get("NEXUS_CUELINE_REPO_ROOT")
    if env_root:
        candidate = Path(env_root).resolve()
        cli_path = candidate / "scripts" / "engine" / "nexus_cli.py"
        if not cli_path.is_file():
            raise ValueError(f"NEXUS_CUELINE_REPO_ROOT path '{env_root}' is not a valid Nexus repository checkout.")
        return candidate

    default_root = Path(__file__).resolve().parents[2]
    cli_path = default_root / "scripts" / "engine" / "nexus_cli.py"
    if not cli_path.is_file():
        raise ValueError(f"Default resolved repo root '{default_root}' is not a valid Nexus repository checkout.")
    return default_root


def _validate_field_type(key: str, val: Any) -> None:
    if key in {
        "task_id", "what", "why", "controller_revision", "target_base_revision",
        "controller_repo_root", "target_repo_root", "target_worktree_root",
        "worker", "state_dir", "candidate_commit_sha", "candidate_tree_sha",
        "candidate_state_hash", "verified_receipt_hash", "integration_branch",
        "disposition", "superseded_by", "op", "operation",
    }:
        if not isinstance(val, str):
            raise TypeError(f"Field '{key}' must be a string, got {type(val).__name__}.")
    elif key in {"allowed_files", "forbidden_files", "verifier_commands", "protected_contracts"}:
        if isinstance(val, str):
            pass
        elif isinstance(val, list):
            if not all(isinstance(item, str) for item in val):
                raise TypeError(f"List items in '{key}' must all be strings.")
        else:
            raise TypeError(f"Field '{key}' must be a string or list of strings, got {type(val).__name__}.")
    elif key in {"timeout", "timeout_seconds", "poll_interval", "poll_interval_seconds"}:
        if isinstance(val, (int, float)):
            pass
        elif isinstance(val, str):
            try:
                float(val)
            except ValueError:
                raise TypeError(f"Field '{key}' must be numeric, got string '{val}'.")
        else:
            raise TypeError(f"Field '{key}' must be numeric (int/float), got {type(val).__name__}.")


def parse_and_validate_input(raw_input: str) -> Dict[str, Any]:
    if not raw_input or not raw_input.strip():
        raise ValueError("Empty input provided. Exactly one JSON object is required on stdin.")

    try:
        data = json.loads(raw_input)
    except Exception as exc:
        raise ValueError(f"Invalid JSON object on stdin: {exc}") from exc

    if not isinstance(data, dict):
        raise TypeError(f"Input payload must be a JSON object, got {type(data).__name__}.")

    op = data.get("op") or data.get("operation")
    if not op or not isinstance(op, str):
        raise ValueError("JSON payload missing valid 'op' or 'operation' string field.")

    op_norm = op.lower()
    if op_norm not in ALLOWED_OPERATIONS:
        raise ValueError(f"Unknown operation '{op}'. Allowed operations: {sorted(list(ALLOWED_OPERATIONS))}")

    schema_op = "list-actionable" if op_norm in {"list-actionable", "list_actionable"} else op_norm
    schema = OPERATION_SCHEMAS[schema_op]

    input_keys = set(data.keys())
    unknown_keys = input_keys - schema["allowed"]
    if unknown_keys:
        raise ValueError(f"Unknown field(s) for operation '{op}': {sorted(list(unknown_keys))}")

    for req_key in schema["required"]:
        if req_key not in data or data[req_key] is None:
            raise ValueError(f"Missing required field '{req_key}' for operation '{op}'.")

    for k, v in data.items():
        if v is not None:
            _validate_field_type(k, v)

    if schema_op == "dispose":
        disp = str(data["disposition"]).upper()
        if disp not in {"REJECTED", "SUPERSEDED"}:
            raise ValueError(f"Invalid disposition '{data['disposition']}'. Must be REJECTED or SUPERSEDED.")

    return data


def build_cli_argv(data: Dict[str, Any], repo_root: Path | None = None) -> List[str]:
    op = data.get("op") or data.get("operation")
    op_norm = str(op).lower()
    cli_op = "list-actionable" if op_norm in {"list-actionable", "list_actionable"} else op_norm

    argv = [sys.executable, "-m", "scripts.engine.nexus_cli", "self-hosted", cli_op]

    def _add_str_opt(flag: str, key: str):
        val = data.get(key)
        if val is not None:
            argv.extend([flag, str(val)])

    def _add_csv_opt(flag: str, key: str):
        val = data.get(key)
        if val is not None:
            if isinstance(val, list):
                csv_str = ",".join(val)
            else:
                csv_str = str(val)
            argv.extend([flag, csv_str])

    if cli_op == "submit":
        _add_str_opt("--task-id", "task_id")
        _add_str_opt("--what", "what")
        _add_str_opt("--why", "why")
        _add_str_opt("--controller-revision", "controller_revision")
        _add_str_opt("--target-base-revision", "target_base_revision")
        _add_str_opt("--controller-repo-root", "controller_repo_root")
        _add_str_opt("--target-repo-root", "target_repo_root")
        _add_str_opt("--target-worktree-root", "target_worktree_root")
        _add_csv_opt("--allowed-files", "allowed_files")
        _add_csv_opt("--forbidden-files", "forbidden_files")
        _add_csv_opt("--verifier-commands", "verifier_commands")
        _add_csv_opt("--protected-contracts", "protected_contracts")
        _add_str_opt("--worker", "worker")
        _add_str_opt("--state-dir", "state_dir")

    elif cli_op == "status":
        _add_str_opt("--task-id", "task_id")
        _add_str_opt("--state-dir", "state_dir")

    elif cli_op == "wait":
        _add_str_opt("--task-id", "task_id")
        timeout_val = data.get("timeout") or data.get("timeout_seconds")
        if timeout_val is not None:
            argv.extend(["--timeout", str(timeout_val)])
        poll_val = data.get("poll_interval") or data.get("poll_interval_seconds")
        if poll_val is not None:
            argv.extend(["--poll-interval", str(poll_val)])
        _add_str_opt("--state-dir", "state_dir")

    elif cli_op == "list-actionable":
        _add_str_opt("--state-dir", "state_dir")

    elif cli_op == "approve":
        _add_str_opt("--task-id", "task_id")
        _add_str_opt("--candidate-commit-sha", "candidate_commit_sha")
        _add_str_opt("--candidate-tree-sha", "candidate_tree_sha")
        _add_str_opt("--candidate-state-hash", "candidate_state_hash")
        _add_str_opt("--verified-receipt-hash", "verified_receipt_hash")
        _add_str_opt("--state-dir", "state_dir")

    elif cli_op == "integrate":
        _add_str_opt("--task-id", "task_id")
        _add_str_opt("--integration-branch", "integration_branch")
        _add_str_opt("--state-dir", "state_dir")

    elif cli_op == "dispose":
        _add_str_opt("--task-id", "task_id")
        _add_str_opt("--disposition", "disposition")
        _add_str_opt("--superseded-by", "superseded_by")
        _add_str_opt("--state-dir", "state_dir")

    elif cli_op == "cancel":
        _add_str_opt("--task-id", "task_id")
        _add_str_opt("--state-dir", "state_dir")

    return argv


def main() -> int:
    try:
        if len(sys.argv) > 1:
            raise ValueError(f"Extra positional command-line text is strictly rejected: {sys.argv[1:]}")

        raw_input = sys.stdin.read()
        validated_data = parse_and_validate_input(raw_input)
        repo_root = resolve_repo_root()
        argv = build_cli_argv(validated_data, repo_root=repo_root)

        env = os.environ.copy()
        if str(repo_root) not in env.get("PYTHONPATH", ""):
            existing_pp = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = f"{repo_root}:{existing_pp}" if existing_pp else str(repo_root)

        proc = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            env=env,
        )

        if proc.stdout:
            sys.stdout.write(proc.stdout)
            sys.stdout.flush()
        if proc.stderr:
            sys.stderr.write(proc.stderr)
            sys.stderr.flush()

        return proc.returncode

    except Exception as exc:
        err_msg = json.dumps({"error": str(exc), "status": "FAILED"}, ensure_ascii=False)
        sys.stderr.write(f"{err_msg}\n")
        sys.stderr.flush()
        return 1


if __name__ == "__main__":
    sys.exit(main())
