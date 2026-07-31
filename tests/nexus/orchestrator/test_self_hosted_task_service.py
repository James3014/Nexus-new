import copy
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

repo_root = str(Path(__file__).resolve().parents[3])
if repo_root in sys.path:
    sys.path.remove(repo_root)
sys.path.insert(0, repo_root)

import pytest

from nexus.executors.worker_contract import WorkerExecutionReceipt, WorkerOutcome, WorkerPreflight
from nexus.executors.worker_registry import WorkerRegistry
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.worktree_manager import TargetWorktreeLease, WorktreeManager


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
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", *args],
        cwd=cwd, check=True, capture_output=True, text=True, env=env,
    ).stdout.strip()


def _init_repo(path: Path) -> None:
    """Initialize a git repo with hooks disabled, regardless of user global config."""
    _git(path, "init", "-b", "main")
    _git(path, "config", "core.hooksPath", "/dev/null")


def _real_request(tmp_path: Path, task_id: str = "real-reconcile"):
    controller = tmp_path / "controller"
    controller.mkdir(exist_ok=True)
    git_dir = controller / ".git"
    if not git_dir.exists():
        _init_repo(controller)
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

    from nexus.orchestrator.governed_integration import IntegrationReceipt

    class SuccessfulIntegration:
        def __init__(self, integration_root):
            pass
        def integrate_task_state(self, state, integration_branch):
            calls.append(integration_branch)
            return IntegrationReceipt(
                schema="nexus.integration_receipt/v1",
                task_id="integration-once",
                integration_branch=integration_branch,
                source_branch="nexus/task/integration-once",
                candidate_commit_sha="c" * 40,
                integration_base_sha="b" * 40,
                integration_commit_sha="c" * 40,
                verifier_passed=True,
                merge_performed=True,
                push_performed=False,
                worktree_removed=True,
            )

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager", SuccessfulIntegration)
    first = service.integrate_approved("integration-once")
    second = service.integrate_approved("integration-once")

    assert first == second
    assert calls == ["nexus/integration/main"]
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
    service.wait_task("wait-timeout", timeout_seconds=2.0)


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


def test_list_actionable_tasks_is_compact_and_does_not_reconcile(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("blocked", {
        "task_id": "blocked",
        "status": "FINAL_BLOCK",
        "promotion_status": "NOT_CREATED",
        "error": "worker failed",
        "request": {"large": "x" * 10000},
    })

    def fail_reconcile(_task_id):
        raise AssertionError("list_actionable_tasks must not reconcile task state")

    monkeypatch.setattr(service, "reconcile_task", fail_reconcile)
    result = service.list_actionable_tasks()

    assert result["details_included"] is False
    assert result["actionable_count"] == 1
    assert result["tasks"][0]["task_id"] == "blocked"
    assert "error" not in result["tasks"][0]


def test_workspace_inventory_plan_and_slot_status_are_read_only(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="workspace-service")
    contract = service.build_contract(request)
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    before = sorted(path.name for path in (tmp_path / "state").iterdir())

    inventory = service.workspace_inventory(controller_root=contract.controller_repo_root)
    plan = service.workspace_convergence_plan(
        controller_root=contract.controller_repo_root,
        expected_controller_revision=contract.controller_revision,
    )
    slot = service.workspace_slot_status(
        campaign_id="workspace-service",
        controller_root=contract.controller_repo_root,
    )

    assert inventory["schema"] == "nexus.workspace_inventory.v1"
    assert plan["schema"] == "nexus.workspace_convergence_plan.v1"
    assert plan["controller_revision"] == contract.controller_revision
    assert slot["status"] in {"READY", "BLOCKED"}
    assert Path(lease.target_worktree).exists()
    assert sorted(path.name for path in (tmp_path / "state").iterdir()) == before


def test_workspace_apply_requires_exact_plan_binding(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="workspace-apply")
    contract = service.build_contract(request)
    plan = service.workspace_convergence_plan(controller_root=contract.controller_repo_root)

    with pytest.raises(RuntimeError, match="PLAN_HASH_MISMATCH"):
        service.apply_workspace_convergence(
            controller_root=contract.controller_repo_root,
            expected_controller_revision=contract.controller_revision,
            expected_plan_hash="0" * 64,
            apply=True,
        )

    preview = service.apply_workspace_convergence(
        controller_root=contract.controller_repo_root,
        expected_controller_revision=contract.controller_revision,
        expected_plan_hash=plan["plan_hash"],
        apply=False,
    )
    assert preview["applied"] is False
    assert preview["next_gate"] == "EXPLICIT_APPLY"


def test_workspace_slot_prepare_is_idempotent_and_reuses_same_path(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="slot-service")

    first = service.workspace_slot_prepare(request, campaign_id="slot-campaign", slot_index=0)
    second = service.workspace_slot_prepare(request, campaign_id="slot-campaign", slot_index=0)

    assert first["status"] == "READY"
    assert second["status"] == "READY"
    assert first["slot_path"] == second["slot_path"]
    assert Path(first["slot_path"]).exists()


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


def test_close_retained_dirty_salvage_requires_integrated_replacement(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    request = _real_request(tmp_path, task_id="retained-salvage-gated")
    contract = service.build_contract(request)
    from nexus.orchestrator.worktree_manager import WorktreeManager
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "dirty.txt").write_text("verifier side effect\n", encoding="utf-8")
    service._write_state(request["task_id"], {
        "task_id": request["task_id"],
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "target_worktree": str(target),
        "attempt_id": "attempt-salvage-gated",
        "worker_pid": None,
        "worker_child_pgid": None,
    })

    with pytest.raises(RuntimeError, match="superseded_by must name"):
        service.close_retained_without_candidate(
            request["task_id"], superseded_by="missing-integrated-task"
        )

    assert target.exists()
    assert (target / "dirty.txt").exists()
    assert service._read_state(request["task_id"])["status"] == "RETAINED_FOR_REVIEW"


def test_close_retained_dirty_salvage_rejects_mismatched_replacement_identity(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    request = _real_request(tmp_path, task_id="retained-salvage-identity-gated")
    contract = service.build_contract(request)
    from nexus.orchestrator.worktree_manager import WorktreeManager
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "dirty.txt").write_text("must remain untouched\n", encoding="utf-8")
    replacement_id = "integrated-replacement-requested"
    service._write_state(replacement_id, {
        "task_id": "different-integrated-task",
        "status": "INTEGRATED",
        "promotion_status": "INTEGRATED",
        "integration_result_sha": "i" * 40,
    })
    service._write_state(request["task_id"], {
        "task_id": request["task_id"],
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "target_worktree": str(target),
        "attempt_id": "attempt-salvage-identity-gated",
        "worker_pid": None,
        "worker_child_pgid": None,
    })

    controller = Path(request["controller_repo_root"])
    refs_before = _git(controller, "show-ref")
    worktrees_before = _git(controller, "worktree", "list", "--porcelain")

    with pytest.raises(RuntimeError, match="superseded_by must name"):
        service.close_retained_without_candidate(
            request["task_id"], superseded_by=replacement_id
        )

    assert target.exists()
    assert (target / "dirty.txt").read_text(encoding="utf-8") == "must remain untouched\n"
    assert _git(controller, "show-ref") == refs_before
    assert _git(
        controller,
        "for-each-ref",
        "--format=%(refname)",
        "refs/nexus-salvage/worktree/",
    ) == ""
    assert _git(controller, "worktree", "list", "--porcelain") == worktrees_before
    assert service._read_state(request["task_id"])["status"] == "RETAINED_FOR_REVIEW"


def test_close_retained_dirty_salvage_protects_ref_and_never_becomes_candidate(tmp_path, monkeypatch):
    for env_var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(env_var, raising=False)
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    request = _real_request(tmp_path, task_id="retained-salvage-success")
    contract = service.build_contract(request)
    from nexus.orchestrator.worktree_manager import WorktreeManager
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "README").write_text("dirty verifier state\n", encoding="utf-8")
    (target / "untracked.txt").write_text("complete salvage\n", encoding="utf-8")
    replacement_id = "integrated-replacement"
    service._write_state(replacement_id, {
        "task_id": replacement_id,
        "status": "INTEGRATED",
        "promotion_status": "INTEGRATED",
        "integration_result_sha": "i" * 40,
    })
    service._write_state(request["task_id"], {
        "task_id": request["task_id"],
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "target_worktree": str(target),
        "attempt_id": "attempt-salvage-success",
        "worker_pid": None,
        "worker_child_pgid": None,
    })

    result = service.close_retained_without_candidate(
        request["task_id"], superseded_by=replacement_id
    )

    salvage_commit = result["salvage_commit_sha"]
    salvage_ref = result["salvage_ref"]
    controller = Path(request["controller_repo_root"])
    assert result["status"] == "SUPERSEDED"
    assert result["promotion_status"] == "NOT_CREATED"
    assert result["salvage_only"] is True
    assert result["promotion_eligible"] is False
    assert result["superseded_by"] == replacement_id
    assert result.get("candidate_commit_sha") is None
    assert result.get("candidate_ref") is None
    assert result.get("promotion_packet") is None
    assert not target.exists()
    assert _git(controller, "rev-parse", salvage_ref) == salvage_commit
    assert _git(controller, "show", "-s", "--format=%an", salvage_commit) == "Nexus Salvage Bot"
    assert _git(controller, "show", "-s", "--format=%ae", salvage_commit) == "nexus-salvage-bot@nexus.local"
    assert _git(controller, "show", "-s", "--format=%s", salvage_commit) == (
        "Nexus Salvage Bot: salvage-only snapshot retained-salvage-success/attempt-salvage-success"
    )
    assert _git(controller, "show", f"{salvage_commit}:untracked.txt") == "complete salvage"


