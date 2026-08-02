from nexus.orchestrator.target_integration_lifecycle import TargetIntegrationLifecycle


def test_receipt_binding_is_caller_persisted_and_round_trips():
    receipt = {"schema": "nexus.integration_receipt.v1", "status": "STAGED", "commit": "a" * 40}
    state = TargetIntegrationLifecycle.bind_receipt({"task_id": "task-1"}, receipt_name="integration_receipt", receipt=receipt)
    assert state["integration_receipt"] == receipt
    assert len(state["integration_receipt_hash"]) == 64
    reloaded = TargetIntegrationLifecycle.bind_receipt({}, receipt_name="integration_receipt", receipt=state["integration_receipt"])
    assert reloaded["integration_receipt"] == state["integration_receipt"]
    assert reloaded["integration_receipt_hash"] == state["integration_receipt_hash"]


def test_cleanup_never_removes_canonical_or_unaccepted_target():
    retained = TargetIntegrationLifecycle.cleanup_decision(
        task_id="task-1", target_id="canonical", target_owner="task-1",
        target_is_canonical=True, reviewer_worktree=False, dirty=False,
        untracked=False, active_process=False, accepted=False, integrated=False,
        canonical_contains_result=False, durable_ref_verified=False,
        receipts_complete=False, unique_unprotected_commits=False,
    )
    result = TargetIntegrationLifecycle.cleanup_target(
        decision=retained, target_path="/tmp/never-remove", canonical_root="/tmp/repo", apply=True,
    )
    assert result["performed"] is False
    assert retained.decision == "RETAIN"
