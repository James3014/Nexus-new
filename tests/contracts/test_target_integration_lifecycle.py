from nexus.contracts.target_integration_lifecycle import (
    CleanupDecision,
    ExternalAcceptanceReceipt,
    IntegrationAuthorizationEnvelope,
    TargetResolutionMode,
)


SHA = "a" * 40
HASH = "b" * 64


def test_contracts_preserve_target_reuse_and_external_acceptance_boundary():
    from nexus.orchestrator.target_integration_lifecycle import TargetIntegrationLifecycle

    reused = TargetIntegrationLifecycle.resolve_target(
        task_id="task-1", campaign_id="campaign", attempt_id="attempt-2", base_revision=SHA,
        existing_targets=[{
            "task_id": "task-1", "campaign_id": "campaign", "target_id": "target-1",
            "target_path": "/tmp/target-1", "target_branch": "nexus/task/task-1",
            "base_revision": SHA, "dirty": False, "untracked": False,
        }],
    )
    assert reused.mode is TargetResolutionMode.REUSE_EXISTING_TARGET
    assert reused.target_id == "target-1"
    assert reused.attempt_id == "attempt-2"

    blocked = TargetIntegrationLifecycle.resolve_target(
        task_id="task-1", campaign_id="campaign", attempt_id="attempt-3", base_revision=SHA,
        existing_targets=[{
            "task_id": "task-1", "campaign_id": "campaign", "target_id": "target-1",
            "target_path": "/tmp/target-1", "target_branch": "nexus/task/task-1",
            "base_revision": SHA, "dirty": True,
        }],
    )
    assert blocked.mode is TargetResolutionMode.BLOCK

    created = TargetIntegrationLifecycle.resolve_target(
        task_id="task-2", campaign_id="campaign", attempt_id="attempt-1", base_revision=SHA,
        existing_targets=[], requested_target_path="/tmp/target-2",
    )
    assert created.mode is TargetResolutionMode.CREATE_ISOLATED_TARGET
    assert created.target_id != reused.target_id

    unowned = TargetIntegrationLifecycle.resolve_target(
        task_id="task-2", campaign_id="campaign", attempt_id="attempt-1", base_revision=SHA,
        existing_targets=[{
            "target_id": "target-1", "target_path": "/tmp/target-2",
            "target_branch": "nexus/task/task-1", "owner_task_id": "other-task",
            "campaign_id": "campaign", "base_revision": SHA,
        }], requested_target_path="/tmp/target-2",
    )
    assert unowned.mode is TargetResolutionMode.BLOCK

    pending = TargetIntegrationLifecycle.accept_candidate(
        task_id="task-1", attempt_id="attempt-1", candidate_commit=SHA,
        external_receipt=None, implementer_output={"accepted": True},
    )
    assert pending["accepted"] is False
    assert pending["disposition"] == "PENDING_EXTERNAL_ACCEPTANCE"


def test_authorization_and_cleanup_fail_closed_on_drift():
    from nexus.orchestrator.target_integration_lifecycle import TargetIntegrationLifecycle

    receipt = ExternalAcceptanceReceipt(
        schema="nexus.external_acceptance_receipt.v1", task_id="task-1",
        attempt_id="attempt-1", candidate_commit=SHA, receipt_hash=HASH,
        reviewer_id="reviewer", passed=True, verifier_artifact="artifact",
    )
    preview = TargetIntegrationLifecycle.build_preview(
        task_id="task-1", target_id="target-1", candidate_commit=SHA,
        acceptance=receipt, canonical_branch="main", expected_canonical_head=SHA,
        verification_commands=(), cleanup_target_id="target-1", rollback="reset staging",
    )
    authorization = TargetIntegrationLifecycle.authorize(
        task_id="task-1", campaign_id="campaign", task_card_hash=HASH,
        candidate_commit=SHA, candidate_receipt_hash=HASH, acceptance_receipt_hash=HASH,
        canonical_root="/tmp/repo", canonical_branch="main",
        expected_canonical_head=SHA, canonical_dirty_baseline=HASH, preview=preview,
        cleanup_target_id="target-1", cleanup_target_path="/tmp/target-1",
        durable_ref="refs/nexus-candidate-commits/task-1/aaa", rollback="reset staging",
        issued_at="2026-08-02T00:00:00+00:00",
    )
    assert authorization.authorization_hash
    authorization.validate_current(authorization.to_dict())
    current = authorization.to_dict()
    current["candidate_commit"] = "c" * 40
    try:
        authorization.validate_current(current)
    except ValueError as exc:
        assert "authorization drift" in str(exc)
    else:
        raise AssertionError("candidate drift must invalidate authorization")

    retained = TargetIntegrationLifecycle.cleanup_decision(
        task_id="task-1", target_id="target-1", target_owner="task-1",
        target_is_canonical=False, reviewer_worktree=False, dirty=True,
        untracked=False, active_process=False, accepted=True, integrated=True,
        canonical_contains_result=True, durable_ref_verified=True,
        receipts_complete=True, unique_unprotected_commits=False,
    )
    assert retained.decision == "RETAIN"
    assert "Target has tracked changes" in retained.reasons


def test_rejected_candidate_reuses_same_target_with_new_attempt():
    from nexus.orchestrator.target_integration_lifecycle import TargetIntegrationLifecycle

    first = TargetIntegrationLifecycle.resolve_target(
        task_id="task-1", campaign_id="campaign", attempt_id="attempt-1", base_revision=SHA,
        existing_targets=[{
            "task_id": "task-1", "campaign_id": "campaign", "target_id": "target-1",
            "target_path": "/tmp/target-1", "target_branch": "nexus/task/task-1",
            "base_revision": SHA, "dirty": False, "untracked": False,
        }],
    )
    retry = TargetIntegrationLifecycle.resolve_target(
        task_id="task-1", campaign_id="campaign", attempt_id="attempt-2", base_revision=SHA,
        existing_targets=[{**first.to_dict(), "status": "REJECTED"}],
    )
    assert retry.reused is True
    assert retry.target_id == first.target_id
    assert retry.attempt_id != first.attempt_id