def test_close_retained_dirty_salvage_ref_mismatch_keeps_target_and_task_retained(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    request = _real_request(tmp_path, task_id="retained-salvage-ref-failure")
    contract = service.build_contract(request)
    from nexus.orchestrator.worktree_manager import WorktreeManager
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "dirty.txt").write_text("must remain\n", encoding="utf-8")
    replacement_id = "integrated-replacement-ref-failure"
    service._write_state(replacement_id, {
        "task_id": replacement_id,
        "status": "INTEGRATED",
        "promotion_status": "INTEGRATED",
        "integration_result_sha": "r" * 40,
    })
    service._write_state(request["task_id"], {
        "task_id": request["task_id"],
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "target_worktree": str(target),
        "attempt_id": "attempt-salvage-ref-failure",
        "worker_pid": None,
        "worker_child_pgid": None,
    })
    original = WorktreeManager.create_salvage_snapshot

    def mismatched_ref(self, contract, lease, attempt_id):
        snapshot = original(self, contract, lease, attempt_id)
        return {**snapshot, "salvage_ref": snapshot["salvage_ref"] + "-mismatch"}

    monkeypatch.setattr(WorktreeManager, "create_salvage_snapshot", mismatched_ref)

    result = service.close_retained_without_candidate(
        request["task_id"], superseded_by=replacement_id
    )

    assert result["status"] == "RETAINED_FOR_REVIEW"
    assert result["cleanup_decision"] == "BLOCKED_BY_MISSING_REF"
    assert result["salvage_only"] is True
    assert result["promotion_eligible"] is False
    assert target.exists()
    assert result["promotion_status"] == "NOT_CREATED"
    assert result.get("candidate_commit_sha") is None
    assert result.get("candidate_ref") is None


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


# --- 00c: Self-hosted Retained Target Auto Closeout RED tests ---

