from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.p3_p6_advisory_consumer import (
    P3P6AdvisoryConsumptionResult,
    compute_p3_p6_advisory_consumption,
    p3_p6_advisory_to_dict,
)


# ============================================================
# O6-1: valid P6 handoff consumed as advisory
# ============================================================


def test_valid_p6_handoff_advisory():
    result = compute_p3_p6_advisory_consumption(
        p6_handoff={"recommendation": "reduce_candidates", "candidate_budget": "5"}
    )
    assert result.p6_handoff_present is True
    assert result.p6_recommendation == "reduce_candidates"
    assert result.p3_may_record_p6_receipt_ref is True
    assert result.p3_topology_override_allowed is False


# ============================================================
# O6-2: missing P6 handoff is safe no-op
# ============================================================


def test_missing_p6_handoff_noop():
    result = compute_p3_p6_advisory_consumption(p6_handoff=None)
    assert result.p6_handoff_present is False
    assert result.p3_topology_override_allowed is False


# ============================================================
# O6-3: P6 topology override attempt blocks
# ============================================================


def test_p6_topology_override_blocks():
    result = compute_p3_p6_advisory_consumption(
        p6_handoff={"topology_override": True}
    )
    assert "p6_topology_override_attempted" in result.blocked_reasons
    assert result.p3_topology_override_allowed is False


# ============================================================
# O6-4: P6 P4 verifier override attempt blocks
# ============================================================


def test_p6_verifier_override_blocks():
    result = compute_p3_p6_advisory_consumption(
        p6_handoff={"verifier_override": True}
    )
    assert "p6_verifier_override_attempted" in result.blocked_reasons
    assert result.p4_verifier_override_allowed is False


# ============================================================
# O6-5: P6 claim gate override attempt blocks
# ============================================================


def test_p6_claim_gate_override_blocks():
    result = compute_p3_p6_advisory_consumption(
        p6_handoff={"claim_gate_override": True}
    )
    assert "p6_claim_gate_override_attempted" in result.blocked_reasons
    assert result.p4_claim_gate_override_allowed is False


# ============================================================
# O6-6: P6 P5 override attempt blocks
# ============================================================


def test_p6_p5_override_blocks():
    result = compute_p3_p6_advisory_consumption(
        p6_handoff={"p5_override": True}
    )
    assert "p6_p5_override_attempted" in result.blocked_reasons
    assert result.p5_selection_override_allowed is False


# ============================================================
# O6-7: rollback recommendation records fail_closed advisory
# ============================================================


def test_rollback_records_fail_closed():
    result = compute_p3_p6_advisory_consumption(
        p6_handoff={"recommendation": "rollback", "fail_closed": "quota_exceeded"}
    )
    assert result.p6_recommendation == "rollback"
    assert result.fail_closed_advisory == "quota_exceeded"


# ============================================================
# O6-8: p3_runtime_behavior_changed=false always
# ============================================================


def test_runtime_behavior_changed_always_false():
    result = compute_p3_p6_advisory_consumption(
        p6_handoff={"recommendation": "reduce"}
    )
    assert result.p3_runtime_behavior_changed is False


# ============================================================
# O6-9: public_claim_allowed=false always
# ============================================================


def test_public_claim_allowed_always_false():
    result = compute_p3_p6_advisory_consumption(
        p6_handoff={"recommendation": "reduce"}
    )
    assert result.public_claim_allowed is False


# ============================================================
# O6-10: production_ready=false always
# ============================================================


def test_production_ready_always_false():
    result = compute_p3_p6_advisory_consumption(
        p6_handoff={"recommendation": "reduce"}
    )
    assert result.production_ready is False


# ============================================================
# O6-11: solved_allowed=false always
# ============================================================


def test_solved_allowed_always_false():
    result = compute_p3_p6_advisory_consumption(
        p6_handoff={"recommendation": "reduce"}
    )
    assert result.solved_allowed is False


# ============================================================
# O6-12: JSON serialization works
# ============================================================


def test_json_serializable():
    result = compute_p3_p6_advisory_consumption(
        p6_handoff={"recommendation": "reduce"}
    )
    d = p3_p6_advisory_to_dict(result)
    assert isinstance(json.dumps(d), str)


# ============================================================
# O6-13: module does not import P6 runtime hook
# ============================================================


def test_no_p6_runtime_hook_import():
    import nexus.services.local_heal.p3_p6_advisory_consumer as mod
    source = open(mod.__file__).read()
    assert "p6_runtime_hook" not in source
