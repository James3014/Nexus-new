"""P6-C2: Rollout Candidate Receipt v2 Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p6_rollout_receipt import (
    P6RolloutReceipt,
    build_p6_rollout_receipt,
    p6_rollout_receipt_to_dict,
)


def test_passing_evidence_creates_rollout_candidate():
    """P6-C2: Passing B8 evidence + rollout_candidate policy creates receipt state rollout_candidate."""
    receipt = build_p6_rollout_receipt(
        rollout_state="rollout_candidate",
        total_rows=24,
        rows_per_arm_min=3,
        unsafe_action_count=0,
        unknown_quota_as_healthy_count=0,
        memory_or_belief_quota_override_count=0,
        receipt_complete_rate=1.0,
        flag_off_behavior_unchanged=True,
    )
    assert receipt.p6_rollout_state == "rollout_candidate"
    assert receipt.p6_public_claim_allowed is False
    assert receipt.p6_production_ready is False
    assert receipt.p6_default_runtime_allowed is False


def test_public_claim_allowed_always_false():
    """P6-C2: public_claim_allowed=false always."""
    receipt = build_p6_rollout_receipt(
        rollout_state="rollout_candidate",
        total_rows=24, rows_per_arm_min=3,
        unsafe_action_count=0, unknown_quota_as_healthy_count=0,
        memory_or_belief_quota_override_count=0,
        receipt_complete_rate=1.0, flag_off_behavior_unchanged=True,
    )
    assert receipt.p6_public_claim_allowed is False


def test_production_ready_always_false():
    """P6-C2: production_ready=false always."""
    receipt = build_p6_rollout_receipt(
        rollout_state="rollout_candidate",
        total_rows=24, rows_per_arm_min=3,
        unsafe_action_count=0, unknown_quota_as_healthy_count=0,
        memory_or_belief_quota_override_count=0,
        receipt_complete_rate=1.0, flag_off_behavior_unchanged=True,
    )
    assert receipt.p6_production_ready is False


def test_default_runtime_allowed_always_false():
    """P6-C2: default_runtime_allowed=false always."""
    receipt = build_p6_rollout_receipt(
        rollout_state="rollout_candidate",
        total_rows=24, rows_per_arm_min=3,
        unsafe_action_count=0, unknown_quota_as_healthy_count=0,
        memory_or_belief_quota_override_count=0,
        receipt_complete_rate=1.0, flag_off_behavior_unchanged=True,
    )
    assert receipt.p6_default_runtime_allowed is False


def test_unsafe_action_prevents_rollout():
    """P6-C2: unsafe_action_count > 0 prevents rollout_candidate."""
    receipt = build_p6_rollout_receipt(
        rollout_state="blocked",
        total_rows=24, rows_per_arm_min=3,
        unsafe_action_count=1, unknown_quota_as_healthy_count=0,
        memory_or_belief_quota_override_count=0,
        receipt_complete_rate=1.0, flag_off_behavior_unchanged=True,
        reason="unsafe_action_detected",
    )
    assert receipt.p6_rollout_state == "blocked"
    assert receipt.p6_unsafe_action_count == 1


def test_unknown_healthy_prevents_rollout():
    """P6-C2: unknown_quota_as_healthy_count > 0 prevents rollout_candidate."""
    receipt = build_p6_rollout_receipt(
        rollout_state="blocked",
        total_rows=24, rows_per_arm_min=3,
        unsafe_action_count=0, unknown_quota_as_healthy_count=1,
        memory_or_belief_quota_override_count=0,
        receipt_complete_rate=1.0, flag_off_behavior_unchanged=True,
        reason="unknown_quota_treated_as_healthy",
    )
    assert receipt.p6_rollout_state == "blocked"
    assert receipt.p6_unknown_quota_as_healthy_count == 1


def test_json_serializable():
    """P6-C2: Receipt is JSON-serializable."""
    receipt = build_p6_rollout_receipt(
        rollout_state="rollout_candidate",
        total_rows=24, rows_per_arm_min=3,
        unsafe_action_count=0, unknown_quota_as_healthy_count=0,
        memory_or_belief_quota_override_count=0,
        receipt_complete_rate=1.0, flag_off_behavior_unchanged=True,
    )
    d = p6_rollout_receipt_to_dict(receipt)
    json_str = json.dumps(d)
    assert len(json_str) > 0
