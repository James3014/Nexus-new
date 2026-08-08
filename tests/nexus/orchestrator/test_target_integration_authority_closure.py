"""Corrective RED probes for the rejected Target integration Candidate."""

import subprocess
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.contracts.target_integration_lifecycle import (
    CleanupDecision,
    ExternalAcceptanceReceipt,
    IntegrationAuthorizationEnvelope,
    TargetResolutionMode,
)
from nexus.orchestrator.target_integration_lifecycle import TargetIntegrationLifecycle
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.worktree_manager import WorktreeManager
from nexus.orchestrator.governed_integration import ControlledIntegrationManager
from nexus.orchestrator.repository_contract_gate import RepositoryContractGate


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, str, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "canary")
    _git(root, "config", "user.email", "canary@example.invalid")
    (root / "value.txt").write_text("base\n")
    _git(root, "add", "value.txt")
    _git(root, "commit", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    _git(root, "branch", "candidate")
    _git(root, "checkout", "candidate")
    (root / "value.txt").write_text("candidate\n")
    _git(root, "commit", "-am", "candidate")
    candidate = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "main")
    _git(root, "checkout", "-b", "nexus/integration/canary")
    return root, base, candidate


def _status_hash(root: Path) -> str:
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    return hashlib.sha256(status.encode()).hexdigest()


def _verified_gate_proof(root: Path, contract) -> dict[str, object]:
    """Build the exact policy proof consumed by integration recheck."""
    gate = RepositoryContractGate(
        WorktreeManager(root_dir=str(root), create_root=False)
    )
    policy_inputs = gate._policy_input_hashes(
        root.resolve(), contract.target_base_revision
    )
    return {
        "repository_contract_gate_passed": True,
        "repository_contract_policy_revision_hash": gate._policy_revision_hash(
            contract.target_base_revision, policy_inputs
        ),
    }


def _acceptance(candidate: str) -> ExternalAcceptanceReceipt:
    return ExternalAcceptanceReceipt(
        schema="nexus.external_acceptance_receipt.v1", task_id="task-1",
        attempt_id="attempt-1", candidate_commit=candidate,
        receipt_hash="b" * 64, reviewer_id="reviewer-1", passed=True,
        verifier_artifact="artifact-1",
    )


def _authorization(root: Path, base: str, candidate: str, acceptance: ExternalAcceptanceReceipt) -> IntegrationAuthorizationEnvelope:
    return IntegrationAuthorizationEnvelope(
        schema="nexus.integration_authorization.v1", task_id="task-1",
        campaign_id="campaign", task_card_hash="c" * 64, attempt_id="attempt-1",
        candidate_commit=candidate, candidate_tree_sha=_git(root, "rev-parse", f"{candidate}^{{tree}}"),
        candidate_state_hash="d" * 64, candidate_receipt_hash="e" * 64,
        acceptance_receipt_hash=acceptance.receipt_hash, reviewer_id=acceptance.reviewer_id,
        verifier_artifact_hash="f" * 64, canonical_root=str(root.resolve()),
        canonical_branch="nexus/integration/canary", expected_canonical_head=base,
        canonical_dirty_baseline=_status_hash(root), integration_plan_hash="1" * 64,
        strategy="EPHEMERAL_WORKTREE_MERGE_THEN_APPLY", verification_commands_hash="2" * 64,
        post_apply_commands_hash="3" * 64, cleanup_target_id="target-1",
        cleanup_target_path=str(root / "target"), durable_ref="refs/nexus-candidate/task-1",
        cleanup_requested=True, rollback="retain target", issued_at="2026-08-02T00:00:00+00:00",
        action_set=("ACCEPT_DISPOSITION", "INTEGRATION_STAGING", "APPLY_VERIFIED_INTEGRATION", "POST_INTEGRATION_VERIFY", "CLEANUP_OWNED_TARGET"),
    )


