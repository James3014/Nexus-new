"""P6-B3: DegradationPolicy Receipt Integration Tests."""
from __future__ import annotations

import json
import pytest
from nexus.services.local_heal.quota_state import QuotaState, BudgetClass
from nexus.services.local_heal.degradation_policy import evaluate_degradation_policy
from nexus.services.local_heal.p6_receipt import build_p6_receipt, p6_receipt_to_dict


def _make_receipt(budget_class, local_available=True):
    quota_state = QuotaState(
        quota_known=budget_class != BudgetClass.UNKNOWN,
        budget_class=budget_class,
        cloud_budget_remaining=10 if budget_class == BudgetClass.HEALTHY else 5 if budget_class == BudgetClass.CONSTRAINED else 0,
        local_available=local_available,
        committee_budget_remaining=10 if budget_class == BudgetClass.HEALTHY else 5 if budget_class == BudgetClass.CONSTRAINED else 0,
        source="env",
        confidence=1.0 if budget_class != BudgetClass.UNKNOWN else 0.0,
        reason=budget_class.value,
    )
    decision = evaluate_degradation_policy(quota_state=quota_state, local_available=local_available)
    return build_p6_receipt(quota_state=quota_state, decision=decision)


def test_healthy_receipt():
    """P6-B3: healthy → keep_full_committee receipt."""
    receipt = _make_receipt(BudgetClass.HEALTHY)
    assert receipt.p6_degradation_action == "keep_full_committee"
    assert receipt.p6_cloud_allowed is True
    assert receipt.p6_committee_allowed is True


def test_constrained_receipt():
    """P6-B3: constrained → reduce_candidate_count receipt."""
    receipt = _make_receipt(BudgetClass.CONSTRAINED)
    assert receipt.p6_degradation_action == "reduce_candidate_count"
    assert receipt.p6_candidate_count_limit is not None


def test_exhausted_receipt():
    """P6-B3: exhausted → local_only receipt."""
    receipt = _make_receipt(BudgetClass.EXHAUSTED)
    assert receipt.p6_degradation_action == "local_only"
    assert receipt.p6_cloud_allowed is False


def test_unknown_receipt():
    """P6-B3: unknown → fail_closed receipt."""
    receipt = _make_receipt(BudgetClass.UNKNOWN)
    assert receipt.p6_degradation_action == "fail_closed"
    assert receipt.p6_budget_class == "unknown"


def test_unknown_not_healthy():
    """P6-B3: receipt does not write unknown quota as healthy."""
    receipt = _make_receipt(BudgetClass.UNKNOWN)
    assert receipt.p6_budget_class == "unknown"
    assert receipt.p6_budget_class != "healthy"


def test_memory_cannot_affect_quota():
    """P6-B3: memory/belief cannot change quota action."""
    receipt = _make_receipt(BudgetClass.HEALTHY)
    assert receipt.p6_memory_signal_used_for_quota is False
    assert receipt.p6_belief_signal_used_for_quota is False


def test_verifier_claim_required():
    """P6-B3: verifier and claim gate remain required."""
    receipt = _make_receipt(BudgetClass.HEALTHY)
    assert receipt.p6_verifier_required is True
    assert receipt.p6_claim_gate_required is True


def test_no_public_claim():
    """P6-B3: public_claim_allowed is always false."""
    receipt = _make_receipt(BudgetClass.HEALTHY)
    assert receipt.p6_public_claim_allowed is False


def test_receipt_json_serializable():
    """P6-B3: receipt is JSON-serializable."""
    receipt = _make_receipt(BudgetClass.HEALTHY)
    d = p6_receipt_to_dict(receipt)
    json_str = json.dumps(d)
    assert len(json_str) > 0


def test_runtime_route_mutation_not_allowed():
    """P6-B3: runtime_route_mutation_allowed is always false."""
    receipt = _make_receipt(BudgetClass.HEALTHY)
    assert receipt.p6_runtime_route_mutation_allowed is False
