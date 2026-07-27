import json
from pathlib import Path
from types import SimpleNamespace
import time

import pytest

from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.worktree_manager import TargetWorktreeLease
from nexus.executors.worker_contract import WorkerExecutionReceipt, WorkerPreflight, WorkerOutcome
from nexus.executors.worker_registry import WorkerRegistry


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
            return SimpleNamespace(candidate_state_hash="c" * 64)

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