def test_cleanup_retained_dirty_target_salvages_and_removes(tmp_path, monkeypatch):
    """RED: retained dirty Target currently remains registered after cleanup_tasks(..., dry_run=False)."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="retained-dirty-cleanup")
    contract = service.build_contract(request)
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "dirty.txt").write_text("dirty work\n", encoding="utf-8")
    for env_var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(env_var, raising=False)
    service._write_state(contract.task_id, {
        "task_id": contract.task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "attempt_id": "att-retained-dirty",
        "worker_pid": None,
        "worker_child_pgid": None,
    })

    result = service.cleanup_tasks(task_id=contract.task_id, dry_run=False)
    decision = result["decisions"][0]
    state_after = service._read_state(contract.task_id)

    assert decision["cleanup_decision"] != "BLOCKED_BY_UNSAVED_CHANGES", (
        "retained dirty Target should not be blocked by unsaved changes when salvage is available"
    )
    assert decision["cleanup_performed"] is True
    assert not target.exists(), "Target worktree should be removed after salvage"
    assert state_after["status"] == "RETAINED_FOR_REVIEW"
    assert state_after.get("salvage_commit_sha") is not None
    assert state_after.get("salvage_ref") is not None


def test_cleanup_retained_clean_changed_head_salvages_head_and_removes(tmp_path):
    """RED: retained clean changed-HEAD Target currently remains registered without a durable binding."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="retained-clean-head-cleanup")
    contract = service.build_contract(request)
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    _git(target, "config", "user.name", "Test")
    _git(target, "config", "user.email", "test@example.com")
    _git(target, "commit", "--allow-empty", "-m", "drift")
    assert _git(target, "rev-parse", "HEAD") != lease.initial_head
    service._write_state(contract.task_id, {
        "task_id": contract.task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "attempt_id": "att-retained-clean-head",
        "worker_pid": None,
        "worker_child_pgid": None,
    })

    result = service.cleanup_tasks(task_id=contract.task_id, dry_run=False)
    decision = result["decisions"][0]

    assert decision["cleanup_performed"] is True
    assert not target.exists()


def test_cleanup_retained_discover_existing_salvage_ref(tmp_path, monkeypatch):
    """RED: existing exact salvage ref currently is not discovered when state metadata is absent."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="retained-existing-salvage")
    contract = service.build_contract(request)
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "dirty.txt").write_text("salvage me\n", encoding="utf-8")
    for env_var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(env_var, raising=False)
    attempt_id = "att-existing-salvage"
    snapshot = manager.create_salvage_snapshot(contract, lease, attempt_id)
    salvage_ref = snapshot["salvage_ref"]
    salvage_commit = snapshot["salvage_commit_sha"]
    service._write_state(contract.task_id, {
        "task_id": contract.task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "attempt_id": attempt_id,
        "worker_pid": None,
        "worker_child_pgid": None,
    })

    result = service.cleanup_tasks(task_id=contract.task_id, dry_run=False)
    decision = result["decisions"][0]
    state_after = service._read_state(contract.task_id)

    assert decision["cleanup_performed"] is True
    assert not target.exists()
    assert state_after["status"] == "RETAINED_FOR_REVIEW"
    assert state_after.get("salvage_commit_sha") == salvage_commit
    assert state_after.get("salvage_ref") == salvage_ref


def test_cleanup_retained_active_process_preserves_target(tmp_path, monkeypatch):
    """RED: active process must not allow Target removal."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="retained-active-process")
    contract = service.build_contract(request)
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    service._write_state(contract.task_id, {
        "task_id": contract.task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "attempt_id": "att-retained-active",
        "worker_pid": 12345,
        "worker_child_pgid": None,
    })
    monkeypatch.setattr(SelfHostedTaskService, "_pid_alive", staticmethod(lambda pid: True))

    result = service.cleanup_tasks(task_id=contract.task_id, dry_run=False)
    decision = result["decisions"][0]

    assert decision["cleanup_performed"] is False
    assert target.exists()


def test_cleanup_retained_dry_run_does_not_mutate_state(tmp_path, monkeypatch):
    """RED: dry-run currently cannot describe a salvage-and-remove plan because retained tasks are rejected."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="retained-dry-run")
    contract = service.build_contract(request)
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    (target / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    for env_var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(env_var, raising=False)
    service._write_state(contract.task_id, {
        "task_id": contract.task_id,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "lease": lease.__dict__,
        "attempt_id": "att-retained-dry-run",
        "worker_pid": None,
        "worker_child_pgid": None,
    })

    result = service.cleanup_tasks(task_id=contract.task_id, dry_run=True)
    decision = result["decisions"][0]
    state_after = service._read_state(contract.task_id)

    assert decision["cleanup_performed"] is False
    assert target.exists(), "dry-run must not remove Target"
    assert state_after.get("salvage_commit_sha") is None, "dry-run must not create salvage"
    assert state_after.get("salvage_ref") is None, "dry-run must not record salvage ref"


# ---------- LC2: terminal failure restore wiring tests ----------


class _FailingRunner:
    """Runner that raises to trigger the terminal-failure exception handler."""

    def __init__(self, exc: Exception = None):
        self._exc = exc or RuntimeError("deliberate terminal failure")

    def __call__(self, contract, request, update):
        raise self._exc


def _setup_lc2_task(tmp_path, service, task_id):
    """Create a real task with lease for LC2 testing."""
    request = _real_request(tmp_path, task_id=task_id)
    contract = service.build_contract(request)
    manager = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = manager.create_lease(contract)
    attempt_id = "att-" + task_id
    service._write_state(task_id, {
        "task_id": task_id,
        "status": "LEASED",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash,
        "lease": lease.__dict__,
        "attempt_id": attempt_id,
        "worker_pid": None,
        "worker_child_pgid": None,
    })
    return contract, lease, attempt_id


def test_run_owned_task_terminal_failure_calls_restore(tmp_path, monkeypatch):
    """Happy path: salvage + cleanup REMOVED → restore called with RESTORED."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "lc2-restore"
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    restore_called = {"n": 0}

    class SpyManager:
        def __init__(self, root_dir):
            pass

        def cleanup_terminal_target(self, contract, lease, **kw):
            if kw.get("salvage_commit"):
                return SimpleNamespace(decision="REMOVED", blocker=None, performed=True, eligible=True)
            return SimpleNamespace(decision="BLOCKED_BY_UNSAVED_CHANGES", blocker="dirty", performed=False, eligible=True)

        def create_salvage_snapshot(self, contract, lease, attempt_id):
            return {"salvage_commit_sha": "c" * 40, "salvage_ref": "refs/nexus-salvages/lc2-restore"}

        def restore_task_branch_for_retry(self, contract, lease, salvage_commit, salvage_ref):
            restore_called["n"] += 1
            assert salvage_commit == "c" * 40
            return {"decision": "RESTORED", "restored_to": "b" * 40}

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", SpyManager)
    service._custom_runner = _FailingRunner()
    # Directly invoke _run_owned_task (bypasses submit_task lease creation)
    service._run_owned_task(task_id, attempt_id)

    state = service._read_state(task_id)
    assert restore_called["n"] == 1
    assert state["task_branch_restore_decision"] == "RESTORED"
    assert state["task_branch_restored_to"] == "b" * 40
    assert state["task_branch_restore_performed"] is True
    assert state["task_branch_restore_verified"] is True
    assert state["salvage_commit_sha"] == "c" * 40
    assert state["salvage_ref"] == "refs/nexus-salvages/lc2-restore"


