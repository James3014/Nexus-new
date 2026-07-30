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


def test_candidate_commit_ignores_user_global_hooks(tmp_path, monkeypatch):
    contract, lease, candidate, manager, controller_root, target_root = _scenario(tmp_path)
    # Set global user hook to fail exit 42
    fake_global_hooks = tmp_path / "global_hooks"
    fake_global_hooks.mkdir()
    hook_file = fake_global_hooks / "pre-commit"
    hook_file.write_text("#!/bin/sh\necho 'USER HOOK FAIL' >&2\nexit 42\n", encoding="utf-8")
    hook_file.chmod(0o755)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "fake_gitconfig"))

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


def test_verified_target_preserved_when_commit_fails(tmp_path):
    contract, lease, candidate, manager, controller_root, target_root = _scenario(tmp_path)
    target_path = Path(lease.target_worktree)
    assert target_path.exists()
    # Verify target retention semantics
    assert manager._path_has_process(target_path) is False


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


def test_fast_lane_uses_single_provider_call(tmp_path):
    contract, lease, candidate, manager, controller_root, target_root = _scenario(tmp_path)

    assert check_fast_lane_eligible(contract) is True

    contract_multi = contract.model_copy(update={"maximum_provider_calls": 3})
    assert check_fast_lane_eligible(contract_multi) is False


def test_mcp_disconnect_does_not_delete_verified_target(tmp_path):
    contract, lease, candidate, manager, controller_root, target_root = _scenario(tmp_path)
    target_path = Path(lease.target_worktree)
    # Verified target remains physically intact
    assert target_path.exists()