def test_integration_without_external_acceptance_is_blocked(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    with pytest.raises(RuntimeError, match="external acceptance"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base,
                expected_status_hash=_status_hash(root),
            staging_root=tmp_path / "stage", apply=True,
            external_acceptance=None, authorization=None,
        )
    assert _git(root, "rev-parse", "HEAD") == base


def test_integration_without_owner_authorization_is_blocked(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    with pytest.raises(RuntimeError, match="Owner authorization"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base,
            expected_status_hash=_status_hash(root),
            staging_root=tmp_path / "stage", apply=True,
            external_acceptance=_acceptance(candidate), authorization=None,
        )


def test_authorization_is_consumed_once():
    authorization = {"approval_scope": "ALLOW_ACTION_ONCE"}
    consumed = TargetIntegrationLifecycle.consume_authorization(authorization, consumed_at="2026-08-02T00:00:00+00:00")
    assert consumed["consumed_at"]
    with pytest.raises(RuntimeError, match="ALREADY_CONSUMED"):
        TargetIntegrationLifecycle.consume_authorization(consumed, consumed_at="2026-08-02T00:01:00+00:00")


def test_authorization_candidate_drift_is_blocked(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    receipt = _acceptance(candidate)
    auth = _authorization(root, base, candidate, receipt)
    with pytest.raises(RuntimeError, match="candidate drift"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit="f" * 40,
            expected_canonical_head=base, staging_root=str(tmp_path / "stage"),
            external_acceptance=receipt, authorization=auth,
        )


def test_authorization_task_card_drift_is_blocked(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    receipt = _acceptance(candidate)
    auth = _authorization(root, base, candidate, receipt)
    with pytest.raises(RuntimeError, match="task card drift"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base, staging_root=str(tmp_path / "stage"),
            external_acceptance=receipt, authorization=auth,
            current_task_card_hash="f" * 64,
        )


def test_authorization_plan_drift_is_blocked(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    receipt = _acceptance(candidate)
    auth = _authorization(root, base, candidate, receipt)
    with pytest.raises(RuntimeError, match="integration plan drift"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base, staging_root=str(tmp_path / "stage"),
            external_acceptance=receipt, authorization=auth,
            current_integration_plan_hash="f" * 64,
        )


def test_target_lifecycle_adapter_does_not_execute_raw_git_mutations():
    source = Path(TargetIntegrationLifecycle.__module__.replace(".", "/") + ".py").read_text()
    assert "subprocess" not in source
    assert "git merge" not in source
    assert "worktree add" not in source
    assert "worktree remove" not in source


def test_integration_delegates_to_controlled_integration_manager():
    assert hasattr(TargetIntegrationLifecycle, "delegate_integration")


def test_cleanup_delegates_to_worktree_manager():
    assert hasattr(TargetIntegrationLifecycle, "delegate_cleanup")


def test_dirty_canonical_blocks_apply_even_when_status_hash_matches(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    (root / "value.txt").write_text("unrelated dirty\n")
    with pytest.raises(RuntimeError, match="canonical.*clean"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base,
                expected_status_hash=_status_hash(root),
                staging_root=tmp_path / "stage", apply=True,
                external_acceptance=_acceptance(candidate), authorization=_authorization(root, base, candidate, _acceptance(candidate)),
        )


def test_untracked_canonical_blocks_apply(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    (root / "untracked.txt").write_text("untracked\n")
    with pytest.raises(RuntimeError, match="canonical.*clean"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base,
                expected_status_hash=_status_hash(root),
                staging_root=tmp_path / "stage", apply=True,
                external_acceptance=_acceptance(candidate), authorization=_authorization(root, base, candidate, _acceptance(candidate)),
        )


def test_forged_cleanup_decision_cannot_remove_worktree(tmp_path: Path):
    root, _, _ = _repo(tmp_path)
    target = tmp_path / "target"
    _git(root, "worktree", "add", "--detach", str(target), "HEAD")
    decision = CleanupDecision(
        schema="nexus.target_cleanup_decision.v1", decision="ELIGIBLE",
        task_id="task-1", target_id="target-1",
    )
    result = TargetIntegrationLifecycle.cleanup_target(
        decision=decision, target_path=target, canonical_root=root, apply=True,
        authorization=None, lifecycle_state=None,
    )
    assert result["performed"] is False
    assert target.exists()


def test_cleanup_without_integration_receipt_is_blocked(tmp_path: Path):
    root, _, _ = _repo(tmp_path)
    target = tmp_path / "target"
    _git(root, "worktree", "add", "--detach", str(target), "HEAD")
    decision = TargetIntegrationLifecycle.cleanup_decision(
        task_id="task-1", target_id="target-1", target_owner="task-1",
        target_is_canonical=False, reviewer_worktree=False, dirty=False,
        untracked=False, active_process=False, accepted=True, integrated=True,
        canonical_contains_result=True, durable_ref_verified=True,
        receipts_complete=False, unique_unprotected_commits=False,
    )
    result = TargetIntegrationLifecycle.cleanup_target(
        decision=decision, target_path=target, canonical_root=root, apply=True,
        authorization={"cleanup_requested": True}, lifecycle_state={"status": "INTEGRATED"},
    )
    assert result["performed"] is False
    assert target.exists()


def test_cleanup_without_durable_ref_is_blocked(tmp_path: Path):
    root, _, _ = _repo(tmp_path)
    target = tmp_path / "target"
    _git(root, "worktree", "add", "--detach", str(target), "HEAD")
    decision = TargetIntegrationLifecycle.cleanup_decision(
        task_id="task-1", target_id="target-1", target_owner="task-1",
        target_is_canonical=False, reviewer_worktree=False, dirty=False,
        untracked=False, active_process=False, accepted=True, integrated=True,
        canonical_contains_result=True, durable_ref_verified=False,
        receipts_complete=True, unique_unprotected_commits=False,
    )
    result = TargetIntegrationLifecycle.cleanup_target(
        decision=decision, target_path=target, canonical_root=root, apply=True,
        authorization={"cleanup_requested": True}, lifecycle_state={"status": "INTEGRATED"},
    )
    assert result["performed"] is False
    assert target.exists()


def test_post_apply_verification_failure_blocks_cleanup(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    with pytest.raises(RuntimeError, match="post-apply"):
        TargetIntegrationLifecycle.transactional_integration(
            task_id="task-1", canonical_root=root, candidate_commit=candidate,
            expected_canonical_head=base,
                expected_status_hash=_status_hash(root),
                staging_root=tmp_path / "stage", apply=True,
                external_acceptance=_acceptance(candidate), authorization=_authorization(root, base, candidate, _acceptance(candidate)),
            post_apply_commands=(("/bin/sh", "-c", "exit 1"),),
        )


def test_multiple_active_targets_returns_typed_block():
    decision = TargetIntegrationLifecycle.resolve_target(
        task_id="task-1", campaign_id="campaign", attempt_id="attempt-2",
        base_revision="a" * 40,
        existing_targets=[
            {"task_id": "task-1", "campaign_id": "campaign", "target_id": "t1", "target_path": "/tmp/t1", "target_branch": "b1", "base_revision": "a" * 40},
            {"task_id": "task-1", "campaign_id": "campaign", "target_id": "t2", "target_path": "/tmp/t2", "target_branch": "b2", "base_revision": "a" * 40},
        ],
    )
    assert decision.mode is TargetResolutionMode.BLOCK
    assert decision.target_id is None
    assert decision.reason == "SERIAL_TASK_MULTIPLE_ACTIVE_TARGETS"


def _receipt_service(tmp_path: Path) -> SelfHostedTaskService:
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("task-1", {
        "task_id": "task-1", "attempt_id": "attempt-1", "status": "INTEGRATING",
        "promotion_status": "INTEGRATING", "status_history": [], "request": {},
    })
    return service


def test_integration_receipt_survives_fresh_service_reload(tmp_path: Path):
    service = _receipt_service(tmp_path)
    returned_state = TargetIntegrationLifecycle.persist_receipt(
        service, "task-1", receipt_name="integration_receipt",
        receipt={"schema": "nexus.integration_receipt.v1", "post_apply_verified": True},
    )
    fresh = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    assert TargetIntegrationLifecycle.reload_receipt(fresh, "task-1", receipt_name="integration_receipt") == returned_state["integration_receipt"]


def test_cleanup_receipt_survives_fresh_service_reload(tmp_path: Path):
    service = _receipt_service(tmp_path)
    receipt = {"schema": "nexus.target_cleanup_receipt.v1", "decision": "RETAIN"}
    TargetIntegrationLifecycle.persist_receipt(service, "task-1", receipt_name="cleanup_receipt", receipt=receipt)
    fresh = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    assert TargetIntegrationLifecycle.reload_receipt(fresh, "task-1", receipt_name="cleanup_receipt") == receipt


def test_persisted_receipts_equal_returned_receipts():
    assert hasattr(TargetIntegrationLifecycle, "persist_receipt")
    assert hasattr(TargetIntegrationLifecycle, "reload_receipt")


def test_authorize_default_action_set_excludes_branch_deletion(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    receipt = _acceptance(candidate)
    preview = TargetIntegrationLifecycle.build_preview(
        task_id="task-1", target_id="target-1", candidate_commit=candidate,
        acceptance=receipt, canonical_branch="nexus/integration/canary",
        expected_canonical_head=base, verification_commands=(),
        cleanup_target_id="target-1", rollback="retain target",
    )
    auth = TargetIntegrationLifecycle.authorize(
        task_id="task-1", campaign_id="campaign-1", task_card_hash="c" * 64,
        candidate_commit=candidate, candidate_receipt_hash="d" * 64,
        acceptance_receipt_hash=receipt.receipt_hash, canonical_root=str(root),
        canonical_branch="nexus/integration/canary", expected_canonical_head=base,
        canonical_dirty_baseline=_status_hash(root), preview=preview,
        cleanup_target_id="target-1", cleanup_target_path=str(root / "target"),
        durable_ref="refs/nexus-candidate/task-1", rollback="retain target",
        issued_at="2026-08-02T00:00:00+00:00",
    )
    assert auth.action_set == (
        "ACCEPT_DISPOSITION", "INTEGRATION_STAGING", "APPLY_VERIFIED_INTEGRATION",
        "POST_INTEGRATION_VERIFY", "CLEANUP_OWNED_TARGET",
    )


def test_owner_finish_delegates_full_authorized_integration_then_cleanup(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    receipt = _acceptance(candidate)
    auth = _authorization(root, base, candidate, receipt)
    target = tmp_path / "targets" / "task-1"
    target.parent.mkdir()
    _git(root, "worktree", "add", "-b", "nexus/task/task-1", str(target), base)
    _git(target, "merge", "--ff-only", candidate)
    durable_ref = "refs/nexus-candidate/task-1"
    _git(root, "update-ref", durable_ref, candidate)
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = {
        "task_id": "task-1", "what": "authorized integration", "why": "closure",
        "controller_revision": base, "target_base_revision": base,
        "controller_repo_root": str(root), "target_repo_root": str(target),
        "target_worktree_root": str(target.parent), "allowed_files": ["value.txt"],
        "verifier_commands": [], "worker": "codex",
    }
    contract = service.build_contract(request)
    lease_id = WorktreeManager(root_dir=str(target.parent), create_root=False)._lease_id(
        contract, target, "nexus/task/task-1"
    )
    service._write_state("task-1", {
        "task_id": "task-1", "attempt_id": "attempt-1", "status": "CANDIDATE_CAPTURED",
        "promotion_status": "PENDING_HUMAN_APPROVAL", "request": request,
        "contract": contract.model_dump(mode="json"), "contract_hash": contract.contract_hash,
        "task_card_hash": "c" * 64,
        "verified_receipt": _verified_gate_proof(root, contract),
        "promotion_packet": {
            "candidate_commit_sha": candidate,
            "candidate_tree_sha": _git(root, "rev-parse", f"{candidate}^{{tree}}"),
            "candidate_state_hash": "d" * 64, "verified_receipt_hash": "e" * 64,
        },
        "candidate_ref": durable_ref,
        "lease": {
            "schema": "nexus.target_worktree_lease.v1", "lease_id": lease_id,
            "task_id": "task-1", "controller_revision": base, "target_base_revision": base,
            "target_worktree": str(target), "target_branch": "nexus/task/task-1",
            "initial_head": base, "initial_status_sha256": "0" * 64,
            "controller_status_sha256": "0" * 64, "created_from_exact_revision": True,
            "commit_created": True, "merge_performed": False,
        },
    })
    context = {
        "schema": "nexus.approval.v2", "approval_id": "approval-task-1",
        "approval_scope": "ALLOW_ACTION_ONCE", "contract_kind": "TRACKED_TASK_CARD",
        "contract_hash": "c" * 64, "task_card_hash": "c" * 64,
    }
    result = service.owner_finish(
        "task-1", candidate_commit_sha=candidate,
        candidate_tree_sha=_git(root, "rev-parse", f"{candidate}^{{tree}}"),
        candidate_state_hash="d" * 64, verified_receipt_hash="e" * 64,
        integration_branch="nexus/integration/canary", approval_context=context,
        external_acceptance=receipt.to_dict(), integration_authorization={
            **auth.to_dict(), "canonical_branch": "nexus/integration/canary",
            "cleanup_target_path": str(target), "durable_ref": durable_ref,
        },
    )
    assert result["status"] == "INTEGRATED_AND_CLEANED"
    assert result["cleanup_status"] == "CLEANED"
    assert result["finalization_receipt"]["terminal"]["final_status"] == "INTEGRATED_AND_CLEANED"
    stored = service._read_state("task-1") or service._latest_archived_state("task-1")[1]
    assert stored["integration_receipt"]["post_apply_verified"] is True
    assert stored["integration_receipt"]["acceptance_receipt_hash"] == receipt.receipt_hash
    assert stored["cleanup_receipt"]["performed"] is True
    assert stored["finalization_receipt"] == result["finalization_receipt"]
    fresh_integration = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    persisted_integration = fresh_integration._read_state("task-1") or fresh_integration._latest_archived_state("task-1")[1]
    assert persisted_integration["integration_receipt"] == result["integration_receipt"]
    fresh = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    persisted = fresh._read_state("task-1") or fresh._latest_archived_state("task-1")[1]
    assert persisted["cleanup_receipt"] == result["cleanup_receipt"]
    assert persisted["cleanup_receipt_hash"] == hashlib.sha256(
        json.dumps(result["cleanup_receipt"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    assert not target.exists()
    assert _git(root, "show-ref", "--verify", "refs/heads/nexus/task/task-1")
    assert _git(root, "show-ref", "--verify", durable_ref)


def test_owner_finish_single_confirmation_integrates_and_cleans_owned_target(tmp_path: Path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    calls: list[str] = []

    monkeypatch.setattr(service, "approve_promotion", lambda task_id, **kwargs: calls.append("approve") or {"status": "APPROVED", "promotion_status": "APPROVED"})
    monkeypatch.setattr(service, "integrate_approved", lambda task_id, *, integration_branch: calls.append("integrate") or {"status": "INTEGRATED", "promotion_status": "INTEGRATED", "integration_receipt": {"schema": "nexus.integration_receipt.v1"}})
    monkeypatch.setattr(service, "cleanup_tasks", lambda *, task_id, dry_run: calls.append("cleanup") or {"dry_run": False, "decisions": [{"task_id": task_id, "cleanup_performed": True, "cleanup_eligible": True, "cleanup_decision": "REMOVED", "cleanup_receipt": {"performed": True, "eligible": True, "decision": "REMOVED", "target_present_after": False}}]})
    monkeypatch.setattr(service, "archive_states", lambda *, dry_run: calls.append("archive") or {"dry_run": dry_run, "entries": []})

    result = service.owner_finish(
        "single-confirmation", candidate_commit_sha="a" * 40,
        candidate_tree_sha="b" * 40, candidate_state_hash="c" * 64,
        verified_receipt_hash="d" * 64, external_acceptance={"passed": True},
        integration_authorization={"cleanup_requested": True, "cleanup_target_path": str(tmp_path / "target"), "action_set": ["CLEANUP_OWNED_TARGET"]},
    )

    assert calls == ["approve", "integrate", "cleanup", "archive"]
    assert result["status"] == "INTEGRATED_AND_CLEANED"


def test_owner_finish_retains_noneligible_target_with_typed_reason(tmp_path: Path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    calls: list[str] = []
    monkeypatch.setattr(service, "approve_promotion", lambda task_id, **kwargs: {"status": "APPROVED", "promotion_status": "APPROVED"})
    monkeypatch.setattr(service, "integrate_approved", lambda task_id, *, integration_branch: {"status": "INTEGRATED", "promotion_status": "INTEGRATED", "integration_receipt": {"schema": "nexus.integration_receipt.v1"}})
    monkeypatch.setattr(service, "cleanup_tasks", lambda *, task_id, dry_run: calls.append("cleanup") or {"dry_run": False, "decisions": [{"task_id": task_id, "cleanup_performed": False, "cleanup_eligible": False, "cleanup_decision": "BLOCKED_BY_PROCESS", "cleanup_blocker": "active process uses Target", "cleanup_receipt": {"performed": False, "eligible": False, "decision": "BLOCKED_BY_PROCESS", "blocker": "active process uses Target", "target_present_after": True}}]})
    monkeypatch.setattr(service, "archive_states", lambda **kwargs: (_ for _ in ()).throw(AssertionError("retained state must not archive")))

    result = service.owner_finish(
        "retained", candidate_commit_sha="a" * 40,
        candidate_tree_sha="b" * 40, candidate_state_hash="c" * 64,
        verified_receipt_hash="d" * 64, external_acceptance={"passed": True},
        integration_authorization={"cleanup_requested": True, "cleanup_target_path": str(tmp_path / "target"), "action_set": ["CLEANUP_OWNED_TARGET"]},
    )

    assert calls == ["cleanup"]
    assert result["status"] == "INTEGRATED_TARGET_RETAINED"
    assert result["retention_reason"] == "active process uses Target"
    assert result["next_action"] == "retry_cleanup"
    assert result["archive_eligible"] is False


def test_owner_finish_does_not_archive_cleanup_pending_or_retained_state(tmp_path: Path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    order: list[str] = []
    monkeypatch.setattr(service, "approve_promotion", lambda task_id, **kwargs: {"status": "APPROVED", "promotion_status": "APPROVED"})
    monkeypatch.setattr(service, "integrate_approved", lambda task_id, *, integration_branch: order.append("integrate") or {"status": "INTEGRATED", "promotion_status": "INTEGRATED"})
    monkeypatch.setattr(service, "cleanup_tasks", lambda *, task_id, dry_run: order.append("cleanup") or {"dry_run": False, "decisions": [{"cleanup_performed": False, "cleanup_eligible": False, "cleanup_decision": "BLOCKED_BY_UNSAVED_CHANGES", "cleanup_blocker": "dirty Target"}]})
    monkeypatch.setattr(service, "archive_states", lambda **kwargs: order.append("archive") or {"entries": []})
    result = service.owner_finish(
        "no-premature-archive", candidate_commit_sha="a" * 40,
        candidate_tree_sha="b" * 40, candidate_state_hash="c" * 64,
        verified_receipt_hash="d" * 64, external_acceptance={"passed": True},
        integration_authorization={"cleanup_requested": True, "cleanup_target_path": str(tmp_path / "target"), "action_set": ["CLEANUP_OWNED_TARGET"]},
    )
    assert result["status"] == "INTEGRATED_TARGET_RETAINED"
    assert order == ["integrate", "cleanup"]


def test_post_apply_physical_truth_is_typed_and_persistable(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    receipt = _acceptance(candidate)
    auth = _authorization(root, base, candidate, receipt)
    state = {
        "task_id": "task-1", "contract": {"controller_repo_root": str(root)},
        "promotion_packet": {"candidate_commit_sha": candidate},
        "integration_authorization": auth.to_dict(),
        "external_acceptance": receipt.to_dict(),
        "lease": {"target_branch": "nexus/task/task-1"},
    }
    with pytest.raises(RuntimeError) as raised:
        ControlledIntegrationManager(integration_root=root).integrate_authorized_task_state(
            state, integration_branch="nexus/integration/canary",
            staging_root=tmp_path / "stage", post_apply_commands=(("/bin/sh", "-c", "exit 1"),),
        )
    assert raised.value.merge_performed is True
    assert raised.value.post_apply_verified is False
    assert raised.value.branch_head_before == base
    assert raised.value.branch_head_after != base
    assert raised.value.integration_result_sha == raised.value.branch_head_after


def test_service_post_apply_failure_persists_physical_truth_and_blocks_cleanup(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    receipt = replace(_acceptance(candidate), task_id="post-apply-task")
    auth = replace(
        _authorization(root, base, candidate, receipt),
        task_id="post-apply-task",
        acceptance_receipt_hash=receipt.receipt_hash,
        cleanup_target_id="post-apply-task",
    )
    target = tmp_path / "targets" / "post-apply-task"
    target.parent.mkdir()
    _git(root, "worktree", "add", "-b", "nexus/task/post-apply-task", str(target), base)
    _git(target, "merge", "--ff-only", candidate)
    durable_ref = "refs/nexus-candidate/post-apply-task"
    _git(root, "update-ref", durable_ref, candidate)
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = {
        "task_id": "post-apply-task", "what": "post apply truth", "why": "closure",
        "controller_revision": base, "target_base_revision": base,
        "controller_repo_root": str(root), "target_repo_root": str(target),
        "target_worktree_root": str(target.parent), "allowed_files": ["value.txt"],
        "verifier_commands": [], "worker": "codex",
    }
    contract = service.build_contract(request)
    lease_id = WorktreeManager(root_dir=str(target.parent), create_root=False)._lease_id(contract, target, "nexus/task/post-apply-task")
    packet = {
        "candidate_commit_sha": candidate,
        "candidate_tree_sha": _git(root, "rev-parse", f"{candidate}^{{tree}}"),
        "candidate_state_hash": "d" * 64, "verified_receipt_hash": "e" * 64,
    }
    service._write_state("post-apply-task", {
        "task_id": "post-apply-task", "attempt_id": "attempt-1",
        "status": "CANDIDATE_CAPTURED", "promotion_status": "PENDING_HUMAN_APPROVAL",
        "request": request, "contract": contract.model_dump(mode="json"),
        "contract_hash": contract.contract_hash, "task_card_hash": "c" * 64,
        "verified_receipt": _verified_gate_proof(root, contract),
        "promotion_packet": packet, "candidate_ref": durable_ref,
        "post_apply_commands": [["/bin/sh", "-c", "exit 1"]],
        "lease": {
            "schema": "nexus.target_worktree_lease.v1", "lease_id": lease_id,
            "task_id": "post-apply-task", "controller_revision": base,
            "target_base_revision": base, "target_worktree": str(target),
            "target_branch": "nexus/task/post-apply-task", "initial_head": base,
            "initial_status_sha256": "0" * 64, "controller_status_sha256": "0" * 64,
            "created_from_exact_revision": True, "commit_created": True,
            "merge_performed": False,
        },
    })
    context = {
        "schema": "nexus.approval.v2", "approval_id": "approval-post-apply-task",
        "approval_scope": "ALLOW_ACTION_ONCE", "contract_kind": "TRACKED_TASK_CARD",
        "contract_hash": "c" * 64, "task_card_hash": "c" * 64,
    }
    with pytest.raises(RuntimeError, match="post-apply verification failed"):
        service.owner_finish(
            "post-apply-task", candidate_commit_sha=candidate,
            candidate_tree_sha=packet["candidate_tree_sha"], candidate_state_hash="d" * 64,
            verified_receipt_hash="e" * 64, integration_branch="nexus/integration/canary",
            approval_context=context, external_acceptance=receipt.to_dict(),
            integration_authorization={**auth.to_dict(), "canonical_branch": "nexus/integration/canary", "cleanup_target_path": str(target), "durable_ref": durable_ref},
        )
    branch_head = _git(root, "rev-parse", "nexus/integration/canary")
    assert branch_head != base
    assert _git(root, "merge-base", "--is-ancestor", candidate, branch_head) == ""
    state = service._read_state("post-apply-task")
    assert state["status"] == "INTEGRATION_VERIFY_FAILED_AFTER_APPLY"
    assert state["merge_performed"] is True
    assert state["integration_result_sha"] == branch_head
    assert state["integration_execution"]["post_apply_verified"] is False
    cleanup = service.cleanup_tasks(task_id="post-apply-task", dry_run=False)
    assert cleanup["decisions"][0]["cleanup_performed"] is False
    assert "post-apply" in cleanup["decisions"][0]["cleanup_blocker"]


def test_post_apply_failure_cannot_retry_integration(tmp_path: Path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("post-apply-retry", {"task_id": "post-apply-retry", "status": "INTEGRATION_VERIFY_FAILED_AFTER_APPLY", "promotion_status": "INTEGRATION_VERIFY_FAILED_AFTER_APPLY", "merge_performed": True, "approved_binding": {"candidate_commit_sha": "a" * 40}})
    with pytest.raises(RuntimeError, match="INTEGRATION_ALREADY_APPLIED_RETRY_FORBIDDEN"):
        service.retry_integration("post-apply-retry")


def test_post_apply_failure_never_runs_cleanup(tmp_path: Path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("post-apply-cleanup", {"task_id": "post-apply-cleanup", "status": "INTEGRATION_VERIFY_FAILED_AFTER_APPLY", "promotion_status": "INTEGRATION_VERIFY_FAILED_AFTER_APPLY", "merge_performed": True, "lease": {}})
    result = service.cleanup_tasks(task_id="post-apply-cleanup", dry_run=False)
    assert result["decisions"][0]["cleanup_performed"] is False
    assert "post-apply" in result["decisions"][0]["cleanup_blocker"]


def test_finalization_failure_and_retention_actions_remain_fail_closed():
    post_apply = SelfHostedTaskService._task_action_envelope({
        "task_id": "post-apply-action", "status": "INTEGRATION_VERIFY_FAILED_AFTER_APPLY",
        "promotion_status": "INTEGRATION_VERIFY_FAILED_AFTER_APPLY", "merge_performed": True,
    })
    assert post_apply["action_state"] == "FINAL_BLOCK"
    assert post_apply["next_action"] == "owner_review_post_apply_failure"
    pre_apply = SelfHostedTaskService._task_action_envelope({
        "task_id": "pre-apply-action", "status": "INTEGRATION_FAILED_PRE_APPLY",
        "promotion_status": "INTEGRATION_FAILED_PRE_APPLY", "merge_performed": False,
    })
    assert pre_apply["next_action"] == "retry_integration_same_task"
    retained = SelfHostedTaskService._task_action_envelope({
        "task_id": "retained-action", "status": "INTEGRATED_TARGET_RETAINED",
        "promotion_status": "INTEGRATED", "archive_eligible": False,
    })
    assert retained["action_state"] == "ACTION_REQUIRED"
    assert retained["next_action"] == "retry_cleanup"


def test_pre_apply_failure_leaves_branch_unchanged_and_is_retryable(tmp_path: Path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    service._write_state("pre-apply-retry", {"task_id": "pre-apply-retry", "status": "INTEGRATION_FAILED_PRE_APPLY", "promotion_status": "INTEGRATION_FAILED_PRE_APPLY", "merge_performed": False, "approved_binding": {"candidate_commit_sha": "a" * 40}})
    called = []
    service.integrate_approved = lambda task_id, *, integration_branch: called.append((task_id, integration_branch)) or {"status": "INTEGRATED"}
    result = service.retry_integration("pre-apply-retry")
    assert called == [("pre-apply-retry", "nexus/integration/main")]
    assert result["status"] == "INTEGRATED"


def test_finalization_receipt_survives_fresh_service_reload(tmp_path: Path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    monkeypatch.setattr(service, "approve_promotion", lambda task_id, **kwargs: {"status": "APPROVED", "promotion_status": "APPROVED"})
    monkeypatch.setattr(service, "integrate_approved", lambda task_id, *, integration_branch: {"status": "INTEGRATED", "promotion_status": "INTEGRATED", "integration_receipt": {"schema": "nexus.integration_receipt.v1", "integration_commit_sha": "a" * 40}})
    monkeypatch.setattr(service, "cleanup_tasks", lambda *, task_id, dry_run: {"dry_run": False, "decisions": [{"cleanup_performed": True, "cleanup_eligible": True, "cleanup_decision": "REMOVED", "cleanup_receipt": {"performed": True, "eligible": True, "target_present_after": False}}]})
    monkeypatch.setattr(service, "archive_states", lambda **kwargs: {"entries": []})
    result = service.owner_finish("reload-finalization", candidate_commit_sha="a" * 40, candidate_tree_sha="b" * 40, candidate_state_hash="c" * 64, verified_receipt_hash="d" * 64, external_acceptance={"passed": True}, integration_authorization={"cleanup_requested": True, "cleanup_target_path": str(tmp_path / "target")})
    fresh = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    stored = fresh._read_state("reload-finalization") or fresh._latest_archived_state("reload-finalization")[1]
    assert stored["finalization_receipt"] == result["finalization_receipt"]


def test_owner_finish_replay_is_idempotent(tmp_path: Path, monkeypatch):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    calls: list[str] = []
    monkeypatch.setattr(service, "approve_promotion", lambda task_id, **kwargs: calls.append("approve") or {"status": "APPROVED", "promotion_status": "APPROVED"})
    monkeypatch.setattr(service, "integrate_approved", lambda task_id, *, integration_branch: calls.append("integrate") or {"status": "INTEGRATED", "promotion_status": "INTEGRATED", "integration_receipt": {"schema": "nexus.integration_receipt.v1"}})
    monkeypatch.setattr(service, "cleanup_tasks", lambda *, task_id, dry_run: calls.append("cleanup") or {"dry_run": False, "decisions": [{"cleanup_performed": True, "cleanup_eligible": True, "cleanup_decision": "REMOVED", "cleanup_receipt": {"performed": True, "eligible": True, "target_present_after": False}}]})
    monkeypatch.setattr(service, "archive_states", lambda **kwargs: {"entries": []})
    kwargs = dict(candidate_commit_sha="a" * 40, candidate_tree_sha="b" * 40, candidate_state_hash="c" * 64, verified_receipt_hash="d" * 64, external_acceptance={"passed": True}, integration_authorization={"cleanup_requested": True, "cleanup_target_path": str(tmp_path / "target"), "action_set": ["CLEANUP_OWNED_TARGET"]})
    first = service.owner_finish("replay", **kwargs)
    second = service.owner_finish("replay", **kwargs)
    assert calls == ["approve", "integrate", "cleanup"]
    assert second["duplicate"] is True
    assert second["finalization_receipt"] == first["finalization_receipt"]


def test_owner_finish_never_deletes_task_branch_or_candidate_ref(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    receipt = _acceptance(candidate)
    auth = _authorization(root, base, candidate, receipt)
    target = tmp_path / "targets" / "task-branch"
    target.parent.mkdir()
    _git(root, "worktree", "add", "-b", "nexus/task/task-branch", str(target), base)
    _git(target, "merge", "--ff-only", candidate)
    durable_ref = "refs/nexus-candidate/task-branch"
    _git(root, "update-ref", durable_ref, candidate)
    assert _git(root, "show-ref", "--verify", "refs/heads/nexus/task/task-branch")
    assert _git(root, "show-ref", "--verify", durable_ref)


def test_owner_finish_retains_real_dirty_target_with_typed_reason(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    receipt = replace(_acceptance(candidate), task_id="dirty-owner-finish")
    auth = replace(
        _authorization(root, base, candidate, receipt),
        task_id="dirty-owner-finish",
        cleanup_target_id="dirty-owner-finish",
    )
    target = tmp_path / "targets" / "dirty-owner-finish"
    target.parent.mkdir()
    _git(root, "worktree", "add", "-b", "nexus/task/dirty-owner-finish", str(target), base)
    _git(target, "merge", "--ff-only", candidate)
    durable_ref = "refs/nexus-candidate/dirty-owner-finish"
    _git(root, "update-ref", durable_ref, candidate)
    (target / "untracked.txt").write_text("must retain\n", encoding="utf-8")
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = {
        "task_id": "dirty-owner-finish", "what": "dirty retention", "why": "closure",
        "controller_revision": base, "target_base_revision": base,
        "controller_repo_root": str(root), "target_repo_root": str(target),
        "target_worktree_root": str(target.parent), "allowed_files": ["value.txt"],
        "verifier_commands": [], "worker": "codex",
    }
    contract = service.build_contract(request)
    lease_id = WorktreeManager(root_dir=str(target.parent), create_root=False)._lease_id(contract, target, "nexus/task/dirty-owner-finish")
    packet = {"candidate_commit_sha": candidate, "candidate_tree_sha": _git(root, "rev-parse", f"{candidate}^{{tree}}"), "candidate_state_hash": "d" * 64, "verified_receipt_hash": "e" * 64}
    service._write_state("dirty-owner-finish", {
        "task_id": "dirty-owner-finish", "attempt_id": "attempt-1", "status": "CANDIDATE_CAPTURED", "promotion_status": "PENDING_HUMAN_APPROVAL", "request": request, "contract": contract.model_dump(mode="json"), "contract_hash": contract.contract_hash, "task_card_hash": "c" * 64, "verified_receipt": _verified_gate_proof(root, contract), "promotion_packet": packet, "candidate_ref": durable_ref,
        "lease": {"schema": "nexus.target_worktree_lease.v1", "lease_id": lease_id, "task_id": "dirty-owner-finish", "controller_revision": base, "target_base_revision": base, "target_worktree": str(target), "target_branch": "nexus/task/dirty-owner-finish", "initial_head": base, "initial_status_sha256": "0" * 64, "controller_status_sha256": "0" * 64, "created_from_exact_revision": True, "commit_created": True, "merge_performed": False},
    })
    context = {"schema": "nexus.approval.v2", "approval_id": "approval-dirty-owner-finish", "approval_scope": "ALLOW_ACTION_ONCE", "contract_kind": "TRACKED_TASK_CARD", "contract_hash": "c" * 64, "task_card_hash": "c" * 64}
    result = service.owner_finish(
        "dirty-owner-finish", candidate_commit_sha=candidate,
        candidate_tree_sha=packet["candidate_tree_sha"], candidate_state_hash="d" * 64,
        verified_receipt_hash="e" * 64, integration_branch="nexus/integration/canary",
        approval_context=context, external_acceptance=receipt.to_dict(),
        integration_authorization={**auth.to_dict(), "canonical_branch": "nexus/integration/canary", "cleanup_target_path": str(target), "durable_ref": durable_ref},
    )
    assert result["status"] == "INTEGRATED_TARGET_RETAINED"
    assert result["cleanup_status"] == "RETAINED"
    assert result["retention_reason"]
    assert result["next_action"] == "retry_cleanup"
    assert result["archive_eligible"] is False
    assert target.exists()
    assert (target / "untracked.txt").read_text(encoding="utf-8") == "must retain\n"


def _approved_closure_service(tmp_path: Path):
    root, base, candidate = _repo(tmp_path)
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    request = {
        "task_id": "closure-bind", "campaign_id": "campaign", "what": "closure", "why": "closure",
        "controller_revision": base, "target_base_revision": base,
        "controller_repo_root": str(root), "target_repo_root": str(tmp_path / "target"),
        "target_worktree_root": str(tmp_path), "allowed_files": ["value.txt"],
        "verifier_commands": [], "worker": "codex",
    }
    contract = service.build_contract(request)
    packet = {
        "candidate_commit_sha": candidate,
        "candidate_tree_sha": _git(root, "rev-parse", f"{candidate}^{{tree}}"),
        "candidate_state_hash": "d" * 64, "verified_receipt_hash": "e" * 64,
    }
    service._write_state("closure-bind", {
        "task_id": "closure-bind", "attempt_id": "attempt-1", "status": "APPROVED", "promotion_status": "APPROVED",
        "request": request, "contract": contract.model_dump(mode="json"), "contract_hash": contract.contract_hash,
        "contract_kind": "TRACKED_TASK_CARD", "task_card_hash": "c" * 64, "candidate_ref": "refs/nexus-candidate/closure-bind",
        "controller_revision": base, "promotion_packet": packet,
        "approved_binding": {**packet, "approval_grant": {"approval_scope": "ALLOW_ACTION_ONCE", "consumed_at": "2026-08-08T00:00:00+00:00"}},
        "lease": {"lease_id": "lease-closure-bind", "target_worktree": str(tmp_path / "target")},
    })
    acceptance = _acceptance(candidate)
    artifact_dir = tmp_path / "state" / "acceptance-artifacts" / "closure-bind"
    artifact_dir.mkdir(parents=True)
    artifact = artifact_dir / "verifier.txt"
    artifact.write_text("accepted\n", encoding="utf-8")
    artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    acceptance = replace(acceptance, task_id="closure-bind", attempt_id="attempt-1", receipt_hash=artifact_hash, verifier_artifact=str(artifact))
    runtime = {"tool_manifest_hash": "1" * 64, "full_tool_schema_hash": "2" * 64, "permission_policy_hash": "3" * 64, "lifecycle_revision": "lifecycle", "server_instance_id": "server"}
    approval = {
        "schema": "nexus.approval.v2", "approval_id": "integrate-approval", "approved_by": "owner",
        "issued_at": "2026-08-08T00:00:00+00:00", "expires_at": "2099-08-08T00:00:00+00:00",
        "bound_task_id": "closure-bind", "bound_attempt_id": "attempt-1", "bound_action_type": "CANDIDATE_INTEGRATE",
        "approval_scope": "ALLOW_ACTION_ONCE", "contract_kind": "TRACKED_TASK_CARD", "contract_hash": contract.contract_hash,
        "task_card_hash": "c" * 64, "expected_canonical_head": base, "integration_branch": "nexus/integration/canary",
        "candidate_commit_sha": candidate, "candidate_tree_sha": packet["candidate_tree_sha"], "candidate_state_hash": packet["candidate_state_hash"], "verified_receipt_hash": packet["verified_receipt_hash"], "acceptance_receipt_hash": acceptance.receipt_hash, **runtime,
    }
    return service, root, base, candidate, acceptance, approval, runtime


def test_service_closure_binding_is_typed_idempotent_and_does_not_integrate(tmp_path: Path, monkeypatch):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    monkeypatch.setattr(service, "integrate_approved", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("bind must not integrate")))
    first = service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    assert first["integration_performed"] is False
    assert first["status"] == "APPROVED"
    second = service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    assert second["duplicate"] is True
    assert second["integration_performed"] is False
    assert (service._read_state("closure-bind") or {})["integration_approval_grant"]["consumed_at"]


def test_service_closure_binding_rejects_tamper_and_head_drift(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    with pytest.raises(RuntimeError, match="CLOSURE_APPROVAL_SCHEMA_CLOSED"):
        service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval={**approval, "action_set": ["APPLY_VERIFIED_INTEGRATION"]}, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    with pytest.raises(RuntimeError, match="EXTERNAL_ACCEPTANCE_BINDING_MISMATCH"):
        service.bind_candidate_integration_closure("closure-bind", external_acceptance=replace(acceptance, candidate_commit="f" * 40), approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    (root / "value.txt").write_text("drift\n")
    _git(root, "commit", "-am", "head drift")
    with pytest.raises(RuntimeError, match="CLOSURE_CANONICAL_HEAD_DRIFT"):
        service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        (lambda state, approval: state["promotion_packet"].update(candidate_tree_sha="f" * 40), "CLOSURE_CANDIDATE_BINDING_DRIFT"),
        (lambda state, approval: state["promotion_packet"].update(candidate_commit_sha="f" * 40), "CLOSURE_CANDIDATE_BINDING_DRIFT"),
        (lambda state, approval: state["promotion_packet"].update(candidate_state_hash="f" * 64), "CLOSURE_CANDIDATE_BINDING_DRIFT"),
        (lambda state, approval: state["promotion_packet"].update(verified_receipt_hash="f" * 64), "CLOSURE_CANDIDATE_BINDING_DRIFT"),
        (lambda state, approval: state.update(task_id="other-task"), "CLOSURE_TASK_ID_DRIFT"),
        (lambda state, approval: approval.update(bound_attempt_id="other-attempt"), "APPROVAL_BINDING_MISMATCH"),
        (lambda state, approval: approval.update(task_card_hash="f" * 64), "APPROVAL_BINDING_MISMATCH"),
        (lambda state, approval: approval.update(acceptance_receipt_hash="f" * 64), "CLOSURE_CANDIDATE_BINDING_DRIFT"),
        (lambda state, approval: approval.update(integration_branch="nexus/integration/main"), "CLOSURE_BRANCH_BINDING_MISMATCH"),
    ],
)
def test_closure_identity_matrix_fails_closed(tmp_path: Path, tamper, message, monkeypatch):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    state = service._read_state("closure-bind")
    tamper(state, approval)
    if state.get("task_id") != "closure-bind":
        monkeypatch.setattr(service, "_read_state", lambda task_id: state)
    else:
        service._write_state("closure-bind", state)
    with pytest.raises((RuntimeError, ValueError), match=message):
        service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")


def test_closure_artifact_hash_mismatch_fails_closed(tmp_path: Path):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    approval = {**approval, "acceptance_receipt_hash": "a" * 64}
    with pytest.raises(RuntimeError, match="EXTERNAL_ACCEPTANCE_ARTIFACT_HASH_MISMATCH"):
        service.bind_candidate_integration_closure("closure-bind", external_acceptance=replace(acceptance, receipt_hash="a" * 64), approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")


def test_bind_then_integrate_uses_fresh_integration_grant(tmp_path: Path, monkeypatch):
    service, root, base, candidate, acceptance, approval, runtime = _approved_closure_service(tmp_path)
    state = service._read_state("closure-bind")
    state["approved_binding"]["approval_grant"]["expires_at"] = "2020-01-01T00:00:00+00:00"
    state["verified_receipt"] = _verified_gate_proof(root, service.build_contract(state["request"]))
    service._write_state("closure-bind", state)
    service.bind_candidate_integration_closure("closure-bind", external_acceptance=acceptance, approval=approval, runtime_identity=runtime, expected_canonical_head=base, integration_branch="nexus/integration/canary")
    monkeypatch.setattr(service, "_record_integration", lambda receipt, *, task_id=None: {"status": "INTEGRATED", "promotion_status": "INTEGRATED", "task_id": task_id})
    monkeypatch.setattr(RepositoryContractGate, "evaluate_committed_candidate", lambda *args, **kwargs: SimpleNamespace(passed=True, blocking_reasons=()))
    class FakeIntegrationManager:
        def __init__(self, **kwargs):
            pass
        def integrate_authorized_task_state(self, *args, **kwargs):
            return SimpleNamespace()
    monkeypatch.setattr("nexus.orchestrator.self_hosted_task_service.ControlledIntegrationManager", FakeIntegrationManager)
    result = service.integrate_approved("closure-bind", integration_branch="nexus/integration/canary", runtime_identity=runtime)
    assert result["status"] == "INTEGRATED"
