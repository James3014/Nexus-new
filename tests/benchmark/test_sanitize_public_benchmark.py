from __future__ import annotations

from scripts.bench.sanitize_public_benchmark import sanitize_execution_manifest, sanitize_manifest


def test_sanitize_manifest_removes_local_file_scope_and_keeps_public_contract() -> None:
    payload = {
        "schema": "source",
        "tasks": [
            {
                "id": "task-1",
                "repo": "/Users/example/private/repo",
                "task_desc": "Fix public fixture behavior.",
                "allowed_files": ["target.py"],
                "forbidden_files": ["/Users/example/private/.nexus"],
                "expected_capabilities": ["claim_gate"],
                "hidden_oracle_kind": "semantic_fixture",
            }
        ],
    }

    out = sanitize_manifest(payload)
    task = out["tasks"][0]

    assert out["schema"] == "nexus_public_benchmark_sanitized_manifest_v1"
    assert task["repo"] == "fixture://sanitized"
    assert "allowed_files" not in task
    assert "forbidden_files" not in task
    assert task["expected_capabilities"] == ["claim_gate"]


def test_sanitize_execution_manifest_keeps_runner_contract_without_private_scope() -> None:
    payload = {
        "version": "v1",
        "benchmark_id": "bench",
        "description": "demo",
        "tasks": [
            {
                "id": "task-1",
                "category": "bugfix",
                "difficulty": "hard",
                "repo_kind": "neutral_fixture",
                "repo": "/Users/example/private/repo",
                "repo_ref": "abc123",
                "task_desc": "Fix public fixture behavior and README.md.",
                "fixture_kind": "nexus_value_hidden_state",
                "success_criteria": "patch_and_tests_pass",
                "mutation_required": True,
                "allowed_files": ["target.py", "README.md", "/Users/example/private.py"],
                "forbidden_files": ["/Users/example/private/.nexus"],
                "setup_command": "python -m pytest --version",
                "verification_command": "python -m pytest -q test_target.py",
            }
        ],
    }

    out = sanitize_execution_manifest(payload)
    task = out["tasks"][0]

    assert out["schema"] == "nexus_public_benchmark_execution_safe_manifest_v1"
    assert out["frozen"] is True
    assert task["repo"] == "fixture://sanitized"
    assert task["allowed_files"] == ["target.py", "README.md", "test_target.py"]
    assert task["forbidden_files"] == []
