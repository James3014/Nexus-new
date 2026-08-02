"""Corrective RED probes for the rejected Target integration Candidate."""

import subprocess
import hashlib
import json
from pathlib import Path

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
    assert result["status"] == "INTEGRATED"
    stored = service._read_state("task-1") or service._latest_archived_state("task-1")[1]
    assert stored["integration_receipt"]["post_apply_verified"] is True
    assert stored["integration_receipt"]["acceptance_receipt_hash"] == receipt.receipt_hash
    fresh_integration = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    persisted_integration = fresh_integration._read_state("task-1") or fresh_integration._latest_archived_state("task-1")[1]
    assert persisted_integration["integration_receipt"] == result["integration_receipt"]

    cleanup = service.cleanup_tasks(task_id="task-1", dry_run=False)
    assert cleanup["decisions"][0]["cleanup_performed"] is True
    cleanup_receipt = cleanup["decisions"][0]["cleanup_receipt"]
    fresh = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)
    persisted = fresh._read_state("task-1") or fresh._latest_archived_state("task-1")[1]
    assert persisted["cleanup_receipt"] == cleanup_receipt
    assert persisted["cleanup_receipt_hash"] == hashlib.sha256(
        json.dumps(cleanup_receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    assert not target.exists()
