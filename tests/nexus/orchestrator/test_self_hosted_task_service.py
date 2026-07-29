import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

repo_root = str(Path(__file__).resolve().parents[3])
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import pytest

from nexus.executors.worker_contract import WorkerExecutionReceipt, WorkerOutcome, WorkerPreflight
from nexus.executors.worker_registry import WorkerRegistry
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.worktree_manager import TargetWorktreeLease


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


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _real_request(tmp_path: Path, task_id: str = "real-reconcile"):
    controller = tmp_path / "controller"
    controller.mkdir()
    _git(controller, "init", "-b", "main")
    _git(controller, "config", "user.name", "Lifecycle Test")
    _git(controller, "config", "user.email", "lifecycle@example.test")
    (controller / "README").write_text("base\n")
    _git(controller, "add", "README")
    _git(controller, "commit", "-m", "base")
    head = _git(controller, "rev-parse", "HEAD")
    target_root = tmp_path / "targets"
    return _request(
        tmp_path, task_id=task_id, controller_revision=head,
        target_base_revision=head, controller_repo_root=str(controller),
        target_repo_root=str(target_root / task_id), target_worktree_root=str(target_root),
    )


def _wait_for_status(service: SelfHostedTaskService, task_id: str, status: str):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        current = service.get_task(task_id)
        if current and current["status"] == status:
            return current
        time.sleep(0.01)
    return service.get_task(task_id)


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
    _wait_for_status(service, request["task_id"], "CANDIDATE_COMMITTED")
    second = service.submit_task(request)

    assert first["task_id"] == "mcp-task-001"
    assert first["status"] == "SUBMITTED"
    assert second["candidate_commit_sha"] == "c" * 40
    assert calls == ["mcp-task-001"]
    persisted = json.loads((tmp_path / "state" / "mcp-task-001.json").read_text())
    assert persisted == second


def test_submitted_at_matches_initial_submitted_history_entry(tmp_path):
    release = __import__("threading").Event()

    def fake_runner(contract, request, update):
        release.wait(2)
        return {"promotion_status": "PENDING_HUMAN_APPROVAL", "candidate_commit_created": True}

    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=fake_runner)
    request = _request(tmp_path, task_id="submitted-at-initial")

    submitted = service.submit_task(request)

    assert submitted["status"] == "SUBMITTED"
    assert submitted["submitted_at"] == submitted["status_history"][0]["at"]
    assert submitted["status_history"][0]["status"] == "SUBMITTED"
    release.set()
    assert _wait_for_status(service, request["task_id"], "PENDING_HUMAN_APPROVAL")["status"] == "PENDING_HUMAN_APPROVAL"


def test_submitted_at_is_immutable_after_background_completion_and_in_receipt(tmp_path):
    release = __import__("threading").Event()

    def fake_runner(contract, request, update):
        release.wait(2)
        update("WORKER_COMPLETED", {"execution": {"provider": "codex"}})
        update("VERIFIED", {"submitted_at": "2099-01-01T00:00:00+00:00"})
        return {"promotion_status": "PENDING_HUMAN_APPROVAL", "candidate_commit_created": True}

    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=fake_runner)
    request = _request(tmp_path, task_id="submitted-at-completion")
    submitted = service.submit_task(request)
    submitted_at = submitted["submitted_at"]

    release.set()
    completed = _wait_for_status(service, request["task_id"], "PENDING_HUMAN_APPROVAL")
    receipt = service.get_receipt(request["task_id"])

    assert completed["submitted_at"] == submitted_at
    assert completed["status_history"][0]["at"] == submitted_at
    assert receipt["submitted_at"] == submitted_at


def test_submitted_at_is_stable_across_idempotent_resubmission(tmp_path):
    calls = []

    def fake_runner(contract, request, update):
        calls.append(contract.task_id)
        return {"promotion_status": "PENDING_HUMAN_APPROVAL", "candidate_commit_created": True}

    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=fake_runner)
    request = _request(tmp_path, task_id="submitted-at-idempotent")

    first = service.submit_task(request)
    completed = _wait_for_status(service, request["task_id"], "PENDING_HUMAN_APPROVAL")
    second = service.submit_task(request)

    assert first["submitted_at"] == first["status_history"][0]["at"]
    assert completed["submitted_at"] == first["submitted_at"]
    assert second["submitted_at"] == first["submitted_at"]
    assert calls == ["submitted-at-idempotent"]



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
    while time.monotonic() < deadline and service.get_task(request["task_id"])["status"] != "PENDING_HUMAN_APPROVAL":
        time.sleep(0.01)
    assert service.get_task(request["task_id"])["status"] == "PENDING_HUMAN_APPROVAL"


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
    auto = service.build_contract(
        _request(tmp_path, worker="auto", worker_order=["gemini", "codex", "ollama"])
    )
    assert auto.preferred_provider == "gemini"
    assert auto.fallback_provider == "codex"
    assert auto.provider_order == ["gemini", "codex", "ollama"]
    assert auto.maximum_provider_calls == 3
    with pytest.raises(ValueError, match="one of"):
        service.build_contract(_request(tmp_path, worker="unknown"))


