import json
from pathlib import Path

import pytest

from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService


def _request(tmp_path: Path, **overrides):
    values = {
        "task_id": "mcp-task-001",
        "what": "Add one bounded canary test",
        "why": "Prove the MCP request becomes a governed task",
        "controller_revision": "a" * 40,
        "target_base_revision": "b" * 40,
        "controller_repo_root": str(tmp_path / "controller"),
        "target_repo_root": str(tmp_path / "targets" / "mcp-task-001"),
        "target_worktree_root": str(tmp_path / "targets"),
        "allowed_files": ["nexus_canary.txt"],
        "forbidden_files": ["nexus/orchestrator/"],
        "verifier_commands": ["python3 -c 'print(\"pass\")'"],
        "protected_contracts": ["candidate-receipt-v1"],
        "worker": "codex",
    }
    values.update(overrides)
    return values


def test_what_why_are_mapped_to_architect_contract(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state")

    contract = service.build_contract(_request(tmp_path))

    assert contract.schema == "nexus.self_hosted_task_contract.v2"
    assert contract.objective == "Add one bounded canary test"
    assert contract.goal.what == contract.objective
    assert contract.goal.why == "Prove the MCP request becomes a governed task"
    assert contract.preferred_provider == "codex"
    assert contract.human_approval_required is True


def test_submit_persists_idempotent_task_state(tmp_path):
    calls = []

    def fake_runner(contract, request, update):
        calls.append(contract.task_id)
        update("CANDIDATE_COMMITTED", {"candidate_commit_sha": "c" * 40})
        return {
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "candidate_commit_created": True,
        }

    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=fake_runner)
    request = _request(tmp_path)

    first = service.submit_task(request)
    second = service.submit_task(request)

    assert first["task_id"] == "mcp-task-001"
    assert first["status"] == "CANDIDATE_COMMITTED"
    assert first["candidate_commit_sha"] == "c" * 40
    assert second == first
    assert calls == ["mcp-task-001"]
    persisted = json.loads((tmp_path / "state" / "mcp-task-001.json").read_text())
    assert persisted == first


def test_submit_rejects_raw_prompt_and_non_codex_worker(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state")

    with pytest.raises(ValueError, match="prompt"):
        service.build_contract(_request(tmp_path, prompt="run arbitrary shell"))
    with pytest.raises(ValueError, match="codex"):
        service.build_contract(_request(tmp_path, worker="gemini"))


def test_approval_is_hash_bound_and_does_not_merge(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state")
    request = _request(tmp_path)

    state = service._write_state(
        request["task_id"],
        {
            "task_id": request["task_id"],
            "status": "CANDIDATE_COMMITTED",
            "promotion_packet": {
                "candidate_commit_sha": "c" * 40,
                "candidate_tree_sha": "d" * 40,
                "candidate_state_hash": "e" * 64,
                "verified_receipt_hash": "f" * 64,
            },
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "merge_performed": False,
            "push_performed": False,
        },
    )

    approved = service.approve_promotion(
        request["task_id"],
        candidate_commit_sha="c" * 40,
        candidate_tree_sha="d" * 40,
        candidate_state_hash="e" * 64,
        verified_receipt_hash="f" * 64,
    )

    assert approved["promotion_status"] == "APPROVED"
    assert approved["merge_performed"] is False
    assert approved["push_performed"] is False
