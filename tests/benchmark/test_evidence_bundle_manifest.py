from __future__ import annotations

from pathlib import Path

from scripts.bench.evidence_bundle_manifest import (
    build_artifact_file_manifest,
    build_raw_file_manifest,
    build_run_identity,
    build_task_manifest,
    build_timeout_manifest,
)


def test_build_artifact_file_manifest_uses_existing_record_and_diff_files(tmp_path: Path):
    record = tmp_path / "record.json"
    diff = tmp_path / "diff.patch"
    missing = tmp_path / "missing.json"
    record.write_text("record", encoding="utf-8")
    diff.write_text("diff", encoding="utf-8")

    manifest = build_artifact_file_manifest(
        [
            {
                "evidence_record_file": str(record),
                "evidence_diff_file": str(diff),
            },
            {
                "evidence_record_file": str(missing),
                "evidence_diff_file": "",
            },
        ],
        sha256_file=lambda path: f"sha:{path.name}",
    )

    assert manifest == [
        {"path": str(record), "sha256": "sha:record.json"},
        {"path": str(diff), "sha256": "sha:diff.patch"},
    ]


def test_build_run_identity_keeps_runner_and_cwd_metadata(tmp_path: Path):
    identity = build_run_identity(
        runner_command="uv run bench",
        cwd=tmp_path,
        git_commit_provider=lambda cwd: f"commit:{cwd.name}",
    )

    assert identity == {
        "nexus_git_commit": f"commit:{tmp_path.name}",
        "runner": "scripts/bench/capability_ab_runner.py",
        "runner_command": "uv run bench",
        "cwd": str(tmp_path),
    }


def test_build_task_manifest_preserves_existing_config_defaults():
    manifest = build_task_manifest(
        {
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "unique_tasks_requested": "2",
            "repeat_trials": "",
            "shuffle_seed": 7,
        }
    )

    assert manifest == {
        "path": "tasks.json",
        "sha256": "abc",
        "unique_tasks_requested": 2,
        "repeat_trials": 1,
        "shuffle_seed": 7,
    }


def test_build_timeout_manifest_uses_gateway_env_and_direct_timeout_policy():
    manifest = build_timeout_manifest(
        {
            "timeout_sec": "20",
            "total_timeout_sec": "60",
            "effective_total_timeout_sec": "55",
            "stop_loss_sec": "50",
            "per_task_stop_loss_sec": "10",
        },
        environ={"NEXUS_BENCH_GATEWAY_TIMEOUT_SEC": "17"},
        direct_gemini_timeout_sec=lambda timeout: timeout + 5,
    )

    assert manifest == {
        "timeout_sec": 20,
        "total_timeout_sec": 60,
        "effective_total_timeout_sec": 55,
        "stop_loss_sec": 50,
        "per_task_stop_loss_sec": 10,
        "gateway_timeout_sec_policy": "17",
        "direct_gemini_timeout_sec": 25,
    }


def test_build_raw_file_manifest_hashes_with_and_without_paths(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_path.write_text("with", encoding="utf-8")
    without_path.write_text("without", encoding="utf-8")

    manifest = build_raw_file_manifest(
        with_path=with_path,
        without_path=without_path,
        sha256_file=lambda path: f"sha:{path.name}",
    )

    assert manifest == {
        "with_nexus": {"path": str(with_path), "sha256": "sha:with.jsonl"},
        "without_nexus": {"path": str(without_path), "sha256": "sha:without.jsonl"},
    }