def test_approval_is_hash_bound_and_does_not_merge(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state")
    request = _request(tmp_path)

    service._write_state(
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


def test_approved_task_action_envelope_requires_integration_not_terminal(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _request(tmp_path, task_id="approved-action")
    service._write_state(
        "approved-action",
        {
            "task_id": "approved-action",
            "status": "APPROVED",
            "request": request,
            "promotion_status": "APPROVED",
            "promotion_packet": {
                "candidate_commit_sha": "c" * 40,
                "candidate_tree_sha": "d" * 40,
                "candidate_state_hash": "e" * 64,
                "verified_receipt_hash": "f" * 64,
            },
            "cleanup_decision": "REMOVED",
            "cleanup_performed": True,
        },
    )

    state = service.get_task("approved-action")

    assert state["task_action"]["action_state"] == "ACTION_REQUIRED"
    assert state["task_action"]["attention_required"] is True
    assert state["task_action"]["next_action"] == "integrate_approved_candidate"
    assert state["task_action"]["recommended_tool"] == "nexus_self_hosted_integrate_approved"
    assert state["task_action"]["candidate_commit_sha"] == "c" * 40
    assert state["task_action"]["cleanup_status"]["cleanup_decision"] == "REMOVED"


def test_approval_mismatch_returns_action_required_envelope(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _request(tmp_path, task_id="approval-mismatch")
    service._write_state(
        "approval-mismatch",
        {
            "task_id": "approval-mismatch",
            "status": "PENDING_HUMAN_APPROVAL",
            "request": request,
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "promotion_packet": {
                "candidate_commit_sha": "c" * 40,
                "candidate_tree_sha": "d" * 40,
                "candidate_state_hash": "e" * 64,
                "verified_receipt_hash": "f" * 64,
            },
            "merge_performed": False,
            "push_performed": False,
        },
    )

    result = service.approve_promotion(
        "approval-mismatch",
        candidate_commit_sha="c" * 40,
        candidate_tree_sha="0" * 40,
        candidate_state_hash="e" * 64,
        verified_receipt_hash="f" * 64,
    )

    assert result["status"] == "APPROVAL_INVALIDATED"
    assert result["task_action"]["action_state"] == "ACTION_REQUIRED"
    assert result["task_action"]["attention_required"] is True
    assert result["task_action"]["next_action"] == "resubmit_exact_approval_binding"
    assert result["task_action"]["recommended_tool"] == "nexus_self_hosted_approve_promotion"


def test_terminal_retry_keeps_task_identity_and_increments_attempt(tmp_path):
    calls = []

    def runner(contract, request, update):
        calls.append(contract.task_id)
        update("FINAL_BLOCK", {"cleanup_decision": "REMOVED", "cleanup_performed": True})
        return {"promotion_status": "NOT_CREATED"}

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", runner=runner, auto_reconcile=False, ephemeral=True
    )
    request = _request(tmp_path, task_id="stable-task")
    first = service.submit_task(request)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and service._read_state("stable-task")["status"] != "FINAL_BLOCK":
        time.sleep(0.01)
    first_attempt = service._read_state("stable-task")["attempt_id"]
    service.submit_task(request)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and len(calls) < 2:
        time.sleep(0.01)
    state = service._read_state("stable-task")

    assert first["task_id"] == state["task_id"] == "stable-task"
    assert state["attempt_id"] != first_attempt
    assert len(state["attempts"]) == 2
    assert calls == ["stable-task", "stable-task"]


def test_noncanonical_state_root_requires_ephemeral_mode(tmp_path):
    with pytest.raises(ValueError, match="canonical state root"):
        SelfHostedTaskService(state_dir="/Users/jameschen/Workspace/nexus-sibling-state", auto_reconcile=False)


def test_default_state_root_uses_configured_canonical_root(tmp_path, monkeypatch):
    canonical = tmp_path / "canonical"
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(canonical))

    service = SelfHostedTaskService(auto_reconcile=False)

    assert service.state_dir == canonical.resolve()


def test_archive_manifest_hash_is_reproducible(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("done", {"task_id": "done", "status": "FINAL_BLOCK"})

    first = service.archive_states(dry_run=True)
    second = service.archive_states(dry_run=True)

    assert first["manifest_hash"] == second["manifest_hash"]
    assert first["entries"][0]["receipt_hash"]


def test_archive_apply_persists_manifest_and_remains_readable(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("done", {"task_id": "done", "status": "FINAL_BLOCK", "updated_at": "2026-01-01T00:00:00+00:00"})
    preview = service.archive_states(dry_run=True)

    applied = service.archive_states(dry_run=False)
    repeated = service.archive_states(dry_run=False)

    assert applied["manifest_hash"] == preview["manifest_hash"]
    assert Path(applied["manifest_path"]).is_file()
    assert not (tmp_path / "state" / "done.json").exists()
    assert service.get_task("done")["status"] == "FINAL_BLOCK"
    assert repeated["entries"] == []


def test_archived_integrated_task_retries_with_same_identity_and_versions_receipt(tmp_path):
    calls = []

    def runner(contract, request, update):
        calls.append(contract.task_id)
        update("FINAL_BLOCK", {"cleanup_decision": "REMOVED", "cleanup_performed": True})
        return {"promotion_status": "NOT_CREATED"}

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", runner=runner, auto_reconcile=False, ephemeral=True
    )
    request = _request(tmp_path, task_id="archived-integrated")
    contract = service.build_contract(request)
    first_attempt = "a" * 32
    service._write_state("archived-integrated", {
        "task_id": "archived-integrated", "status": "INTEGRATED",
        "attempt_id": first_attempt, "attempts": [{"attempt_id": first_attempt}],
        "request": request, "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash, "promotion_status": "INTEGRATED",
        "candidate_ref": "refs/nexus-candidates/archived-integrated/old",
        "promotion_packet": {"candidate_commit_sha": "c" * 40},
        "final_disposition": "INTEGRATED", "cleanup_decision": "REMOVED",
        "cleanup_performed": True, "updated_at": "2026-01-01T00:00:00+00:00",
    })
    first_archive = service.archive_states(dry_run=False)

    submitted = service.submit_task(request)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        current = service._read_state("archived-integrated")
        if current and current["status"] == "FINAL_BLOCK":
            break
        time.sleep(0.01)
    current = service._read_state("archived-integrated")
    second_archive = service.archive_states(dry_run=False)

    assert submitted["task_id"] == "archived-integrated"
    assert current["attempt_id"] != first_attempt
    assert len(current["attempts"]) == 2
    assert current["candidate_ref"] is None
    assert current["candidate_history"][0]["final_disposition"] == "INTEGRATED"
    assert calls == ["archived-integrated"]
    assert Path(first_archive["entries"][0]["archive_location"]).is_file()
    assert Path(second_archive["entries"][0]["archive_location"]).is_file()
    assert first_archive["entries"][0]["archive_location"] != second_archive["entries"][0]["archive_location"]
    assert service.get_task("archived-integrated")["attempt_id"] == current["attempt_id"]


def test_terminal_retry_accepts_revision_fast_forward_and_preserves_contract_history(tmp_path):
    calls = []

    def runner(contract, request, update):
        calls.append((contract.controller_revision, contract.target_base_revision))
        update("FINAL_BLOCK", {"cleanup_decision": "REMOVED", "cleanup_performed": True})
        return {"promotion_status": "NOT_CREATED"}

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", runner=runner, auto_reconcile=False, ephemeral=True
    )
    request = _real_request(tmp_path, task_id="activation-retry")
    first_contract = service.build_contract(request)
    first_attempt = "a" * 32
    service._write_state("activation-retry", {
        "task_id": "activation-retry", "status": "FINAL_BLOCK",
        "attempt_id": first_attempt, "attempts": [{"attempt_id": first_attempt}],
        "request": request, "contract": first_contract.model_dump(mode="json"),
        "contract_hash": first_contract.contract_hash, "promotion_status": "NOT_CREATED",
        "final_disposition": "FINAL_BLOCK", "cleanup_decision": "ALREADY_REMOVED",
        "cleanup_performed": False,
    })

    controller = Path(request["controller_repo_root"])
    (controller / "README").write_text("activation\n")
    _git(controller, "add", "README")
    _git(controller, "commit", "-m", "activate lifecycle")
    activated_head = _git(controller, "rev-parse", "HEAD")
    refreshed = {
        **request,
        "controller_revision": activated_head,
        "target_base_revision": activated_head,
    }

    submitted = service.submit_task(refreshed)
    current = _wait_for_status(service, "activation-retry", "FINAL_BLOCK")

    assert submitted["attempt_id"] != first_attempt
    assert current["attempt_id"] == submitted["attempt_id"]
    assert len(current["attempts"]) == 2
    assert current["contract_hash"] == service.build_contract(refreshed).contract_hash
    assert current["controller_revision"] == activated_head
    assert current["target_initial_revision"] == activated_head
    assert current["contract_history"] == [{
        "attempt_id": first_attempt,
        "contract_hash": first_contract.contract_hash,
        "controller_revision": request["controller_revision"],
        "target_base_revision": request["target_base_revision"],
        "final_disposition": "FINAL_BLOCK",
    }]
    assert calls == [(activated_head, activated_head)]


def test_terminal_retry_rejects_non_revision_contract_change(tmp_path):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", runner=lambda *_: {}, auto_reconcile=False, ephemeral=True
    )
    request = _real_request(tmp_path, task_id="semantic-drift-retry")
    contract = service.build_contract(request)
    service._write_state("semantic-drift-retry", {
        "task_id": "semantic-drift-retry", "status": "FINAL_BLOCK",
        "attempt_id": "a" * 32, "attempts": [{"attempt_id": "a" * 32}],
        "request": request, "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash, "promotion_status": "NOT_CREATED",
        "cleanup_decision": "ALREADY_REMOVED",
    })

    changed = {**request, "what": "Silently change the task objective"}

    with pytest.raises(ValueError, match="different contract"):
        service.submit_task(changed)


def test_pending_candidate_blocks_retry_until_superseded(tmp_path):
    calls = []

    def runner(contract, request, update):
        calls.append(contract.task_id)
        update("FINAL_BLOCK", {"cleanup_decision": "REMOVED", "cleanup_performed": True})
        return {"promotion_status": "NOT_CREATED"}

    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=runner, auto_reconcile=False, ephemeral=True)
    request = _request(tmp_path, task_id="pending-task")
    contract = service.build_contract(request)
    service._write_state("pending-task", {
        "task_id": "pending-task", "status": "PENDING_HUMAN_APPROVAL",
        "attempt_id": "a" * 32, "attempts": [{"attempt_id": "a" * 32}],
        "request": request, "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash, "promotion_status": "PENDING_HUMAN_APPROVAL",
        "cleanup_decision": "REMOVED", "cleanup_performed": True,
    })

    blocked = service.submit_task(request)
    assert blocked["attempt_id"] == "a" * 32
    assert calls == []

    service.dispose_candidate("pending-task", disposition="SUPERSEDED", superseded_by="next")
    retried = service.submit_task(request)
    assert retried["attempt_id"] != "a" * 32