def test_run_owned_task_terminal_failure_already_restored(tmp_path, monkeypatch):
    """Second failure: restore sees ALREADY_RESTORED → state recorded, no mutation."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "lc2-already-restored"
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    restore_calls = {"n": 0}

    class SpyManager:
        def __init__(self, root_dir):
            pass

        def cleanup_terminal_target(self, contract, lease, **kw):
            if kw.get("salvage_commit"):
                return SimpleNamespace(decision="REMOVED", blocker=None, performed=True, eligible=True)
            return SimpleNamespace(decision="BLOCKED_BY_UNSAVED_CHANGES", blocker="dirty", performed=False, eligible=True)

        def create_salvage_snapshot(self, contract, lease, attempt_id):
            return {"salvage_commit_sha": "c" * 40, "salvage_ref": "refs/nexus-salvages/lc2-already-restored"}

        def restore_task_branch_for_retry(self, contract, lease, salvage_commit, salvage_ref):
            restore_calls["n"] += 1
            return {"decision": "ALREADY_RESTORED", "restored_to": "b" * 40}

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", SpyManager)
    service._custom_runner = _FailingRunner()
    service._run_owned_task(task_id, attempt_id)

    state = service._read_state(task_id)
    assert restore_calls["n"] == 1
    assert state["task_branch_restore_decision"] == "ALREADY_RESTORED"
    assert state["salvage_commit_sha"] == "c" * 40


def test_run_owned_task_terminal_failure_restored_with_state_writeback(tmp_path, monkeypatch):
    """Verify all six state fields are written after RESTORED."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "lc2-writeback"
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    class SpyManager:
        def __init__(self, root_dir):
            pass

        def cleanup_terminal_target(self, contract, lease, **kw):
            if kw.get("salvage_commit"):
                return SimpleNamespace(decision="REMOVED", blocker=None, performed=True, eligible=True)
            return SimpleNamespace(decision="BLOCKED_BY_UNSAVED_CHANGES", blocker="dirty", performed=False, eligible=True)

        def create_salvage_snapshot(self, contract, lease, attempt_id):
            return {"salvage_commit_sha": "c" * 40, "salvage_ref": "refs/nexus-salvages/lc2-wb"}

        def restore_task_branch_for_retry(self, contract, lease, salvage_commit, salvage_ref):
            return {"decision": "RESTORED", "restored_to": "b" * 40}

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", SpyManager)
    service._custom_runner = _FailingRunner()
    service._run_owned_task(task_id, attempt_id)

    state = service._read_state(task_id)
    for key in ("task_branch_restore_decision", "task_branch_restored_to",
                 "task_branch_restore_performed", "task_branch_restore_verified",
                 "salvage_commit_sha", "salvage_ref"):
        assert key in state and state[key] is not None, f"missing or None: {key}"
    assert state["task_branch_restore_performed"] is True
    assert state["task_branch_restore_verified"] is True


def test_run_owned_task_terminal_failure_restore_failure(tmp_path, monkeypatch):
    """restore_task_branch_for_retry raises → RESTORE_BLOCKED, RETAINED_FOR_REVIEW."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "lc2-restore-fail"
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    class SpyManager:
        def __init__(self, root_dir):
            pass

        def cleanup_terminal_target(self, contract, lease, **kw):
            if kw.get("salvage_commit"):
                return SimpleNamespace(decision="REMOVED", blocker=None, performed=True, eligible=True)
            return SimpleNamespace(decision="BLOCKED_BY_UNSAVED_CHANGES", blocker="dirty", performed=False, eligible=True)

        def create_salvage_snapshot(self, contract, lease, attempt_id):
            return {"salvage_commit_sha": "c" * 40, "salvage_ref": "refs/nexus-salvages/lc2-rf"}

        def restore_task_branch_for_retry(self, contract, lease, salvage_commit, salvage_ref):
            raise RuntimeError("restore validation failed: bad parent")

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", SpyManager)
    service._custom_runner = _FailingRunner()
    service._run_owned_task(task_id, attempt_id)

    state = service._read_state(task_id)
    assert state["task_branch_restore_decision"] == "RESTORE_BLOCKED"
    assert state["task_branch_restore_performed"] is False
    assert state["task_branch_restore_verified"] is False
    assert state["terminal_status"] == "RETAINED_FOR_REVIEW"


def test_run_owned_task_terminal_failure_salvage_failure(tmp_path, monkeypatch):
    """create_salvage_snapshot raises → CLEANUP_BLOCKED, no restore called."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "lc2-salvage-fail"
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    restore_called = {"n": 0}

    class SpyManager:
        def __init__(self, root_dir):
            pass

        def cleanup_terminal_target(self, contract, lease, **kw):
            return SimpleNamespace(decision="BLOCKED_BY_UNSAVED_CHANGES", blocker="dirty", performed=False, eligible=True)

        def create_salvage_snapshot(self, contract, lease, attempt_id):
            raise RuntimeError("git snapshot failed: permission denied")

        def restore_task_branch_for_retry(self, contract, lease, salvage_commit, salvage_ref):
            restore_called["n"] += 1
            return {"decision": "RESTORED", "restored_to": "b" * 40}

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", SpyManager)
    service._custom_runner = _FailingRunner()
    service._run_owned_task(task_id, attempt_id)

    state = service._read_state(task_id)
    assert state["cleanup_decision"] == "CLEANUP_BLOCKED"
    assert "permission denied" in state["cleanup_blocker"]
    assert restore_called["n"] == 0
    assert state.get("task_branch_restore_decision") is None


