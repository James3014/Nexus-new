import json
from pathlib import Path
import time

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
    assert first["status"] in {"SUBMITTED", "CANDIDATE_COMMITTED"}
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        current = service.get_task(request["task_id"])
        if current and current["status"] == "CANDIDATE_COMMITTED":
            break
        time.sleep(0.01)
    second = service.submit_task(request)

    assert first["task_id"] == "mcp-task-001"
    assert first["status"] == "SUBMITTED"
    assert second["candidate_commit_sha"] == "c" * 40
    assert calls == ["mcp-task-001"]
    persisted = json.loads((tmp_path / "state" / "mcp-task-001.json").read_text())
    assert persisted == second


def test_submit_returns_before_background_runner_finishes(tmp_path):
    started = __import__("threading").Event()
    release = __import__("threading").Event()

    def fake_runner(contract, request, update):
        started.set()
        release.wait(2)
        update("WORKER_COMPLETED", {"execution": {"provider": "codex"}})
        return {"promotion_status": "PENDING_HUMAN_APPROVAL", "candidate_commit_created": True}

    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=fake_runner)
    request = _request(tmp_path, task_id="async-task-001")
    submitted = service.submit_task(request)

    assert submitted["status"] == "SUBMITTED"
    assert started.wait(1)
    running = service.get_task(request["task_id"])
    assert running["status"] in {"SUBMITTED", "WORKER_COMPLETED", "CANDIDATE_COMMITTED"}
    assert running["attempt_id"]
    assert running["worker_pid"]
    assert running["heartbeat_at"]
    release.set()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and service.get_task(request["task_id"])["status"] != "CANDIDATE_COMMITTED":
        time.sleep(0.01)
    assert service.get_task(request["task_id"])["status"] == "CANDIDATE_COMMITTED"


def test_reconcile_fails_closed_when_worker_lost_before_receipt(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    request = _request(tmp_path, task_id="lost-task-001")
    service._write_state(
        request["task_id"],
        {
            "task_id": request["task_id"],
            "status": "WORKER_RUNNING",
            "attempt_id": "a" * 32,
            "worker_pid": 999999,
            "worker_pgid": 999999,
            "worker_child_pgid": None,
            "heartbeat_at": "2026-01-01T00:00:00+00:00",
            "request": request,
            "promotion_status": "NOT_CREATED",
        },
    )

    reconciled = service.reconcile_task(request["task_id"])

    assert reconciled["status"] == "FINAL_BLOCK"
    assert "lost before recoverable execution evidence" in reconciled["error"]


def test_pid_permission_error_is_treated_as_alive(monkeypatch):
    monkeypatch.setattr("os.kill", lambda pid, signal: (_ for _ in ()).throw(PermissionError()))

    assert SelfHostedTaskService._pid_alive(12345) is True


def test_submit_rejects_raw_prompt_and_unknown_worker(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state")

    with pytest.raises(ValueError, match="prompt"):
        service.build_contract(_request(tmp_path, prompt="run arbitrary shell"))
    contract = service.build_contract(_request(tmp_path, worker="gemini"))
    assert contract.preferred_provider == "gemini"
    escalated = service.build_contract(_request(tmp_path, worker="codex", fallback_worker="opencode"))
    assert escalated.fallback_provider == "opencode"
    assert escalated.maximum_provider_calls == 2
    with pytest.raises(ValueError, match="one of"):
        service.build_contract(_request(tmp_path, worker="unknown"))


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
