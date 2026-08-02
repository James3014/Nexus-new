from __future__ import annotations

import pytest

from nexus.contracts.unified_runtime_receipt import (
    build_runtime_development_mapping,
    validate_runtime_development_mapping,
)


def test_runtime_and_development_share_identity_without_collapsing_claims():
    mapping = build_runtime_development_mapping(
        task_id="task-1",
        attempt_id="attempt-1",
        action_id="action-1",
        runtime_terminal_state="AUDIT_VERIFIED",
        development_status="VERIFIED",
        runtime_success=True,
        candidate_status="PENDING_HUMAN_APPROVAL",
    )
    assert mapping["runtime"]["run_attempt_id"] == "attempt-1"
    assert mapping["development"]["action_id"] == "action-1"
    assert mapping["claim_boundaries"]["runtime_success_implies_candidate_acceptance"] is False
    assert mapping["development"]["candidate_accepted"] is False
    validate_runtime_development_mapping(mapping)


def test_integration_requires_separate_candidate_acceptance():
    with pytest.raises(ValueError, match="INTEGRATION_REQUIRES_ACCEPTANCE"):
        build_runtime_development_mapping(
            task_id="task-1",
            attempt_id="attempt-1",
            action_id="action-1",
            runtime_terminal_state="COMPLETE",
            development_status="INTEGRATED",
            runtime_success=True,
            integrated=True,
            candidate_accepted=False,
        )


def test_identity_drift_is_rejected():
    mapping = build_runtime_development_mapping(
        task_id="task-1",
        attempt_id="attempt-1",
        action_id="action-1",
        runtime_terminal_state="FAILED",
        development_status="FINAL_BLOCK",
        runtime_success=False,
    )
    mapping["runtime"]["entry_action_id"] = "action-drift"
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH:action_id"):
        validate_runtime_development_mapping(mapping)