def test_run_owned_task_terminal_failure_cleanup_blocked(tmp_path, monkeypatch):
    """cleanup_terminal_target raises → CLEANUP_BLOCKED, no restore."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "lc2-cleanup-blocked"
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    restore_called = {"n": 0}

    class SpyManager:
        def __init__(self, root_dir):
            pass

        def cleanup_terminal_target(self, contract, lease, **kw):
            raise RuntimeError("cleanup failed: git lock held")

        def create_salvage_snapshot(self, contract, lease, attempt_id):
            return {"salvage_commit_sha": "c" * 40, "salvage_ref": "refs/nexus-salvages/lc2-cb"}

        def restore_task_branch_for_retry(self, contract, lease, salvage_commit, salvage_ref):
            restore_called["n"] += 1
            return {"decision": "RESTORED", "restored_to": "b" * 40}

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", SpyManager)
    service._custom_runner = _FailingRunner()
    service._run_owned_task(task_id, attempt_id)

    state = service._read_state(task_id)
    assert state["cleanup_decision"] == "CLEANUP_BLOCKED"
    assert "git lock" in state["cleanup_blocker"]
    assert restore_called["n"] == 0


def test_run_owned_task_terminal_failure_no_lease(tmp_path, monkeypatch):
    """No lease in state → no cleanup, no restore, FINAL_BLOCK."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="lc2-no-lease")
    task_id = request["task_id"]
    service._write_state(task_id, {
        "task_id": task_id,
        "status": "SUBMITTED",
        "promotion_status": "NOT_CREATED",
        "request": request,
        "attempt_id": "att-no-lease",
        "worker_pid": None,
        "worker_child_pgid": None,
        # no lease
    })

    service._custom_runner = _FailingRunner()
    service._run_owned_task(task_id, "att-no-lease")

    state = service._read_state(task_id)
    assert state["status"] == "FINAL_BLOCK"
    assert state["terminal_status"] == "FINAL_BLOCK"
    assert state.get("cleanup_decision") == "ALREADY_REMOVED"
    assert state.get("task_branch_restore_decision") is None


