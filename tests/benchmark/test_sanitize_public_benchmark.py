from __future__ import annotations

from scripts.bench.sanitize_public_benchmark import sanitize_manifest


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