def test_cleanup_apply_invokes_governed_worktree_cleanup(tmp_path, monkeypatch):
    calls = []
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _request(tmp_path, task_id="cleanup-task")
    contract = service.build_contract(request)
    lease = TargetWorktreeLease(
        schema="nexus.target_worktree_lease.v1", lease_id="lease", task_id="cleanup-task",
        controller_revision=contract.controller_revision, target_base_revision=contract.target_base_revision,
        target_worktree=request["target_repo_root"], target_branch="nexus/task/cleanup-task",
        initial_head=contract.target_base_revision, initial_status_sha256="0" * 64,
        controller_status_sha256="0" * 64, created_from_exact_revision=True,
        commit_created=False, merge_performed=False,
    )
    service._write_state("cleanup-task", {
        "task_id": "cleanup-task", "status": "FINAL_BLOCK", "request": request,
        "contract": contract.model_dump(mode="json"), "contract_hash": contract.contract_hash,
        "attempt_id": "a" * 32, "lease": lease.__dict__,
    })

    class FakeManager:
        def __init__(self, root_dir):
            pass
        def cleanup_terminal_target(self, contract, lease, **kwargs):
            calls.append(kwargs["dry_run"])
            return SimpleNamespace(decision="REMOVED", blocker=None, performed=not kwargs["dry_run"], eligible=True)

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", FakeManager)
    service.cleanup_tasks(task_id="cleanup-task", dry_run=True)
    applied = service.cleanup_tasks(task_id="cleanup-task", dry_run=False)

    assert calls == [True, False]
    assert applied["decisions"][0]["cleanup_decision"] == "REMOVED"
    assert service._read_state("cleanup-task")["cleanup_performed"] is True