def test_run_owned_task_terminal_failure_restore_already_restored_with_state(tmp_path, monkeypatch):
    """ALREADY_RESTORED with salvage metadata written by a prior run → state fields consistent."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "lc2-ar-state"
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    # Simulate prior run already wrote salvage metadata
    service._write_state(task_id, {
        **service._read_state(task_id),
        "salvage_commit_sha": "c" * 40,
        "salvage_ref": "refs/nexus-salvages/lc2-ar-state",
        "task_branch_restored_to": "b" * 40,
        "task_branch_restore_decision": "RESTORED",
    })

    class SpyManager:
        def __init__(self, root_dir):
            pass

        def cleanup_terminal_target(self, contract, lease, **kw):
            if kw.get("salvage_commit"):
                return SimpleNamespace(decision="REMOVED", blocker=None, performed=True, eligible=True)
            return SimpleNamespace(decision="BLOCKED_BY_UNSAVED_CHANGES", blocker="dirty", performed=False, eligible=True)

        def create_salvage_snapshot(self, contract, lease, attempt_id):
            return {"salvage_commit_sha": "c" * 40, "salvage_ref": "refs/nexus-salvages/lc2-ar-state"}

        def restore_task_branch_for_retry(self, contract, lease, salvage_commit, salvage_ref):
            return {"decision": "ALREADY_RESTORED", "restored_to": "b" * 40}

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.WorktreeManager", SpyManager)
    service._custom_runner = _FailingRunner()
    service._run_owned_task(task_id, attempt_id)

    state = service._read_state(task_id)
    assert state["task_branch_restore_decision"] == "ALREADY_RESTORED"
    assert state["salvage_commit_sha"] == "c" * 40
    assert state["salvage_ref"] == "refs/nexus-salvages/lc2-ar-state"
    assert state["task_branch_restored_to"] == "b" * 40


# ---------- LC3: Real timeout / salvage / retry canary ----------




def test_lc3_service_path_canary(tmp_path, monkeypatch):
    """LC3: Formal service-path canary for timeout/salvage/retry.

    Flow through formal service path:
    1. Pre-set state with SUBMITTED + lease pointing to real Target worktree
    2. Custom runner creates dirty mutation in allowed path, raises timeout
    3. _run_default_resumable exception propagates to _run_owned_task handler
    4. Exception handler: salvage commit/ref → cleanup REMOVED → restore → terminal
    5. Retry with refreshed revision → new attempt, detached Target

    Prohibited: manual create_salvage_snapshot, cleanup_terminal_target,
    restore_task_branch_for_retry, _write_state to manufacture terminal receipt.
    """
    # --- Phase 1: Real controller and target repos ---
    controller = tmp_path / "controller"
    controller.mkdir()
    _init_repo(controller)
    _git(controller, "config", "user.name", "LC3 Service Test")
    _git(controller, "config", "user.email", "lc3-svc@test.com")
    (controller / "README").write_text("base\n")
    _git(controller, "add", "README")
    _git(controller, "commit", "-m", "base commit")
    base_sha = _git(controller, "rev-parse", "HEAD")

    target_root = tmp_path / "targets"
    target_root.mkdir()

    request = {
        "task_id": "lc3-svc-canary",
        "what": "lc3 service path canary",
        "why": "prove formal exception path",
        "controller_revision": base_sha,
        "target_base_revision": base_sha,
        "controller_repo_root": str(controller),
        "target_repo_root": str(target_root / "lc3-svc-canary"),
        "target_worktree_root": str(target_root),
        "allowed_files": ["src/"],
        "forbidden_files": [],
        "verifier_commands": [],
        "protected_contracts": [],
        "worker": "codex",
    }

    # --- Phase 2: Create real lease (worktree) via WorktreeManager ---
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    manager = WorktreeManager(root_dir=str(target_root))
    contract = service.build_contract(request)
    lease = manager.create_lease(contract)
    target = Path(lease.target_worktree)
    assert target.exists(), "Target worktree must exist after real lease"

    # --- Phase 3: Pre-set state with SUBMITTED + lease ---
    attempt_id = "attempt-1-lc3-svc"
    service._write_state("lc3-svc-canary", {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": "lc3-svc-canary",
        "status": "WORKER_RUNNING",
        "submitted_at": "2026-01-01T00:00:00Z",
        "request": request,
        "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash,
        "controller_worktree": str(controller),
        "controller_revision": base_sha,
        "target_worktree": str(target),
        "target_branch": f"nexus/task/lc3-svc-canary",
        "attempt_id": attempt_id,
        "attempts": [{"attempt_id": attempt_id, "started_at": "2026-01-01T00:00:00Z"}],
        "lease": lease.__dict__,
        "worker_pid": None,
        "worker_child_pgid": None,
        "active_provider": "codex",
        "promotion_status": "NOT_CREATED",
        "execution_lane": "FAST_LANE",
        "fast_lane_eligible": True,
        "maximum_provider_calls": 1,
        "maximum_replans": 0,
        "fallback_disabled": True,
    })

    # --- Phase 4: Custom runner creates dirty mutation + raises timeout ---
    def timeout_runner(contract_arg, request_arg, update_fn):
        # Make dirty mutation in the allowed path
        src = target / "src"
        src.mkdir(exist_ok=True)
        (src / "worker.txt").write_text("dirty mutation\n", encoding="utf-8")
        raise RuntimeError("worker timeout: execution exceeded deadline")

    service._custom_runner = timeout_runner

    # --- Phase 5: Execute via _run_owned_task (formal exception path) ---
    service._run_owned_task("lc3-svc-canary", attempt_id)

    # --- Phase 6: Verify terminal state set by exception handler ---
    state = service._read_state("lc3-svc-canary")
    assert state is not None, "state must exist after exception handler"

    # Exception handler should have run salvage + cleanup + restore
    salvage_commit = state.get("salvage_commit_sha")
    salvage_ref = state.get("salvage_ref")
    assert salvage_commit, "salvage_commit_sha must be set by exception handler"
    assert salvage_ref, "salvage_ref must be set by exception handler"

    # Salvage ref resolves to salvage commit in controller
    resolved_salvage = _git(controller, "rev-parse", salvage_ref)
    assert resolved_salvage == salvage_commit, "salvage ref must resolve to salvage commit"

    # Cleanup decision
    cleanup_decision = state.get("cleanup_decision")
    assert cleanup_decision in {"REMOVED", "ALREADY_REMOVED"}, \
        f"cleanup must succeed, got {cleanup_decision}"

    # Restore decision
    restore_decision = state.get("task_branch_restore_decision")
    assert restore_decision in {"RESTORED", "ALREADY_RESTORED"}, \
        f"restore must succeed, got {restore_decision}"

    # Terminal status
    terminal_status = state.get("terminal_status")
    assert terminal_status in {"FINAL_BLOCK", "RETAINED_FOR_REVIEW"}, \
        f"terminal status must be set, got {terminal_status}"

    # Target no longer exists or is detached
    target_still_registered = False
    try:
        registered = manager._registered_worktrees(controller)
        target_still_registered = any(
            "worktree" in e and Path(e["worktree"]).resolve() == target.resolve()
            for e in registered
        )
    except Exception:
        pass
    assert not target_still_registered, "Target must not be registered after cleanup"

    # --- Phase 7: Revision-forward retry reactivates the task and permits a detached Target ---
    first_attempt_id = state["attempt_id"]
    (controller / "refreshed.txt").write_text("refreshed revision\n", encoding="utf-8")
    _git(controller, "add", "refreshed.txt")
    _git(controller, "commit", "-m", "refresh integration revision")
    refreshed_sha = _git(controller, "rev-parse", "HEAD")
    refreshed_request = {
        **request,
        "controller_revision": refreshed_sha,
        "target_base_revision": refreshed_sha,
    }

    # Keep the retry at SUBMITTED so the test can inspect the physical lease deterministically.
    monkeypatch.setattr(
        service,
        "_launch_worker",
        lambda task_id, attempt_id: service._read_state(task_id),
    )
    retried = service.submit_task(refreshed_request)
    assert retried["attempt_id"] != first_attempt_id
    assert retried["status"] == "SUBMITTED"

    refreshed_contract = service.build_contract(refreshed_request)
    retry_lease = manager.create_lease(refreshed_contract)
    assert retry_lease.target_detached is True
    assert retry_lease.initial_head == refreshed_sha
    assert Path(retry_lease.target_worktree).exists()


# ---------- W0: Read-only verification entrypoint tests ----------


def test_verify_task_returns_state_missing_for_unknown_task(tmp_path):
    """W0: verify_task returns STATE_MISSING for non-existent task."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    result = service.verify_task("nonexistent")
    assert result["verdict"] == "STATE_MISSING"
    assert result["verified"] is False
    assert "state_not_found" in result["failure_reasons"]
    assert result["provider_calls"] == 0


def test_verify_task_passes_for_valid_task(tmp_path):
    """W0: verify_task passes for a valid task with clean state."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="verify-valid")
    task_id = request["task_id"]
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    # Add a simple verifier command
    contract_data = service._read_state(task_id).get("contract", {})
    contract_data["verifier_commands"] = ["echo pass"]
    service._write_state(task_id, {
        **service._read_state(task_id),
        "contract": contract_data,
    })

    result = service.verify_task(task_id)
    assert result["verdict"] == "VERIFIED"
    assert result["verified"] is True
    assert result["provider_calls"] == 0
    assert result["failure_reasons"] == []
    assert result["state_intact"] is True
    assert "verifier_commands_executed" in result


def test_verify_task_detects_state_hash_drift(tmp_path):
    """W0: verify_task detects contract hash drift between reads."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="verify-drift")
    task_id = request["task_id"]
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    # Tamper with state between reads
    original_read = service._read_state
    call_count = {"n": 0}
    def tampering_read(task_id):
        state = original_read(task_id)
        call_count["n"] += 1
        if call_count["n"] == 2 and state:
            # Second read: tamper with contract_hash
            state = {**state, "contract_hash": "tampered"}
        return state
    service._read_state = tampering_read

    result = service.verify_task(task_id)
    assert result["verified"] is False
    assert "contract_hash_drift" in result["failure_reasons"]


