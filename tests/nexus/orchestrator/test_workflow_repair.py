"""Tests for Workflow repair, recovery API, Git isolation, preflight binding, and target retention."""

from dataclasses import asdict
import os
import subprocess
from pathlib import Path
import pytest

from nexus.orchestrator.candidate_commit import CandidateCommitter
from nexus.orchestrator.candidate_verifier import VerifiedCandidateReceipt
from nexus.orchestrator.self_hosted_task_service import (
    SelfHostedTaskService,
    check_fast_lane_eligible,
    resolve_canonical_target_roots,
    validate_lifecycle_revision,
    validate_task_card_binding,
)
from nexus.orchestrator.task_contract import MutationMode, SelfHostedTaskContract
from nexus.orchestrator.worktree_manager import WorktreeManager


def _git(cwd: Path, *args: str) -> str:
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    empty_hooks = cwd.parent / "empty_git_hooks"
    empty_hooks.mkdir(exist_ok=True)
    cmd = ["git", "-c", f"core.hooksPath={empty_hooks}", *args]
    result = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True, env=env)
    return result.stdout.strip()


def _scenario(tmp_path: Path):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    controller_root.mkdir()
    target_root.mkdir()
    _git(controller_root, "init", "-b", "main")
    _git(controller_root, "config", "user.email", "test@example.test")
    _git(controller_root, "config", "user.name", "Test")
    (controller_root / "bounded.txt").write_text("base\n", encoding="utf-8")
    _git(controller_root, "add", "bounded.txt")
    _git(controller_root, "commit", "-m", "base")
    target_sha = _git(controller_root, "rev-parse", "HEAD")
    _git(controller_root, "commit", "--allow-empty", "-m", "controller")
    controller_sha = _git(controller_root, "rev-parse", "HEAD")

    contract = SelfHostedTaskContract(
        task_id="workflow-repair-test",
        objective="Verify workflow repair behaviors",
        controller_revision=controller_sha,
        target_base_revision=target_sha,
        controller_repo_root=str(controller_root),
        target_repo_root=str(target_root / "workflow-repair-test"),
        target_worktree_root=str(target_root),
        allowed_files=["bounded.txt"],
        verifier_commands=["python3 -c 'print(\"pass\")'"],
        protected_contracts=["candidate-receipt-v1"],
        preferred_provider="codex",
        maximum_provider_calls=1,
        mutation_mode=MutationMode.WORKING_TREE_ONLY,
        human_approval_required=True,
    )
    manager = WorktreeManager(str(target_root))
    lease = manager.create_lease(contract)
    (Path(lease.target_worktree) / "bounded.txt").write_text("candidate content\n", encoding="utf-8")
    candidate = manager.capture_candidate(contract, lease)
    return contract, lease, candidate, manager, controller_root, target_root


def test_recover_verified_uncommitted_candidate_without_model_recall(tmp_path, monkeypatch):
    contract, lease, candidate, manager, controller_root, target_root = _scenario(tmp_path)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(state_dir))
    svc = SelfHostedTaskService(state_dir=state_dir, ephemeral=True)

    verified_receipt = VerifiedCandidateReceipt(
        schema="nexus.verified_candidate_receipt.v1",
        task_id=contract.task_id,
        contract_hash=contract.contract_hash,
        lease_id=lease.lease_id,
        candidate_state_hash=candidate.candidate_state_hash,
        verified=True,
        verifier_gate_passed=True,
        controller_gate_passed=True,
        scope_gate_passed=True,
        deletion_gate_passed=True,
        protected_contract_gate_passed=True,
        repository_contract_gate_passed=True,
        repository_contract_mode="shadow",
        repository_contract_policy_revision_hash="hash",
        repository_contract_findings=[],
        candidate_commit_allowed=True,
        candidate_commit_created=False,
        public_claim_allowed=False,
        production_ready=False,
        merge_performed=False,
        failure_reasons=[],
        verifier_evidence=[],
    )

    state = {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": contract.task_id,
        "status": "RETAINED_FOR_REVIEW",
        "attempt_id": "attempt-1",
        "attempt_resolution": {
            "verdict": "PROVEN",
            "verified": True,
            "candidate_non_empty": True,
            "candidate_state_hash": candidate.candidate_state_hash,
        },
        "execution": {
            "outcome": "EXECUTION_COMPLETED",
            "provider_calls": 1,
        },
        "verified_receipt": verified_receipt.model_dump(mode="json") if hasattr(verified_receipt, "model_dump") else verified_receipt.__dict__,
        "contract": contract.model_dump(mode="json"),
        "lease": asdict(lease),
        "candidate_state_hash": candidate.candidate_state_hash,
        "promotion_status": "NOT_CREATED",
    }
    svc._write_state(contract.task_id, state)

    res = svc.recover_verified_uncommitted_candidate(contract.task_id)

    assert res.get("status") == "PENDING_HUMAN_APPROVAL"
    assert res.get("candidate_commit_sha") is not None
    assert len(res.get("candidate_commit_sha")) == 40
    assert res.get("candidate_tree_sha") is not None
    assert res.get("verified_receipt_hash") is not None

    # Test rejection when status is WORKER_COMPLETED or VERIFIED
    state_wc = dict(state, status="WORKER_COMPLETED")
    svc._write_state(contract.task_id, state_wc)
    with pytest.raises(RuntimeError, match="not eligible for uncommitted recovery"):
        svc.recover_verified_uncommitted_candidate(contract.task_id)

    state_ver = dict(state, status="VERIFIED")
    svc._write_state(contract.task_id, state_ver)
    with pytest.raises(RuntimeError, match="not eligible for uncommitted recovery"):
        svc.recover_verified_uncommitted_candidate(contract.task_id)