def test_cleanup_rejects_approved_binding_mismatch(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _request(tmp_path, task_id="binding-cleanup")
    contract = service.build_contract(request)
    lease = TargetWorktreeLease(
        schema="nexus.target_worktree_lease.v1", lease_id="lease", task_id="binding-cleanup",
        controller_revision=contract.controller_revision, target_base_revision=contract.target_base_revision,
        target_worktree=request["target_repo_root"], target_branch="nexus/task/binding-cleanup",
        initial_head=contract.target_base_revision, initial_status_sha256="0" * 64,
        controller_status_sha256="0" * 64, created_from_exact_revision=True,
        commit_created=False, merge_performed=False,
    )
    service._write_state("binding-cleanup", {
        "task_id": "binding-cleanup", "status": "INTEGRATED", "request": request,
        "contract": contract.model_dump(mode="json"), "attempt_id": "a" * 32,
        "lease": lease.__dict__, "promotion_status": "INTEGRATED",
        "promotion_packet": {"candidate_commit_sha": "c" * 40},
        "approved_binding": {"candidate_commit_sha": "d" * 40},
    })

    decision = service.cleanup_tasks(task_id="binding-cleanup", dry_run=False)["decisions"][0]

    assert decision["cleanup_decision"] == "BLOCKED_BY_MISSING_REF"
    assert decision["cleanup_blocker"] == "approval binding mismatch"


def test_integration_failure_is_persisted(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("integration-fail", {
        "task_id": "integration-fail", "status": "APPROVED", "attempt_id": "a" * 32,
        "promotion_status": "APPROVED", "contract": {"target_worktree_root": str(tmp_path / "targets")},
    })

    class FailingIntegration:
        def __init__(self, integration_root):
            pass
        def integrate_task_state(self, state, integration_branch):
            raise RuntimeError("integration verifier failed")

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager", FailingIntegration)
    with pytest.raises(RuntimeError, match="integration verifier failed"):
        service.integrate_approved("integration-fail")

    state = service._read_state("integration-fail")
    assert state["status"] == "INTEGRATION_FAILED"
    assert state["promotion_status"] == "INTEGRATION_FAILED"
    assert state["push_performed"] is False


def test_exact_approved_integration_is_idempotent(tmp_path, monkeypatch):
    calls = []
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("integration-once", {
        "task_id": "integration-once", "status": "APPROVED", "attempt_id": "a" * 32,
        "promotion_status": "APPROVED", "contract": {"target_worktree_root": str(tmp_path / "targets")},
    })

    class SuccessfulIntegration:
        def __init__(self, integration_root):
            pass
        def integrate_task_state(self, state, integration_branch):
            calls.append(integration_branch)
            return SimpleNamespace(
                integration_branch=integration_branch,
                integration_base_sha="b" * 40,
                integration_commit_sha="c" * 40,
            )

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager", SuccessfulIntegration)
    first = service.integrate_approved("integration-once")
    second = service.integrate_approved("integration-once")

    assert first == second
    assert calls == ["nexus/integration"]
    assert first["integration_base_sha"] == "b" * 40
    assert first["push_performed"] is False


def test_lifecycle_receipt_exposes_required_fields(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("receipt", {"task_id": "receipt", "status": "FINAL_BLOCK"})

    receipt = service.get_receipt("receipt")

    required = {
        "task_id", "attempt_id", "status", "submitted_at", "controller_worktree", "controller_revision",
        "controller_status_sha256", "target_worktree", "target_initial_revision",
        "target_branch", "target_created_at", "worker_provider", "worker_pid",
        "heartbeat_at", "execution_outcome", "verification_verdict",
        "candidate_commit_sha", "candidate_tree_sha", "candidate_ref",
        "candidate_state_hash", "verified_receipt_hash", "promotion_status",
        "approved_binding", "integration_branch", "integration_base_sha",
        "integration_result_sha", "terminal_status", "cleanup_eligible",
        "cleanup_decision", "cleanup_blocker", "cleanup_performed",
        "cleanup_performed_at", "state_retention_status", "archive_eligible",
        "archive_location",
    }
    assert required <= receipt.keys()


def test_orphan_clean_target_is_reconciled_and_removed(tmp_path):
    request = _real_request(tmp_path)
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    contract = service.build_contract(request)
    from nexus.orchestrator.worktree_manager import WorktreeManager
    lease = WorktreeManager(root_dir=contract.target_worktree_root).create_lease(contract)
    service._write_state(contract.task_id, {
        "task_id": contract.task_id, "status": "TARGET_LEASED",
        "attempt_id": "a" * 32, "attempts": [{"attempt_id": "a" * 32}],
        "request": request, "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash, "lease": lease.__dict__,
        "worker_pid": 999999, "heartbeat_at": "2026-01-01T00:00:00+00:00",
    })

    reconciled = service.reconcile_task(contract.task_id)

    assert reconciled["status"] == "FINAL_BLOCK"
    assert reconciled["cleanup_decision"] == "REMOVED"
    assert reconciled["cleanup_performed"] is True
    assert not Path(lease.target_worktree).exists()


def test_orphan_candidate_checkpoint_resumes_ref_and_cleanup(tmp_path):
    request = _real_request(tmp_path, task_id="candidate-recovery")
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    contract = service.build_contract(request)
    from nexus.orchestrator.worktree_manager import WorktreeManager
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "nexus_canary.txt").write_text("candidate\n")
    _git(target, "add", "nexus_canary.txt")
    _git(target, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "candidate")
    candidate = _git(target, "rev-parse", "HEAD")
    tree = _git(target, "rev-parse", "HEAD^{tree}")
    service._write_state(contract.task_id, {
        "task_id": contract.task_id, "status": "CANDIDATE_COMMITTED",
        "attempt_id": "a" * 32, "attempts": [{"attempt_id": "a" * 32}],
        "request": request, "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash, "lease": lease.__dict__,
        "promotion_packet": {
            "candidate_commit_sha": candidate, "candidate_tree_sha": tree,
            "candidate_state_hash": "c" * 64, "verified_receipt_hash": "d" * 64,
        },
        "worker_pid": 999999, "heartbeat_at": "2026-01-01T00:00:00+00:00",
    })

    reconciled = service.reconcile_task(contract.task_id)

    assert reconciled["status"] == "PENDING_HUMAN_APPROVAL"
    assert reconciled["cleanup_decision"] == "REMOVED"
    assert not target.exists()
    assert _git(Path(contract.controller_repo_root), "rev-parse", reconciled["candidate_ref"]) == candidate


def test_verified_retained_candidate_can_resume_ref_protection_and_cleanup(tmp_path):
    request = _real_request(tmp_path, task_id="retained-candidate-recovery")
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    contract = service.build_contract(request)
    from nexus.orchestrator.worktree_manager import WorktreeManager
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "nexus_canary.txt").write_text("candidate\n")
    _git(target, "add", "nexus_canary.txt")
    _git(target, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "candidate")
    candidate = _git(target, "rev-parse", "HEAD")
    tree = _git(target, "rev-parse", "HEAD^{tree}")
    service._write_state(contract.task_id, {
        "task_id": contract.task_id, "status": "RETAINED_FOR_REVIEW",
        "attempt_id": "a" * 32, "attempts": [{"attempt_id": "a" * 32}],
        "request": request, "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash, "lease": lease.__dict__,
        "promotion_packet": {
            "candidate_commit_sha": candidate, "candidate_tree_sha": tree,
            "candidate_state_hash": "c" * 64, "verified_receipt_hash": "d" * 64,
            "promotion_status": "PENDING_HUMAN_APPROVAL",
        },
        "verified_receipt": {"verified": True},
        "promotion_status": "NOT_CREATED", "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES",
        "worker_pid": 999999, "heartbeat_at": "2026-01-01T00:00:00+00:00",
    })

    recovered = service.recover_retained_candidate(contract.task_id)

    assert recovered["status"] == "PENDING_HUMAN_APPROVAL"
    assert recovered["cleanup_decision"] == "REMOVED"
    assert not target.exists()
    assert _git(Path(contract.controller_repo_root), "rev-parse", recovered["candidate_ref"]) == candidate


def test_live_target_lease_is_not_reconciled_away(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("live", {
        "task_id": "live", "status": "TARGET_LEASED", "attempt_id": "a" * 32,
        "worker_pid": os.getpid(), "heartbeat_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    })

    state = service.reconcile_task("live")

    assert state["status"] == "TARGET_LEASED"


def test_five_terminal_retries_keep_one_task_identity(tmp_path):
    calls = []

    def runner(contract, request, update):
        calls.append(contract.task_id)
        update("FINAL_BLOCK", {"cleanup_decision": "REMOVED", "cleanup_performed": True})
        return {"promotion_status": "NOT_CREATED"}

    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=runner, auto_reconcile=False, ephemeral=True)
    request = _request(tmp_path, task_id="five-attempts")
    for expected in range(1, 6):
        service.submit_task(request)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            state = service._read_state("five-attempts")
            if state["status"] == "FINAL_BLOCK" and len(calls) == expected:
                break
            time.sleep(0.01)

    state = service._read_state("five-attempts")
    assert state["task_id"] == "five-attempts"
    assert len(state["attempts"]) == 5
    assert len({attempt["attempt_id"] for attempt in state["attempts"]}) == 5
    assert calls == ["five-attempts"] * 5


def test_same_task_id_different_contract_fails_closed(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=lambda *args: {}, auto_reconcile=False, ephemeral=True)
    request = _request(tmp_path, task_id="contract-bound")
    service.submit_task(request)

    with pytest.raises(ValueError, match="different contract"):
        service.submit_task({**request, "why": "different"})


def test_different_active_controller_is_rejected(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", runner=lambda *args: {}, auto_reconcile=False, ephemeral=True)
    first = _request(tmp_path, task_id="first-active")
    contract = service.build_contract(first)
    service._write_state("first-active", {
        "task_id": "first-active", "status": "WORKER_RUNNING",
        "contract": contract.model_dump(mode="json"), "contract_hash": contract.contract_hash,
    })
    second = _request(
        tmp_path, task_id="second-active",
        controller_repo_root=str(tmp_path / "different-controller"),
        target_repo_root=str(tmp_path / "targets" / "second-active"),
    )

    with pytest.raises(RuntimeError, match="active Controller lease"):
        service.submit_task(second)


def test_wait_task_polls_until_action_required(tmp_path):
    release = __import__("threading").Event()

    def runner(contract, request, update):
        release.wait(2)
        return {"promotion_status": "PENDING_HUMAN_APPROVAL", "candidate_commit_created": True}

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        runner=runner,
        auto_reconcile=False,
        ephemeral=True,
    )
    request = _request(tmp_path, task_id="wait-poll")
    service.submit_task(request)

    release.set()
    waited = service.wait_task("wait-poll", timeout_seconds=1.0, poll_interval_seconds=0.01)

    assert waited["status"] == "PENDING_HUMAN_APPROVAL"
    assert waited["wait"]["timed_out"] is False
    assert waited["task_action"]["action_state"] == "ACTION_REQUIRED"
    assert waited["task_action"]["recommended_tool"] == "nexus_self_hosted_approve_promotion"


def test_wait_task_timeout_returns_in_progress_envelope(tmp_path):
    release = __import__("threading").Event()

    def runner(contract, request, update):
        release.wait(2)
        return {"promotion_status": "PENDING_HUMAN_APPROVAL", "candidate_commit_created": True}

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        runner=runner,
        auto_reconcile=False,
        ephemeral=True,
    )
    request = _request(tmp_path, task_id="wait-timeout")
    service.submit_task(request)

    waited = service.wait_task("wait-timeout", timeout_seconds=0.01, poll_interval_seconds=0.001)

    assert waited["wait"]["timed_out"] is True
    assert waited["task_action"]["action_state"] == "IN_PROGRESS"
    assert waited["task_action"]["next_action"] == "wait_for_task"
    assert waited["task_action"]["recommended_tool"] == "nexus_self_hosted_wait_task"
    release.set()


def test_list_actionable_tasks_excludes_integrated_terminal_state(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    packet = {
        "candidate_commit_sha": "c" * 40,
        "candidate_tree_sha": "d" * 40,
        "candidate_state_hash": "e" * 64,
        "verified_receipt_hash": "f" * 64,
    }
    service._write_state("needs-approval", {
        "task_id": "needs-approval",
        "status": "PENDING_HUMAN_APPROVAL",
        "promotion_status": "PENDING_HUMAN_APPROVAL",
        "promotion_packet": packet,
    })
    service._write_state("needs-integration", {
        "task_id": "needs-integration",
        "status": "APPROVED",
        "promotion_status": "APPROVED",
        "promotion_packet": packet,
    })
    service._write_state("done", {
        "task_id": "done",
        "status": "INTEGRATED",
        "promotion_status": "INTEGRATED",
        "promotion_packet": packet,
        "terminal_status": "INTEGRATED",
    })

    result = service.list_actionable_tasks()

    assert [item["task_id"] for item in result["tasks"]] == ["needs-approval", "needs-integration"]
    assert result["actionable_count"] == 2
    assert result["tasks"][0]["task_action"]["next_action"] == "approve_candidate"
    assert result["tasks"][1]["task_action"]["next_action"] == "integrate_approved_candidate"


def test_integrated_task_action_envelope_is_terminal(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("integrated", {
        "task_id": "integrated",
        "status": "INTEGRATED",
        "promotion_status": "INTEGRATED",
        "terminal_status": "INTEGRATED",
        "integration_result_sha": "c" * 40,
        "cleanup_decision": "REMOVED",
        "cleanup_performed": True,
    })

    state = service.get_task("integrated")

    assert state["task_action"]["action_state"] == "TERMINAL"
    assert state["task_action"]["attention_required"] is False
    assert state["task_action"]["next_action"] == "none"
    assert state["task_action"]["recommended_tool"] is None


def test_integrating_task_action_envelope_remains_in_progress(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("integrating", {
        "task_id": "integrating",
        "status": "INTEGRATING",
        "promotion_status": "APPROVED",
        "integration_branch": "nexus/integration",
    })

    state = service.get_task("integrating")

    assert state["task_action"]["action_state"] == "IN_PROGRESS"
    assert state["task_action"]["attention_required"] is False
    assert state["task_action"]["recommended_tool"] == "nexus_self_hosted_wait_task"


def test_cancelled_task_records_terminal_cleanup_decision(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("cancel-me", {
        "task_id": "cancel-me", "status": "SUBMITTED", "attempt_id": "a" * 32,
        "worker_pid": None,
    })

    cancelled = service.cancel_task("cancel-me")

    assert cancelled["status"] == "CANCELLED"
    assert cancelled["cleanup_decision"] == "ALREADY_REMOVED"
    assert cancelled["final_disposition"] == "CANCELLED"


def test_default_runner_escalates_after_failed_cheap_worker(tmp_path, monkeypatch):
    calls = []

    class FakeAdapter:
        def __init__(self, provider):
            self.provider = provider

        def preflight(self):
            return WorkerPreflight(
                provider=self.provider,
                executable=f"/bin/{self.provider}",
                executable_available=True,
                authorized=True,
                implementation_status="IMPLEMENTED",
                ready=True,
                reason="ready",
            )

        def invoke(self, contract, lease, *, prompt, **options):
            calls.append(self.provider)
            outcome = WorkerOutcome.FAILED.value if self.provider == "codex" else WorkerOutcome.EXECUTION_COMPLETED.value
            return WorkerExecutionReceipt(
                provider=self.provider,
                task_id=contract.task_id,
                target_worktree=lease.target_worktree,
                worker_status="COMPLETED",
                outcome=outcome,
                exit_code=1 if outcome == WorkerOutcome.FAILED.value else 0,
                executable_identity=f"/bin/{self.provider}",
                argv=(self.provider,),
                stdout_sha256="a" * 64,
                stderr_sha256="b" * 64,
                wall_time_ms=1,
                process_group_id=None,
                process_group_killed=False,
                timed_out=False,
                provider_calls=1,
                evidence_complete=outcome == WorkerOutcome.EXECUTION_COMPLETED.value,
                commit_created=False,
                merge_performed=False,
                push_performed=False,
                failure_reason=None if outcome == WorkerOutcome.EXECUTION_COMPLETED.value else "codex failed",
            )

    registry = WorkerRegistry({provider: FakeAdapter(provider) for provider in ("codex", "gemini", "opencode", "mimo", "ollama")})
    service = SelfHostedTaskService(state_dir=tmp_path / "state", worker_registry=registry, auto_reconcile=False)
    request = _request(tmp_path, worker="codex", fallback_worker="opencode", task_id="escalate-task")
    contract = service.build_contract(request)
    state = {"status": "SUBMITTED", "attempt_id": "a" * 32}
    monkeypatch.setattr(service, "_read_state", lambda task_id: state)

    class FakeManager:
        cleanup_calls = 0

        def __init__(self, root_dir):
            self.root_dir = root_dir

        def verify_controller_unchanged(self, contract, expected_status_sha256=None):
            return expected_status_sha256 or "0" * 64

        def _run_git(self, args, cwd=None):
            return "b" * 40

        def cleanup(self, task_id, force=False):
            FakeManager.cleanup_calls += 1

        def protect_candidate(self, contract, lease, candidate_commit):
            assert state["status"] == "CANDIDATE_COMMITTED"
            assert state["promotion_packet"].candidate_commit_sha == candidate_commit
            return f"refs/nexus-candidates/{contract.task_id}"

        def cleanup_terminal_target(self, contract, lease, **kwargs):
            assert state["status"] == "CANDIDATE_REF_PROTECTED"
            assert state["candidate_ref"] == f"refs/nexus-candidates/{contract.task_id}"
            return SimpleNamespace(decision="REMOVED", blocker=None, performed=True, eligible=True)

    lease_count = 0

    class FakeController:
        def __init__(self, worktree_manager):
            self.worktree_manager = worktree_manager

        def prepare_task(self, contract):
            nonlocal lease_count
            lease_count += 1
            return TargetWorktreeLease(
                schema="nexus.target_worktree_lease.v1",
                lease_id=f"lease-{lease_count}",
                task_id=contract.task_id,
                controller_revision=contract.controller_revision,
                target_base_revision=contract.target_base_revision,
                target_worktree=str(tmp_path / "target"),
                target_branch=f"nexus/task/{contract.task_id}",
                initial_head="b" * 40,
                initial_status_sha256="0" * 64,
                controller_status_sha256="0" * 64,
                created_from_exact_revision=True,
                commit_created=False,
                merge_performed=False,
            )

        def collect_candidate(self, contract, lease):
            return SimpleNamespace(candidate_state_hash="c" * 64, changed_files=["nexus_canary.txt"])

    class FakeVerifier:
        def __init__(self, manager):
            pass

        def verify(self, contract, lease, candidate, protected_paths=None):
            return SimpleNamespace(
                verified=True,
                scope_gate_passed=True,
                deletion_gate_passed=True,
                controller_gate_passed=True,
                protected_contract_gate_passed=True,
                verifier_gate_passed=True,
                failure_reasons=[],
            )

    class FakeCommitter:
        def __init__(self, manager):
            pass

        def create_candidate_commit(self, contract, lease, verified):
            return SimpleNamespace(
                candidate_commit_sha="d" * 40,
                promotion_status="PENDING_HUMAN_APPROVAL",
                candidate_commit_created=True,
                public_claim_allowed=False,
                production_ready=False,
                merge_performed=False,
                push_performed=False,
            )

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", FakeManager)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.SelfHostedDevelopmentController", FakeController)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CandidateVerifier", FakeVerifier)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CandidateCommitter", FakeCommitter)

    def update(status, values):
        state["status"] = status
        state.update(values)

    result = service._run_default_resumable(
        contract,
        request,
        update,
        task_id=contract.task_id,
        attempt_id=state["attempt_id"],
    )

    assert calls == ["codex", "opencode"]
    assert FakeManager.cleanup_calls == 1
    assert lease_count == 2
    assert result["execution"].provider == "opencode"
    assert result["attempt_resolution"].verdict == "PROVEN"


def test_empty_candidate_fails_closed_and_blocks_candidate_commit(tmp_path, monkeypatch):
    class FakeAdapter:
        provider = "codex"

        def preflight(self):
            return WorkerPreflight(
                provider="codex",
                executable="/bin/codex",
                executable_available=True,
                authorized=True,
                implementation_status="IMPLEMENTED",
                ready=True,
                reason="ready",
            )

        def invoke(self, contract, lease, *, prompt, **options):
            return WorkerExecutionReceipt(
                provider="codex",
                task_id=contract.task_id,
                target_worktree=lease.target_worktree,
                worker_status="COMPLETED",
                outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
                exit_code=0,
                executable_identity="/bin/codex",
                argv=("codex",),
                stdout_sha256="a" * 64,
                stderr_sha256="b" * 64,
                wall_time_ms=1,
                process_group_id=None,
                process_group_killed=False,
                timed_out=False,
                provider_calls=1,
                evidence_complete=True,
                commit_created=False,
                merge_performed=False,
                push_performed=False,
            )

    registry = WorkerRegistry({"codex": FakeAdapter(), "gemini": FakeAdapter(), "opencode": FakeAdapter(), "mimo": FakeAdapter(), "ollama": FakeAdapter()})
    service = SelfHostedTaskService(state_dir=tmp_path / "state", worker_registry=registry, auto_reconcile=False)
    request = _request(tmp_path, worker="codex", task_id="empty-cand-task")
    contract = service.build_contract(request)
    checkpoint_history = []
    state = {"status": "SUBMITTED", "attempt_id": "a" * 32}
    monkeypatch.setattr(service, "_read_state", lambda task_id: state)

    class FakeManager:
        def __init__(self, root_dir):
            pass

    class FakeController:
        def __init__(self, worktree_manager):
            pass

        def prepare_task(self, contract):
            return TargetWorktreeLease(
                schema="nexus.target_worktree_lease.v1",
                lease_id="lease-1",
                task_id=contract.task_id,
                controller_revision=contract.controller_revision,
                target_base_revision=contract.target_base_revision,
                target_worktree=str(tmp_path / "target"),
                target_branch="branch",
                initial_head="b" * 40,
                initial_status_sha256="0" * 64,
                controller_status_sha256="0" * 64,
                created_from_exact_revision=True,
                commit_created=False,
                merge_performed=False,
            )

        def collect_candidate(self, contract, lease):
            # empty diff
            return SimpleNamespace(candidate_state_hash="c" * 64, changed_files=[], untracked_files=[], deleted_files=[])

    class FakeVerifier:
        def __init__(self, manager):
            pass

        def verify(self, contract, lease, candidate, protected_paths=None):
            return SimpleNamespace(
                verified=True,
                scope_gate_passed=True,
                deletion_gate_passed=True,
                controller_gate_passed=True,
                protected_contract_gate_passed=True,
                verifier_gate_passed=True,
                failure_reasons=[],
            )

    committer_called = False

    class FakeCommitter:
        def __init__(self, manager):
            pass

        def create_candidate_commit(self, contract, lease, verified):
            nonlocal committer_called
            committer_called = True

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", FakeManager)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.SelfHostedDevelopmentController", FakeController)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CandidateVerifier", FakeVerifier)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.CandidateCommitter", FakeCommitter)

    def update(status, values):
        state["status"] = status
        state.update(values)
        checkpoint_history.append((status, values.get("attempt_resolution")))

    with pytest.raises(RuntimeError, match="candidate verification failed: candidate diff is empty"):
        service._run_default_resumable(
            contract,
            request,
            update,
            task_id=contract.task_id,
            attempt_id=state["attempt_id"],
        )

    assert committer_called is False
    verified_checkpoints = [v for s, v in checkpoint_history if s == "VERIFIED"]
    assert len(verified_checkpoints) == 1
    assert verified_checkpoints[0].verdict == "FAILED"
    assert verified_checkpoints[0].candidate_non_empty is False


def test_legacy_proven_outcome_fails_closed_in_service(tmp_path, monkeypatch):
    class FakeAdapter:
        provider = "codex"

        def preflight(self):
            return WorkerPreflight(
                provider="codex",
                executable="/bin/codex",
                executable_available=True,
                authorized=True,
                implementation_status="IMPLEMENTED",
                ready=True,
                reason="ready",
            )

        def invoke(self, contract, lease, *, prompt, **options):
            return WorkerExecutionReceipt(
                provider="codex",
                task_id=contract.task_id,
                target_worktree=lease.target_worktree,
                worker_status="COMPLETED",
                outcome=WorkerOutcome.PROVEN.value,
                exit_code=0,
                executable_identity="/bin/codex",
                argv=("codex",),
                stdout_sha256="a" * 64,
                stderr_sha256="b" * 64,
                wall_time_ms=1,
                process_group_id=None,
                process_group_killed=False,
                timed_out=False,
                provider_calls=1,
                evidence_complete=True,
                commit_created=False,
                merge_performed=False,
                push_performed=False,
            )

    registry = WorkerRegistry({provider: FakeAdapter() for provider in ("codex", "gemini", "opencode", "mimo", "ollama")})
    service = SelfHostedTaskService(state_dir=tmp_path / "state", worker_registry=registry, auto_reconcile=False)
    request = _request(tmp_path, worker="codex", task_id="legacy-proven-task")
    contract = service.build_contract(request)
    checkpoint_history = []
    state = {"status": "SUBMITTED", "attempt_id": "a" * 32}
    monkeypatch.setattr(service, "_read_state", lambda task_id: state)

    class FakeManager:
        def __init__(self, root_dir):
            pass

    class FakeController:
        def __init__(self, worktree_manager):
            pass

        def prepare_task(self, contract):
            return TargetWorktreeLease(
                schema="nexus.target_worktree_lease.v1",
                lease_id="lease-1",
                task_id=contract.task_id,
                controller_revision=contract.controller_revision,
                target_base_revision=contract.target_base_revision,
                target_worktree=str(tmp_path / "target"),
                target_branch="branch",
                initial_head="b" * 40,
                initial_status_sha256="0" * 64,
                controller_status_sha256="0" * 64,
                created_from_exact_revision=True,
                commit_created=False,
                merge_performed=False,
            )

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", FakeManager)
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.SelfHostedDevelopmentController", FakeController)

    def update(status, values):
        state["status"] = status
        state.update(values)
        checkpoint_history.append((status, values.get("attempt_resolution")))

    with pytest.raises(RuntimeError):
        service._run_default_resumable(
            contract,
            request,
            update,
            task_id=contract.task_id,
            attempt_id=state["attempt_id"],
        )

    verified_checkpoints = [v for s, v in checkpoint_history if s == "VERIFIED"]
    assert len(verified_checkpoints) == 0


def test_close_retained_without_candidate_success_with_missing_target(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-no-candidate-001"
    target_path = tmp_path / "targets" / task_id
    assert not target_path.exists()

    state = {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": task_id,
        "status": "RETAINED_FOR_REVIEW",
        "submitted_at": "2026-07-28T10:00:00+00:00",
        "status_history": [{"status": "RETAINED_FOR_REVIEW", "at": "2026-07-28T10:00:00+00:00"}],
        "request": _request(tmp_path, task_id=task_id),
        "contract": service.build_contract(_request(tmp_path, task_id=task_id)).model_dump(mode="json"),
        "target_worktree": str(target_path),
        "controller_worktree": str(tmp_path / "controller"),
        "attempt_id": "att-001",
        "promotion_status": "NOT_CREATED",
        "worker_pid": None,
        "execution": {"provider": "codex", "outcome": "EXECUTION_FAILED"},
        "error": "worker crashed before candidate",
        "cleanup_decision": "REMOVED",
        "cleanup_eligible": True,
        "cleanup_performed": True,
        "cleanup_performed_at": "2026-07-28T10:05:00+00:00",
        "state_retention_status": "TERMINAL",
        "archive_eligible": False,
    }
    service._write_state(task_id, state)

    result = service.close_retained_without_candidate(task_id, superseded_by="ref-evidence-456")

    assert result["status"] == "SUPERSEDED"
    assert result["final_disposition"] == "SUPERSEDED"
    assert result["terminal_status"] == "SUPERSEDED"
    assert result["state_retention_status"] == "TERMINAL"
    assert result["archive_eligible"] is True
    assert result["merge_performed"] is False
    assert result["push_performed"] is False
    assert result["superseded_by"] == "ref-evidence-456"
    assert result["promotion_status"] == "NOT_CREATED"
    assert result["execution"] == {"provider": "codex", "outcome": "EXECUTION_FAILED"}
    assert result["error"] == "worker crashed before candidate"
    assert result["cleanup_decision"] == "REMOVED"
    assert result["cleanup_eligible"] is True
    assert result["cleanup_performed"] is True
    assert result["cleanup_performed_at"] == "2026-07-28T10:05:00+00:00"

    archive_result = service.archive_states(dry_run=False)
    assert any(entry["task_id"] == task_id for entry in archive_result["entries"])


def test_close_retained_without_candidate_accepts_hash_only_diagnostics(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-no-candidate-hash-only"
    target_path = tmp_path / "targets" / task_id
    assert not target_path.exists()

    state = {
        "task_id": task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "target_worktree": str(target_path),
        "candidate_state_hash": "c" * 64,
        "verified_receipt_hash": "d" * 64,
        "verified_receipt": {"candidate_state_hash": "c" * 64},
        "candidate": {"candidate_state_hash": "c" * 64, "commit_created": False},
        "promotion_packet": None,
        "candidate_commit_sha": None,
        "candidate_ref": None,
        "candidate_commit_created": False,
    }
    service._write_state(task_id, state)

    result = service.close_retained_without_candidate(
        task_id,
        superseded_by="integration:hash-only-diagnostics-covered",
    )

    assert result["status"] == "SUPERSEDED"
    assert result["promotion_status"] == "NOT_CREATED"
    assert result["superseded_by"] == "integration:hash-only-diagnostics-covered"
    assert result["merge_performed"] is False
    assert result["push_performed"] is False


def test_close_retained_without_candidate_fails_closed_missing_superseded_by(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-no-candidate-002"
    state = {
        "task_id": task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "target_worktree": str(tmp_path / "nonexistent"),
    }
    service._write_state(task_id, state)

    with pytest.raises(ValueError, match="superseded_by"):
        service.close_retained_without_candidate(task_id, superseded_by="")

    with pytest.raises(ValueError, match="superseded_by"):
        service.close_retained_without_candidate(task_id, superseded_by="   ")


def test_close_retained_without_candidate_fails_closed_wrong_status(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-no-candidate-003"
    state = {
        "task_id": task_id,
        "status": "FINAL_BLOCK",
        "promotion_status": "NOT_CREATED",
        "target_worktree": str(tmp_path / "nonexistent"),
    }
    service._write_state(task_id, state)

    with pytest.raises(RuntimeError, match="RETAINED_FOR_REVIEW"):
        service.close_retained_without_candidate(task_id, superseded_by="ref-123")


def test_close_retained_without_candidate_fails_closed_candidate_present(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-no-candidate-004"
    state = {
        "task_id": task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "PENDING_HUMAN_APPROVAL",
        "candidate_commit_sha": "a" * 40,
        "target_worktree": str(tmp_path / "nonexistent"),
    }
    service._write_state(task_id, state)

    with pytest.raises(RuntimeError):
        service.close_retained_without_candidate(task_id, superseded_by="ref-123")


def test_close_retained_without_candidate_fails_closed_active_process(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-no-candidate-005"
    state = {
        "task_id": task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "worker_pid": 12345,
        "target_worktree": str(tmp_path / "nonexistent"),
    }
    service._write_state(task_id, state)

    monkeypatch.setattr(service, "_pid_alive", staticmethod(lambda pid: True))

    with pytest.raises(RuntimeError, match="active worker process"):
        service.close_retained_without_candidate(task_id, superseded_by="ref-123")


def test_close_retained_without_candidate_fails_closed_active_child_pgid(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-no-candidate-005b"
    state = {
        "task_id": task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "worker_pid": None,
        "worker_child_pgid": 54321,
        "target_worktree": str(tmp_path / "nonexistent"),
    }
    service._write_state(task_id, state)

    monkeypatch.setattr(service, "_pid_alive", staticmethod(lambda pid: True))

    with pytest.raises(RuntimeError, match="active worker child process"):
        service.close_retained_without_candidate(task_id, superseded_by="ref-123")


def test_close_retained_without_candidate_fails_closed_existing_dirty_target(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-no-candidate-006"
    target_dir = tmp_path / "targets" / task_id
    target_dir.mkdir(parents=True)
    (target_dir / "dirty.txt").write_text("unsaved work")

    state = {
        "task_id": task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "target_worktree": str(target_dir),
    }
    service._write_state(task_id, state)

    with pytest.raises(RuntimeError, match="Target path exists"):
        service.close_retained_without_candidate(task_id, superseded_by="ref-123")


def test_close_task_without_candidate_final_block_success(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "final-block-no-candidate-001"
    target_path = tmp_path / "targets" / task_id
    assert not target_path.exists()

    state = {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": task_id,
        "status": "FINAL_BLOCK",
        "submitted_at": "2026-07-28T10:00:00+00:00",
        "status_history": [{"status": "FINAL_BLOCK", "at": "2026-07-28T10:00:00+00:00"}],
        "request": _request(tmp_path, task_id=task_id),
        "contract": service.build_contract(_request(tmp_path, task_id=task_id)).model_dump(mode="json"),
        "target_worktree": str(target_path),
        "controller_worktree": str(tmp_path / "controller"),
        "attempt_id": "att-001",
        "promotion_status": "NOT_CREATED",
        "worker_pid": None,
        "execution": {"provider": "codex", "outcome": "EXECUTION_FAILED"},
        "error": "worker crashed without producing candidate",
        "cleanup_decision": "REMOVED",
        "cleanup_eligible": True,
        "cleanup_performed": True,
        "cleanup_performed_at": "2026-07-28T10:05:00+00:00",
        "state_retention_status": "TERMINAL",
        "archive_eligible": False,
    }
    service._write_state(task_id, state)

    actionable_before = service.list_actionable_tasks()
    assert any(t["task_id"] == task_id for t in actionable_before["tasks"])

    result = service.close_task_without_candidate(task_id, superseded_by="ref-evidence-789")

    assert result["status"] == "SUPERSEDED"
    assert result["final_disposition"] == "SUPERSEDED"
    assert result["terminal_status"] == "SUPERSEDED"
    assert result["state_retention_status"] == "TERMINAL"
    assert result["archive_eligible"] is True
    assert result["superseded_by"] == "ref-evidence-789"
    assert result["promotion_status"] == "NOT_CREATED"

    actionable_after = service.list_actionable_tasks()
    assert not any(t["task_id"] == task_id for t in actionable_after["tasks"])


def test_close_task_without_candidate_retained_for_review_success(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "retained-gen-no-candidate-001"
    target_path = tmp_path / "targets" / task_id
    assert not target_path.exists()

    state = {
        "task_id": task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "target_worktree": str(target_path),
    }
    service._write_state(task_id, state)

    result = service.close_task_without_candidate(task_id, superseded_by="ref-gen-123")

    assert result["status"] == "SUPERSEDED"
    assert result["superseded_by"] == "ref-gen-123"


def test_close_task_without_candidate_fails_closed_other_status(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    task_id = "other-status-no-candidate-001"
    state = {
        "task_id": task_id,
        "status": "SUBMITTED",
        "promotion_status": "NOT_CREATED",
        "target_worktree": str(tmp_path / "nonexistent"),
    }
    service._write_state(task_id, state)

    with pytest.raises(RuntimeError, match="RETAINED_FOR_REVIEW or FINAL_BLOCK"):
        service.close_task_without_candidate(task_id, superseded_by="ref-123")