def test_verify_task_detects_attempt_drift(tmp_path):
    """W0: verify_task detects attempt ID drift between reads."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="verify-attempt-drift")
    task_id = request["task_id"]
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    # Tamper with attempt_id between reads
    original_read = service._read_state
    call_count = {"n": 0}
    def tampering_read(task_id):
        state = original_read(task_id)
        call_count["n"] += 1
        if call_count["n"] == 2 and state:
            state = {**state, "attempt_id": "tampered_attempt"}
        return state
    service._read_state = tampering_read

    result = service.verify_task(task_id)
    assert result["verified"] is False
    assert "attempt_drift" in result["failure_reasons"]


def test_verify_task_detects_state_deletion(tmp_path):
    """W0: verify_task detects state deletion between reads."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="verify-deleted")
    task_id = request["task_id"]
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    # Delete state between reads
    original_read = service._read_state
    call_count = {"n": 0}
    def deleting_read(task_id):
        state = original_read(task_id)
        call_count["n"] += 1
        if call_count["n"] == 2:
            return None
        return state
    service._read_state = deleting_read

    result = service.verify_task(task_id)
    assert result["verified"] is False
    assert "state_deleted_between_reads" in result["failure_reasons"]


def test_verify_task_no_state_mutation(tmp_path):
    """W0: verify_task does not modify task state."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="verify-no-mutate")
    task_id = request["task_id"]
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    state_before = service._read_state(task_id)
    result = service.verify_task(task_id)
    state_after = service._read_state(task_id)

    # State must be identical
    assert state_before == state_after, "verify_task must not mutate state"
    assert result["verified"] is True


def test_verify_task_repeated_calls_consistent(tmp_path):
    """W0: repeated verify calls on same state produce consistent verdict."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="verify-consistent")
    task_id = request["task_id"]
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    result_1 = service.verify_task(task_id)
    result_2 = service.verify_task(task_id)

    assert result_1["verdict"] == result_2["verdict"]
    assert result_1["verified"] == result_2["verified"]
    assert result_1["failure_reasons"] == result_2["failure_reasons"]
    assert result_1["provider_calls"] == result_2["provider_calls"]


