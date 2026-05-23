from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Mapping


Sha256File = Callable[[Path], str]
GitCommitProvider = Callable[[Path], str]
DirectGeminiTimeout = Callable[[int], int]


def build_artifact_file_manifest(
    rows: list[dict[str, Any]],
    *,
    sha256_file: Sha256File,
) -> list[dict[str, str]]:
    artifact_files: list[dict[str, str]] = []
    for row in rows:
        for key in ("evidence_record_file", "evidence_diff_file"):
            value = row.get(key)
            if not value:
                continue
            path = Path(str(value))
            if path.exists():
                artifact_files.append({"path": str(path), "sha256": sha256_file(path)})
    return artifact_files


def build_run_identity(
    *,
    runner_command: str,
    cwd: Path,
    git_commit_provider: GitCommitProvider,
) -> dict[str, str]:
    return {
        "nexus_git_commit": git_commit_provider(cwd),
        "runner": "scripts/bench/capability_ab_runner.py",
        "runner_command": str(runner_command or ""),
        "cwd": str(cwd),
    }


def build_task_manifest(config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": str(config.get("tasks_file") or ""),
        "sha256": str(config.get("tasks_manifest_hash") or ""),
        "unique_tasks_requested": int(config.get("unique_tasks_requested", 0) or 0),
        "repeat_trials": int(config.get("repeat_trials", 1) or 1),
        "shuffle_seed": config.get("shuffle_seed"),
    }


def build_timeout_manifest(
    config: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
    direct_gemini_timeout_sec: DirectGeminiTimeout,
) -> dict[str, Any]:
    environ = environ if environ is not None else os.environ
    timeout_sec = int(config.get("timeout_sec", 0) or 0)
    return {
        "timeout_sec": timeout_sec,
        "total_timeout_sec": int(config.get("total_timeout_sec", 0) or 0),
        "effective_total_timeout_sec": int(config.get("effective_total_timeout_sec", 0) or 0),
        "stop_loss_sec": int(config.get("stop_loss_sec", 0) or 0),
        "per_task_stop_loss_sec": int(config.get("per_task_stop_loss_sec", 0) or 0),
        "gateway_timeout_sec_policy": str(environ.get("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC") or ""),
        "direct_gemini_timeout_sec": direct_gemini_timeout_sec(timeout_sec),
    }


def build_raw_file_manifest(
    *,
    with_path: Path,
    without_path: Path,
    sha256_file: Sha256File,
) -> dict[str, dict[str, str]]:
    return {
        "with_nexus": {"path": str(with_path), "sha256": sha256_file(with_path)},
        "without_nexus": {"path": str(without_path), "sha256": sha256_file(without_path)},
    }