def test_candidate_commit_ignores_user_global_hooks(tmp_path, monkeypatch):
    contract, lease, candidate, manager, controller_root, target_root = _scenario(tmp_path)
    fake_global_hooks = tmp_path / "global_hooks"
    fake_global_hooks.mkdir()
    hook_file = fake_global_hooks / "pre-commit"
    hook_file.write_text("#!/bin/sh\necho 'USER HOOK FAIL' >&2\nexit 42\n", encoding="utf-8")
    hook_file.chmod(0o755)

    gitconfig = tmp_path / "fake_gitconfig"
    gitconfig.write_text(f"[core]\n\thooksPath = {fake_global_hooks}\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))

    verified_receipt = VerifiedCandidateReceipt(
        schema="nexus.verified_candidate_receipt.v1",
        task_id=contract.task_id,
        contract_hash=contract.contract_hash,
        lease_id=lease.lease_id,
        candidate_state_hash=candidate.candidate_state_hash,
        verified=True,
        verifier_gate_passed=True,
        controller_gate_passed=True,
        scope_gate_passed=True,
        deletion_gate_passed=True,
        protected_contract_gate_passed=True,
        repository_contract_gate_passed=True,
        repository_contract_mode="shadow",
        repository_contract_policy_revision_hash="hash",
        repository_contract_findings=[],
        candidate_commit_allowed=True,
        candidate_commit_created=False,
        public_claim_allowed=False,
        production_ready=False,
        merge_performed=False,
        failure_reasons=[],
        verifier_evidence=[],
    )

    packet = CandidateCommitter(manager).create_candidate_commit(contract, lease, verified_receipt)
    assert packet.candidate_commit_created is True
    assert packet.promotion_status == "PENDING_HUMAN_APPROVAL"


def test_verified_target_preserved_when_commit_fails(tmp_path, monkeypatch):
    contract, lease, candidate, manager, controller_root, target_root = _scenario(tmp_path)
    target_path = Path(lease.target_worktree)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    svc = SelfHostedTaskService(state_dir=state_dir, ephemeral=True)

    verified_receipt = VerifiedCandidateReceipt(
        schema="nexus.verified_candidate_receipt.v1",
        task_id=contract.task_id,
        contract_hash=contract.contract_hash,
        lease_id=lease.lease_id,
        candidate_state_hash=candidate.candidate_state_hash,
        verified=True,
        verifier_gate_passed=True,
        controller_gate_passed=True,
        scope_gate_passed=True,
        deletion_gate_passed=True,
        protected_contract_gate_passed=True,
        repository_contract_gate_passed=True,
        repository_contract_mode="shadow",
        repository_contract_policy_revision_hash="hash",
        repository_contract_findings=[],
        candidate_commit_allowed=True,
        candidate_commit_created=False,
        public_claim_allowed=False,
        production_ready=False,
        merge_performed=False,
        failure_reasons=[],
        verifier_evidence=[],
    )

    from nexus.executors.worker_contract import WorkerExecutionReceipt
    exec_rcpt = WorkerExecutionReceipt(
        provider="codex",
        task_id=contract.task_id,
        target_worktree=str(lease.target_worktree),
        worker_status="COMPLETED",
        outcome="EXECUTION_COMPLETED",
        exit_code=0,
        executable_identity="codex-mock",
        argv=(),
        stdout_sha256="abc",
        stderr_sha256="abc",
        wall_time_ms=100,
        process_group_id=None,
        process_group_killed=False,
        timed_out=False,
        provider_calls=1,
        evidence_complete=True,
        commit_created=False,
        merge_performed=False,
        push_performed=False,
        failure_reason=None,
    )
    exec_dict = asdict(exec_rcpt) if hasattr(exec_rcpt, "__dict__") else exec_rcpt
    state = {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": contract.task_id,
        "status": "WORKER_COMPLETED",
        "attempt_id": "attempt-1",
        "contract": contract.model_dump(mode="json"),
        "lease": asdict(lease),
        "execution": exec_dict,
        "executions": [exec_dict],
        "verified_receipt": verified_receipt.model_dump(mode="json") if hasattr(verified_receipt, "model_dump") else verified_receipt.__dict__,
        "attempt_resolution": {"verdict": "PROVEN"},
    }
    svc._write_state(contract.task_id, state)

    def failing_commit(*args, **kwargs):
        raise RuntimeError("git commit failed: index lock error")
    monkeypatch.setattr(CandidateCommitter, "create_candidate_commit", failing_commit)

    svc._run_owned_task(contract.task_id, "attempt-1")

    assert target_path.exists()
    saved = svc.get_task(contract.task_id)
    assert saved.get("status") == "RETAINED_FOR_REVIEW"


def test_lifecycle_revision_mismatch_fails_before_target_creation(tmp_path):
    contract, lease, candidate, manager, controller_root, target_root = _scenario(tmp_path)

    request = {
        "required_lifecycle_revision": "nonexistent_revision_1234567890"
    }

    with pytest.raises(RuntimeError, match="LIFECYCLE_REVISION_MISMATCH"):
        validate_lifecycle_revision(contract, request)


def test_default_target_root_is_mcp_visible_workspace(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_TARGET_ROOT_OVERRIDE", raising=False)
    worktree_root, repo_root = resolve_canonical_target_roots(
        task_id="test-target-path",
        campaign_id="test-campaign",
    )
    assert "/private/tmp" not in str(worktree_root)
    assert "/tmp" not in str(worktree_root)
    assert "runtime-targets" in str(worktree_root)
    assert worktree_root.is_absolute()


def test_task_card_id_must_match_lifecycle_task_id(tmp_path):
    contract, lease, candidate, manager, controller_root, target_root = _scenario(tmp_path)
    card_file = tmp_path / "card.md"
    card_file.write_text("# Task\n\n**task_id:** `different-id`\nAUTO_CHAIN: false\n", encoding="utf-8")

    request = {
        "task_card_path": str(card_file),
        "task_card_required": True,
    }

    with pytest.raises(RuntimeError, match="TASK_CARD_BINDING_MISMATCH"):
        validate_task_card_binding(contract, request)


def test_fast_lane_uses_single_provider_call(tmp_path, monkeypatch):
    controller_root = tmp_path / "controller"
    target_root = tmp_path / "targets"
    controller_root.mkdir()
    target_root.mkdir()
    _git(controller_root, "init", "-b", "main")
    _git(controller_root, "config", "user.email", "test@example.test")
    _git(controller_root, "config", "user.name", "Test")
    (controller_root / "bounded.txt").write_text("base\n", encoding="utf-8")
    _git(controller_root, "add", "bounded.txt")
    _git(controller_root, "commit", "-m", "base")
    target_sha = _git(controller_root, "rev-parse", "HEAD")
    controller_sha = target_sha

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    svc = SelfHostedTaskService(state_dir=state_dir, ephemeral=True)

    request = {
        "what": "Fast Lane execution test",
        "why": "Verify single provider call",
        "allowed_files": ["bounded.txt"],
        "verifier_commands": ["python3 -c 'print(\"pass\")'"],
        "controller_repo_root": str(controller_root),
        "target_repo_root": str(target_root / "fast-lane-test"),
        "target_worktree_root": str(target_root),
        "controller_revision": controller_sha,
        "target_base_revision": target_sha,
    }
    contract = svc.build_contract(request)
    assert check_fast_lane_eligible(contract) is True

    manager = WorktreeManager(str(target_root))
    lease = manager.create_lease(contract)

    provider_call_count = 0
    from nexus.executors.worker_contract import WorkerExecutionReceipt
    from nexus.executors.worker_registry import WorkerRegistry

    def fake_invoke(self_obj, provider, task_contract, target_lease, **kwargs):
        nonlocal provider_call_count
        provider_call_count += 1
        (Path(target_lease.target_worktree) / "bounded.txt").write_text("modified\n", encoding="utf-8")
        return WorkerExecutionReceipt(
            provider=provider,
            task_id=task_contract.task_id,
            target_worktree=str(target_lease.target_worktree),
            worker_status="COMPLETED",
            outcome="EXECUTION_COMPLETED",
            exit_code=0,
            executable_identity="codex-mock",
            argv=(),
            stdout_sha256="abc",
            stderr_sha256="abc",
            wall_time_ms=100,
            process_group_id=None,
            process_group_killed=False,
            timed_out=False,
            provider_calls=1,
            evidence_complete=True,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
            failure_reason=None,
        )

    monkeypatch.setattr(WorkerRegistry, "invoke", fake_invoke)

    state = {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": contract.task_id,
        "status": "WORKER_RUNNING",
        "attempt_id": "attempt-1",
        "contract": contract.model_dump(mode="json"),
        "lease": asdict(lease),
        "active_provider": "codex",
        "executions": [],
    }
    svc._write_state(contract.task_id, state)

    def mock_update(status, values):
        svc._checkpoint(contract.task_id, status, values, attempt_id="attempt-1")

    svc._run_default_resumable(contract, {}, mock_update, task_id=contract.task_id, attempt_id="attempt-1")
    assert provider_call_count == 1


def test_mcp_disconnect_does_not_delete_verified_target(tmp_path, monkeypatch):
    contract, lease, candidate, manager, controller_root, target_root = _scenario(tmp_path)
    target_path = Path(lease.target_worktree)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    svc = SelfHostedTaskService(state_dir=state_dir, ephemeral=True)

    verified_receipt = VerifiedCandidateReceipt(
        schema="nexus.verified_candidate_receipt.v1",
        task_id=contract.task_id,
        contract_hash=contract.contract_hash,
        lease_id=lease.lease_id,
        candidate_state_hash=candidate.candidate_state_hash,
        verified=True,
        verifier_gate_passed=True,
        controller_gate_passed=True,
        scope_gate_passed=True,
        deletion_gate_passed=True,
        protected_contract_gate_passed=True,
        repository_contract_gate_passed=True,
        repository_contract_mode="shadow",
        repository_contract_policy_revision_hash="hash",
        repository_contract_findings=[],
        candidate_commit_allowed=True,
        candidate_commit_created=False,
        public_claim_allowed=False,
        production_ready=False,
        merge_performed=False,
        failure_reasons=[],
        verifier_evidence=[],
    )

    state = {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": contract.task_id,
        "status": "SUBMITTED",
        "attempt_id": "attempt-1",
        "request": {
            "what": contract.objective,
            "why": contract.objective,
            "allowed_files": contract.allowed_files,
            "controller_repo_root": contract.controller_repo_root,
            "target_repo_root": contract.target_repo_root,
            "target_worktree_root": contract.target_worktree_root,
            "controller_revision": contract.controller_revision,
            "target_base_revision": contract.target_base_revision,
        },
        "verified_receipt": verified_receipt.model_dump(mode="json") if hasattr(verified_receipt, "model_dump") else verified_receipt.__dict__,
        "attempt_resolution": {"verdict": "PROVEN"},
        "lease": asdict(lease),
        "executions": [],
    }
    svc._write_state(contract.task_id, state)

    def failing_runner(contract, request, update):
        update("VERIFIED", {
            "verified_receipt": verified_receipt,
            "attempt_resolution": {"verdict": "PROVEN"},
        })
        raise ConnectionResetError("MCP caller disconnected abruptly during finalizer")

    svc._custom_runner = failing_runner
    svc._run_owned_task(contract.task_id, "attempt-1")

    assert target_path.exists()
    final_state = svc.get_task(contract.task_id)
    assert final_state.get("status") == "RETAINED_FOR_REVIEW"


def test_real_git_commit_failure_preserves_target_and_evidence(tmp_path, monkeypatch):
    contract, lease, candidate, manager, controller_root, target_root = _scenario(tmp_path)
    target_path = Path(lease.target_worktree)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    svc = SelfHostedTaskService(state_dir=state_dir, ephemeral=True)

    fake_canonical_hooks = tmp_path / "failing_hooks"
    fake_canonical_hooks.mkdir()
    hook_file = fake_canonical_hooks / "pre-commit"
    hook_file.write_text("#!/bin/sh\necho 'FAIL COMMIT' >&2\nexit 42\n", encoding="utf-8")
    hook_file.chmod(0o700)
    monkeypatch.setenv("NEXUS_CANONICAL_GIT_HOOKS_DIR", str(fake_canonical_hooks))

    verified_receipt = VerifiedCandidateReceipt(
        schema="nexus.verified_candidate_receipt.v1",
        task_id=contract.task_id,
        contract_hash=contract.contract_hash,
        lease_id=lease.lease_id,
        candidate_state_hash=candidate.candidate_state_hash,
        verified=True,
        verifier_gate_passed=True,
        controller_gate_passed=True,
        scope_gate_passed=True,
        deletion_gate_passed=True,
        protected_contract_gate_passed=True,
        repository_contract_gate_passed=True,
        repository_contract_mode="shadow",
        repository_contract_policy_revision_hash="hash",
        repository_contract_findings=[],
        candidate_commit_allowed=True,
        candidate_commit_created=False,
        public_claim_allowed=False,
        production_ready=False,
        merge_performed=False,
        failure_reasons=[],
        verifier_evidence=[],
    )

    from nexus.executors.worker_contract import WorkerExecutionReceipt
    exec_rcpt = WorkerExecutionReceipt(
        provider="codex",
        task_id=contract.task_id,
        target_worktree=str(lease.target_worktree),
        worker_status="COMPLETED",
        outcome="EXECUTION_COMPLETED",
        exit_code=0,
        executable_identity="codex-mock",
        argv=(),
        stdout_sha256="abc",
        stderr_sha256="abc",
        wall_time_ms=100,
        process_group_id=None,
        process_group_killed=False,
        timed_out=False,
        provider_calls=1,
        evidence_complete=True,
        commit_created=False,
        merge_performed=False,
        push_performed=False,
        failure_reason=None,
    )
    exec_dict = asdict(exec_rcpt) if hasattr(exec_rcpt, "__dict__") else exec_rcpt
    state = {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": contract.task_id,
        "status": "WORKER_COMPLETED",
        "attempt_id": "attempt-1",
        "contract": contract.model_dump(mode="json"),
        "lease": asdict(lease),
        "execution": exec_dict,
        "executions": [exec_dict],
        "verified_receipt": verified_receipt.model_dump(mode="json") if hasattr(verified_receipt, "model_dump") else verified_receipt.__dict__,
        "attempt_resolution": {"verdict": "PROVEN"},
    }
    svc._write_state(contract.task_id, state)

    svc._run_owned_task(contract.task_id, "attempt-1")

    assert target_path.exists()
    saved = svc.get_task(contract.task_id)
    assert saved.get("status") == "RETAINED_FOR_REVIEW"
    assert saved.get("candidate_ref") is None
    assert saved.get("promotion_status") == "NOT_CREATED"


def test_candidate_ref_failure_fails_closed(tmp_path, monkeypatch):
    contract, lease, candidate, manager, controller_root, target_root = _scenario(tmp_path)
    target_path = Path(lease.target_worktree)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    svc = SelfHostedTaskService(state_dir=state_dir, ephemeral=True)

    def failing_protect(*args, **kwargs):
        raise RuntimeError("candidate ref creation failed: update-ref error")
    monkeypatch.setattr(WorktreeManager, "protect_candidate", failing_protect)

    from nexus.executors.worker_contract import WorkerExecutionReceipt
    exec_rcpt = WorkerExecutionReceipt(
        provider="codex",
        task_id=contract.task_id,
        target_worktree=str(lease.target_worktree),
        worker_status="COMPLETED",
        outcome="EXECUTION_COMPLETED",
        exit_code=0,
        executable_identity="codex-mock",
        argv=(),
        stdout_sha256="abc",
        stderr_sha256="abc",
        wall_time_ms=100,
        process_group_id=None,
        process_group_killed=False,
        timed_out=False,
        provider_calls=1,
        evidence_complete=True,
        commit_created=False,
        merge_performed=False,
        push_performed=False,
        failure_reason=None,
    )
    exec_dict = asdict(exec_rcpt) if hasattr(exec_rcpt, "__dict__") else exec_rcpt
    state = {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": contract.task_id,
        "status": "WORKER_COMPLETED",
        "attempt_id": "attempt-1",
        "contract": contract.model_dump(mode="json"),
        "lease": asdict(lease),
        "execution": exec_dict,
        "executions": [exec_dict],
        "verified_receipt": {
            "verified": True,
            "verifier_gate_passed": True,
            "controller_gate_passed": True,
            "scope_gate_passed": True,
            "deletion_gate_passed": True,
            "protected_contract_gate_passed": True,
        },
        "attempt_resolution": {"verdict": "PROVEN"},
    }
    svc._write_state(contract.task_id, state)

    with pytest.raises(RuntimeError, match="candidate ref protection failed"):
        svc._run_default_resumable(contract, {}, lambda status, val: svc._checkpoint(contract.task_id, status, val, attempt_id="attempt-1"), task_id=contract.task_id, attempt_id="attempt-1")

    assert target_path.exists()
    saved = svc.get_task(contract.task_id)
    assert saved.get("status") == "RETAINED_FOR_REVIEW"
    assert saved.get("promotion_status") == "NOT_CREATED"


def test_single_integration_authority_requires_receipt(tmp_path):
    contract, lease, candidate, manager, controller_root, target_root = _scenario(tmp_path)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    svc = SelfHostedTaskService(state_dir=state_dir, ephemeral=True)

    with pytest.raises(TypeError, match="receipt must be an IntegrationReceipt instance"):
        svc._record_integration("invalid_type")  # type: ignore


def test_production_lifecycle_identity_required(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    svc = SelfHostedTaskService(state_dir=state_dir, ephemeral=True)

    request = {
        "task_id": "prod-identity-test-id",
        "what": "Production identity test",
        "why": "Verify identity requirement",
        "allowed_files": ["bounded.txt"],
        "verifier_commands": ["python3 -c 'print(\"pass\")'"],
        "controller_repo_root": str(tmp_path),
        "target_repo_root": str(tmp_path / "target"),
        "target_worktree_root": str(tmp_path),
        "controller_revision": "a" * 40,
        "target_base_revision": "a" * 40,
        "allow_unbound_test_identity": True,
    }
    contract = svc.build_contract(request)

    with pytest.raises(RuntimeError, match="TASK_CARD_BINDING_MISMATCH: allow_unbound_test_identity is only permitted when ephemeral=True"):
        validate_task_card_binding(contract, request, is_ephemeral=False)


def test_hook_permission_fail_closed(tmp_path, monkeypatch):
    from nexus.orchestrator.worktree_manager import get_canonical_git_hooks_dir
    fake_dir = tmp_path / "bad_hooks"
    fake_dir.mkdir()
    fake_dir.chmod(0o777)
    monkeypatch.setenv("NEXUS_CANONICAL_GIT_HOOKS_DIR", str(fake_dir))

    def failing_chmod(*args, **kwargs):
        raise OSError("Permission denied")
    monkeypatch.setattr(Path, "chmod", failing_chmod)

    with pytest.raises(RuntimeError, match="failed to set permissions 0700"):
        get_canonical_git_hooks_dir()


def test_timeout_dirty_worker_auto_invokes_salvage_and_cleanup(tmp_path, monkeypatch):
    contract, lease, candidate, manager, controller_root, target_root = _scenario(tmp_path)
    target_path = Path(lease.target_worktree)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    svc = SelfHostedTaskService(state_dir=state_dir, ephemeral=True)

    (target_path / "bounded.txt").write_text("dirty from timeout\n")

    state = {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": contract.task_id,
        "status": "WORKER_RUNNING",
        "attempt_id": "attempt-1",
        "request": {
            "task_id": contract.task_id,
            "what": contract.objective,
            "why": "Test auto closeout",
            "allowed_files": contract.allowed_files,
            "controller_repo_root": contract.controller_repo_root,
            "target_repo_root": contract.target_repo_root,
            "target_worktree_root": contract.target_worktree_root,
            "controller_revision": contract.controller_revision,
            "target_base_revision": contract.target_base_revision,
        },
        "contract": contract.model_dump(mode="json"),
        "lease": asdict(lease),
        "execution": None,
        "executions": [],
        "verified_receipt": None,
        "attempt_resolution": None,
        "promotion_status": "NOT_CREATED",
    }
    svc._write_state(contract.task_id, state)

    def timeout_runner(contract, request, update):
        raise TimeoutError("worker timed out after 900000 ms")

    svc._custom_runner = timeout_runner
    svc._run_owned_task(contract.task_id, "attempt-1")

    final_state = svc.get_task(contract.task_id)
    assert final_state["status"] == "RETAINED_FOR_REVIEW"
    assert final_state["cleanup_decision"] in ("REMOVED", "ALREADY_REMOVED")
    assert final_state["cleanup_performed"] is True
    assert final_state.get("salvage_commit_sha") is not None
    assert final_state.get("salvage_ref") is not None
    assert not target_path.exists()


def test_failed_dirty_worker_auto_invokes_salvage_and_cleanup(tmp_path, monkeypatch):
    contract, lease, candidate, manager, controller_root, target_root = _scenario(tmp_path)
    target_path = Path(lease.target_worktree)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    svc = SelfHostedTaskService(state_dir=state_dir, ephemeral=True)

    (target_path / "bounded.txt").write_text("dirty from failure\n")

    state = {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": contract.task_id,
        "status": "WORKER_RUNNING",
        "attempt_id": "attempt-1",
        "request": {
            "task_id": contract.task_id,
            "what": contract.objective,
            "why": "Test auto closeout",
            "allowed_files": contract.allowed_files,
            "controller_repo_root": contract.controller_repo_root,
            "target_repo_root": contract.target_repo_root,
            "target_worktree_root": contract.target_worktree_root,
            "controller_revision": contract.controller_revision,
            "target_base_revision": contract.target_base_revision,
        },
        "contract": contract.model_dump(mode="json"),
        "lease": asdict(lease),
        "execution": None,
        "executions": [],
        "verified_receipt": None,
        "attempt_resolution": None,
        "promotion_status": "NOT_CREATED",
    }
    svc._write_state(contract.task_id, state)

    def fail_runner(contract, request, update):
        raise RuntimeError("worker failed with exit code 42")

    svc._custom_runner = fail_runner
    svc._run_owned_task(contract.task_id, "attempt-1")

    final_state = svc.get_task(contract.task_id)
    assert final_state["status"] == "RETAINED_FOR_REVIEW"
    assert final_state["cleanup_decision"] in ("REMOVED", "ALREADY_REMOVED")
    assert final_state["cleanup_performed"] is True
    assert final_state.get("salvage_commit_sha") is not None
    assert not target_path.exists()


def test_closeout_salvage_failure_preserves_retained_target_and_error(tmp_path, monkeypatch):
    contract, lease, candidate, manager, controller_root, target_root = _scenario(tmp_path)
    target_path = Path(lease.target_worktree)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    svc = SelfHostedTaskService(state_dir=state_dir, ephemeral=True)

    (target_path / "bounded.txt").write_text("dirty content\n")

    state = {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": contract.task_id,
        "status": "WORKER_RUNNING",
        "attempt_id": "attempt-1",
        "request": {
            "task_id": contract.task_id,
            "what": contract.objective,
            "why": "Test salvage failure",
            "allowed_files": contract.allowed_files,
            "controller_repo_root": contract.controller_repo_root,
            "target_repo_root": contract.target_repo_root,
            "target_worktree_root": contract.target_worktree_root,
            "controller_revision": contract.controller_revision,
            "target_base_revision": contract.target_base_revision,
        },
        "contract": contract.model_dump(mode="json"),
        "lease": asdict(lease),
        "execution": None,
        "executions": [],
        "verified_receipt": None,
        "attempt_resolution": None,
        "promotion_status": "NOT_CREATED",
    }
    svc._write_state(contract.task_id, state)

    def failing_salvage(*args, **kwargs):
        raise RuntimeError("salvage snapshot creation failed: index.lock")

    monkeypatch.setattr(WorktreeManager, "create_salvage_snapshot", failing_salvage)

    def timeout_runner(contract, request, update):
        raise TimeoutError("worker timed out")

    svc._custom_runner = timeout_runner
    svc._run_owned_task(contract.task_id, "attempt-1")

    final_state = svc.get_task(contract.task_id)
    assert final_state["status"] == "RETAINED_FOR_REVIEW"
    assert "worker timed out" in final_state.get("error", "")
    assert target_path.exists()
    assert final_state["cleanup_decision"] == "CLEANUP_BLOCKED"
    assert "salvage snapshot creation failed" in final_state.get("cleanup_blocker", "")


def test_self_hosted_task_service_has_single_integrate_approved_definition():
    import ast
    import collections
    import pathlib
    p = pathlib.Path("nexus/orchestrator/self_hosted_task_service.py")
    t = ast.parse(p.read_text())
    c = next(n for n in t.body if isinstance(n, ast.ClassDef) and n.name == "SelfHostedTaskService")
    names = collections.Counter(n.name for n in c.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    assert names["integrate_approved"] == 1, f"Expected 1 integrate_approved definition, got: {names['integrate_approved']}"


def test_integrate_approved_accepts_integration_branch_keyword(tmp_path, monkeypatch):
    from nexus.orchestrator.governed_integration import IntegrationReceipt
    calls = []
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "kwarg-test-task"
    service._write_state(task_id, {
        "task_id": task_id,
        "status": "APPROVED",
        "attempt_id": "a" * 32,
        "promotion_status": "APPROVED",
        "promotion_packet": {"candidate_commit_sha": "c" * 40},
        "approved_binding": {"candidate_commit_sha": "c" * 40},
        "contract": {"target_worktree_root": str(tmp_path / "targets")},
    })

    class DummyIntegrationManager:
        def __init__(self, integration_root):
            pass
        def integrate_task_state(self, state, integration_branch):
            calls.append(integration_branch)
            return IntegrationReceipt(
                schema="nexus.integration_receipt/v1",
                task_id=task_id,
                integration_branch=integration_branch,
                source_branch=f"nexus/task/{task_id}",
                candidate_commit_sha="c" * 40,
                integration_base_sha="b" * 40,
                integration_commit_sha="c" * 40,
                verifier_passed=True,
                merge_performed=True,
                push_performed=False,
                worktree_removed=True,
            )

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager", DummyIntegrationManager)
    res = service.integrate_approved(
        task_id,
        integration_branch="nexus/integration/main",
    )
    assert calls == ["nexus/integration/main"]
    assert res["status"] == "INTEGRATED"
    assert res["integration_branch"] == "nexus/integration/main"


def test_integrate_approved_is_idempotent_after_integration(tmp_path, monkeypatch):
    from nexus.orchestrator.governed_integration import IntegrationReceipt
    calls = []
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "idempotent-test-task"
    service._write_state(task_id, {
        "task_id": task_id,
        "status": "APPROVED",
        "attempt_id": "a" * 32,
        "promotion_status": "APPROVED",
        "promotion_packet": {"candidate_commit_sha": "c" * 40},
        "approved_binding": {"candidate_commit_sha": "c" * 40},
        "contract": {"target_worktree_root": str(tmp_path / "targets")},
    })

    class DummyIntegrationManager:
        def __init__(self, integration_root):
            pass
        def integrate_task_state(self, state, integration_branch):
            calls.append(integration_branch)
            return IntegrationReceipt(
                schema="nexus.integration_receipt/v1",
                task_id=task_id,
                integration_branch=integration_branch,
                source_branch=f"nexus/task/{task_id}",
                candidate_commit_sha="c" * 40,
                integration_base_sha="b" * 40,
                integration_commit_sha="c" * 40,
                verifier_passed=True,
                merge_performed=True,
                push_performed=False,
                worktree_removed=True,
            )

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager", DummyIntegrationManager)
    first = service.integrate_approved(task_id, integration_branch="nexus/integration/main")
    second = service.integrate_approved(task_id, integration_branch="nexus/integration/main")
    assert first == second
    assert len(calls) == 1


def test_integrate_approved_rejects_unapproved_state(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "unapproved-task"
    service._write_state(task_id, {
        "task_id": task_id,
        "status": "PENDING_HUMAN_APPROVAL",
        "promotion_status": "PENDING_HUMAN_APPROVAL",
    })
    with pytest.raises(RuntimeError, match="exact approved binding is required"):
        service.integrate_approved(task_id)


def test_record_integration_rejects_duck_typed_fake_receipt(tmp_path):
    from types import SimpleNamespace
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "duck-type-task"
    service._write_state(task_id, {
        "task_id": task_id,
        "status": "APPROVED",
        "promotion_status": "APPROVED",
    })
    fake_receipt = SimpleNamespace(
        task_id=task_id,
        integration_branch="nexus/integration/main",
        integration_commit_sha="c" * 40,
        integration_base_sha="b" * 40,
        verifier_passed=True,
        merge_performed=True,
        push_performed=False,
    )
    with pytest.raises(TypeError, match="receipt must be an IntegrationReceipt instance"):
        service._record_integration(fake_receipt, task_id=task_id)


def test_integration_failure_records_failed_without_merge(tmp_path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "failed-without-merge-task"
    service._write_state(task_id, {
        "task_id": task_id,
        "status": "APPROVED",
        "attempt_id": "a" * 32,
        "promotion_status": "APPROVED",
        "contract": {"target_worktree_root": str(tmp_path / "targets")},
    })

    class FailingManager:
        def __init__(self, integration_root):
            pass
        def integrate_task_state(self, state, integration_branch):
            raise RuntimeError("merge failed due to conflicts")

    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager", FailingManager)
    with pytest.raises(RuntimeError, match="merge failed due to conflicts"):
        service.integrate_approved(task_id)

    st = service._read_state(task_id)
    assert st["status"] == "INTEGRATION_FAILED"
    assert st["promotion_status"] == "INTEGRATION_FAILED"
    assert st["merge_performed"] is False
    assert st["push_performed"] is False


def test_recovery_surface_unknown_task_fails_closed(tmp_path):
    from scripts.engine.commands.self_hosted_actions import run_self_hosted_recover_verified_uncommitted, NexusCliActionError
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    with pytest.raises(NexusCliActionError, match="unknown task_id"):
        run_self_hosted_recover_verified_uncommitted("unknown-task-999", state_dir=state_dir)

    assert len(list(state_dir.glob("*.json"))) == 0


def test_recovery_surface_zero_model_calls_and_maximum_returned_status(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_TARGET_ROOT_OVERRIDE", str(tmp_path / "targets"))
    from scripts.engine.commands.self_hosted_actions import run_self_hosted_recover_verified_uncommitted
    from nexus.orchestrator.worktree_manager import WorktreeManager
    from nexus.orchestrator.candidate_verifier import VerifiedCandidateReceipt

    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"

    controller = tmp_path / "controller"
    controller.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=controller, check=True, env=env)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=controller, check=True, env=env)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=controller, check=True, env=env)
    (controller / "bounded.txt").write_text("initial\n")
    subprocess.run(["git", "add", "bounded.txt"], cwd=controller, check=True, env=env)
    subprocess.run(["git", "commit", "-m", "init"], cwd=controller, check=True, env=env)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=controller, text=True, env=env).strip()

    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    task_id = "recovery-surface-zero-calls"
    req = {
        "task_id": task_id,
        "what": "Recovery surface test",
        "why": "Verify zero provider calls",
        "allowed_files": ["bounded.txt"],
        "verifier_commands": ["python3 -c 'print(\"pass\")'"],
        "controller_repo_root": str(controller),
        "target_repo_root": str(tmp_path / "targets" / task_id),
        "target_worktree_root": str(tmp_path / "targets"),
        "controller_revision": head,
        "target_base_revision": head,
        "allow_unbound_test_identity": True,
    }
    contract = service.build_contract(req)
    wm = WorktreeManager(root_dir=contract.target_worktree_root)
    lease = wm.create_lease(contract)
    (Path(lease.target_worktree) / "bounded.txt").write_text("modified\n")
    current = wm.capture_candidate(contract, lease)

    receipt = VerifiedCandidateReceipt(
        schema="nexus.verified_candidate_receipt/v1",
        task_id=task_id,
        contract_hash=contract.contract_hash,
        lease_id=lease.lease_id,
        candidate_state_hash=current.candidate_state_hash,
        scope_gate_passed=True,
        deletion_gate_passed=True,
        controller_gate_passed=True,
        protected_contract_gate_passed=True,
        verifier_gate_passed=True,
        verified=True,
        candidate_commit_allowed=True,
        public_claim_allowed=False,
        production_ready=False,
        failure_reasons=[],
        verifier_evidence=(),
        candidate_commit_created=False,
        merge_performed=False,
    )
    service._write_state(task_id, {
        "schema": "nexus.self_hosted_task_state.v1",
        "task_id": task_id,
        "attempt_id": "a" * 32,
        "status": "RETAINED_FOR_REVIEW",
        "promotion_status": "NOT_CREATED",
        "candidate_state_hash": current.candidate_state_hash,
        "verified_receipt": receipt.__dict__,
        "lease": lease.__dict__,
        "contract": contract.model_dump(mode="json"),
        "request": req,
        "execution": {"outcome": "EXECUTION_COMPLETED"},
        "attempt_resolution": {"verdict": "PROVEN"},
    })

    provider_invoke_calls = 0
    def failing_invoke(*args, **kwargs):
        nonlocal provider_invoke_calls
        provider_invoke_calls += 1
        raise RuntimeError("Provider invoke should NOT be called during recovery")

    monkeypatch.setattr(service.worker_registry, "invoke", failing_invoke)

    res = run_self_hosted_recover_verified_uncommitted(contract.task_id, service=service)

    assert provider_invoke_calls == 0
    assert res["status"] in {"RETAINED_FOR_REVIEW", "PENDING_HUMAN_APPROVAL"}
    assert res["status"] not in {"APPROVED", "INTEGRATING", "INTEGRATED"}