def test_verify_task_no_commit_no_push_no_cleanup(tmp_path):
    """W0: verify_task must not commit, push, approve, integrate, or cleanup."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="verify-no-ops")
    task_id = request["task_id"]
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    # Record git state before
    controller = Path(contract.controller_repo_root)
    commits_before = _git(controller, "rev-parse", "HEAD")

    result = service.verify_task(task_id)

    # Git state must be unchanged
    commits_after = _git(controller, "rev-parse", "HEAD")
    assert commits_before == commits_after, "verify must not commit"
    assert result["verified"] is True


def test_verify_task_fails_on_missing_target(tmp_path):
    """W0: verify_task fails when target worktree is missing."""
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = _real_request(tmp_path, task_id="verify-no-target")
    task_id = request["task_id"]
    contract, lease, attempt_id = _setup_lc2_task(tmp_path, service, task_id)

    # Remove target worktree
    import shutil
    target_path = Path(lease.target_worktree)
    if target_path.exists():
        shutil.rmtree(target_path)

    result = service.verify_task(task_id)
    assert result["verified"] is False
    assert "target_missing" in result["failure_reasons"]


# ---------- W1: End-to-end fast lane canary ----------


def test_w1_service_path_canary(tmp_path):
    """W1: Formal service-path canary for the owner-controlled happy path.

    Flow through formal service path:
    1. submit_task creates durable task state
    2. _run_default_resumable creates the real Target lease
    3. Mock worker makes bounded mutation and returns EXECUTION_COMPLETED
    4. CandidateVerifier -> commit -> durable ref -> cleanup
    5. Final state: PENDING_HUMAN_APPROVAL, cleanup REMOVED

    Prohibited: manual commit, manual protect candidate ref, manual _write_state
    to force candidate status, BLOCKED_BY_UNSAVED_CHANGES as success.
    """
    # --- Phase 1: Real controller and target repos ---
    controller = tmp_path / "controller"
    controller.mkdir()
    _init_repo(controller)
    _git(controller, "config", "user.name", "W1 Service Test")
    _git(controller, "config", "user.email", "w1-svc@test.com")
    (controller / "README").write_text("base\n")
    _git(controller, "add", "README")
    _git(controller, "commit", "-m", "base commit")
    base_sha = _git(controller, "rev-parse", "HEAD")

    target_root = tmp_path / "targets"
    target_root.mkdir()

    # Verifier command that always passes
    verifier_script = tmp_path / "verify.sh"
    verifier_script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    verifier_script.chmod(0o755)

    request = {
        "task_id": "w1-svc-canary",
        "what": "w1 service path canary",
        "why": "prove formal happy path",
        "controller_revision": base_sha,
        "target_base_revision": base_sha,
        "controller_repo_root": str(controller),
        "target_repo_root": str(target_root / "w1-svc-canary"),
        "target_worktree_root": str(target_root),
        "allowed_files": ["src/"],
        "forbidden_files": [],
        "verifier_commands": [f"/bin/sh {verifier_script}"],
        "protected_contracts": [],
        "worker": "codex",
    }

    # --- Phase 2: Configure a deterministic worker and run submit_task inline ---
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    manager = WorktreeManager(root_dir=str(target_root))

    from unittest.mock import MagicMock

    observed_target: dict[str, Path] = {}

    def mock_invoke(provider, contract_arg, lease_arg, *, prompt, **kwargs):
        target_path = Path(lease_arg.target_worktree)
        observed_target["path"] = target_path
        src = target_path / "src"
        src.mkdir(exist_ok=True)
        (src / "canary.txt").write_text("worker bounded mutation\n", encoding="utf-8")
        return WorkerExecutionReceipt(
            provider=provider,
            task_id=contract_arg.task_id,
            target_worktree=str(target_path),
            worker_status="completed",
            outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
            exit_code=0,
            executable_identity="mock-codex",
            argv=("mock-codex",),
            stdout_sha256="a" * 64,
            stderr_sha256="b" * 64,
            wall_time_ms=100,
            process_group_id=os.getpid(),
            process_group_killed=False,
            timed_out=False,
            provider_calls=1,
            evidence_complete=True,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
        )

    service.worker_registry = MagicMock()
    service.worker_registry.invoke = mock_invoke
    service.worker_registry.preflight.return_value = WorkerPreflight(
        provider="codex",
        executable="mock-codex",
        executable_available=True,
        authorized=True,
        implementation_status="ready",
        ready=True,
        reason=None,
    )

    def launch_inline(task_id, attempt_id):
        service._run_owned_task(task_id, attempt_id)
        return service._read_state(task_id)

    service._launch_worker = launch_inline
    submitted = service.submit_task(request)

    # --- Phase 3: Verify final state written by the full submit/owner path ---
    state = service._read_state("w1-svc-canary")
    assert submitted["status"] == "PENDING_HUMAN_APPROVAL"
    lease = TargetWorktreeLease(**state["lease"])
    target = Path(lease.target_worktree)
    assert observed_target["path"] == target
    assert state is not None, "state must exist"
    assert state.get("terminal_status") == "PENDING_HUMAN_APPROVAL", \
        f"must reach PENDING_HUMAN_APPROVAL, got {state.get('terminal_status')}"
    assert state.get("candidate_status") == "PENDING_HUMAN_APPROVAL"
    assert state.get("cleanup_decision") == "REMOVED", \
        f"cleanup must be REMOVED, got {state.get('cleanup_decision')}"

    # --- Phase 7: Verify candidate commit and ref ---
    candidate_ref = state.get("candidate_ref")
    packet = state.get("promotion_packet") or {}
    candidate_commit = packet.get("candidate_commit_sha")
    assert candidate_ref, "candidate_ref must be set"
    assert candidate_commit, "candidate_commit_sha must be set"

    resolved_ref = _git(controller, "rev-parse", candidate_ref)
    assert resolved_ref == candidate_commit, "candidate ref must resolve to candidate commit"

    # --- Phase 8: Verify Target removed ---
    assert not target.exists(), "Target worktree must be removed after cleanup"

    target_registered = False
    try:
        registered = manager._registered_worktrees(controller)
        target_registered = any(
            "worktree" in e and Path(e["worktree"]).resolve() == target.resolve()
            for e in registered
        )
    except Exception:
        pass
    assert not target_registered, "Target must not be registered after cleanup"

    # --- Phase 9: Verify durable verified receipt present ---
    verified_receipt = state.get("verified_receipt") or {}
    assert verified_receipt.get("verified") is True, "receipt must be verified"
    assert state.get("candidate_commit_sha") == candidate_commit
    assert state.get("candidate_ref") == candidate_ref
    assert state.get("status") == "PENDING_HUMAN_APPROVAL"
    assert state.get("promotion_status") == "PENDING_HUMAN_APPROVAL"

    # --- Phase 10: W0 must verify the protected Candidate after Target cleanup ---
    read_only_verification = service.verify_task("w1-svc-canary")
    assert read_only_verification["verified"] is True, read_only_verification
    assert read_only_verification["verdict"] == "VERIFIED"
    assert read_only_verification["verification_mode"] == "durable_candidate_receipt"
    assert read_only_verification["provider_calls"] == 0
    assert read_only_verification["verifier_commands_executed"] == []

    # A recreated path at the old Target location must not switch verification back
    # to mutable Target mode after durable cleanup.
    target.mkdir(parents=True)
    (target / "untrusted.txt").write_text("not authoritative\n", encoding="utf-8")
    recreated_target_result = service.verify_task("w1-svc-canary")
    assert recreated_target_result["verified"] is True, recreated_target_result
    assert recreated_target_result["verification_mode"] == "durable_candidate_receipt"
    assert recreated_target_result["provider_calls"] == 0
    shutil.rmtree(target)

    # --- Phase 11: Governance invariants ---
    assert state.get("merge_performed") is not True, "no auto merge"
    assert state.get("push_performed") is not True, "no auto push"
    assert state.get("approved_binding") is None, "no auto approval"
    assert state.get("public_claim_allowed") is not True, "no auto public claim"
    assert state.get("production_ready") is not True, "no auto production ready"

    # --- Phase 12: Verify verified receipt details ---
    assert verified_receipt.get("scope_gate_passed") is True, "scope gate must pass"
    assert verified_receipt.get("deletion_gate_passed") is True, "deletion gate must pass"
    assert verified_receipt.get("controller_gate_passed") is True, "controller gate must pass"
    assert verified_receipt.get("verifier_gate_passed") is True, "verifier gate must pass"
    assert verified_receipt.get("public_claim_allowed") is False, "public claim must not be allowed"
    assert verified_receipt.get("production_ready") is False, "must not be production ready"

    # --- Phase 13: Durable verification must fail closed on ref or receipt tamper ---
    original_state = service._read_state("w1-svc-canary")

    target.mkdir(parents=True)
    (target / "recreated.txt").write_text("untrusted replacement\n", encoding="utf-8")
    missing_binding = copy.deepcopy(original_state)
    missing_binding["candidate_commit_sha"] = None
    missing_binding["candidate_tree_sha"] = None
    missing_binding["candidate_ref"] = None
    missing_binding["candidate_state_hash"] = None
    missing_binding["verified_receipt_hash"] = None
    missing_binding["promotion_packet"] = {}
    service._write_state("w1-svc-canary", missing_binding)
    missing_binding_result = service.verify_task("w1-svc-canary")
    assert missing_binding_result["verified"] is False
    assert "durable_candidate_binding_missing" in missing_binding_result["failure_reasons"]
    shutil.rmtree(target)

    tampered_ref = copy.deepcopy(original_state)
    tampered_ref["candidate_ref"] = "refs/heads/main"
    service._write_state("w1-svc-canary", tampered_ref)
    tampered_ref_result = service.verify_task("w1-svc-canary")
    assert tampered_ref_result["verified"] is False
    assert "candidate_ref_namespace_invalid" in tampered_ref_result["failure_reasons"]

    tampered_hash = copy.deepcopy(original_state)
    tampered_hash["promotion_packet"]["verified_receipt_hash"] = "0" * 64
    tampered_hash["verified_receipt_hash"] = "0" * 64
    service._write_state("w1-svc-canary", tampered_hash)
    tampered_hash_result = service.verify_task("w1-svc-canary")
    assert tampered_hash_result["verified"] is False
    assert "verified_receipt_hash_mismatch" in tampered_hash_result["failure_reasons"]
