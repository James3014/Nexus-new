from __future__ import annotations

import pytest

from nexus.services.local_heal.claim_delivery_gate import ClaimDeliveryGate
from nexus.services.local_heal.quota_state import QuotaState, BudgetClass


@pytest.fixture
def gate() -> ClaimDeliveryGate:
    return ClaimDeliveryGate()


@pytest.fixture
def valid_payload() -> dict:
    return {
        "verifier_status": "pass",
        "verifier_artifact": "report.txt",
        "source_hash": "abc123",
        "candidate_hash_matches_applied": True,
        "candidate_target_file": "file.py",
        "patch_applied": True,
        "artifact_refs": ["ref1"],
    }


class TestClaimGateQuotaDependent:

    def test_claim_gate_no_quota_state_backward_compat(self, gate, valid_payload):
        decision = gate.validate(valid_payload)
        assert decision.claim_gate_passed is True
        assert "local_only_executed_with_quota" not in decision.reasons

    def test_claim_gate_local_only_executed_with_quota_adds_reason(self, gate, valid_payload):
        payload = {**valid_payload, "route_mode": "LOCAL_ONLY_EXECUTED"}
        quota_state = QuotaState(
            quota_known=True,
            budget_class=BudgetClass.CONSTRAINED,
            cloud_budget_remaining=5,
            local_available=True,
            committee_budget_remaining=10,
            source="env",
            confidence=1.0,
            reason="constraint_test",
        )
        decision = gate.validate(payload, quota_state=quota_state)
        assert "local_only_executed_with_quota" in decision.reasons

    def test_claim_gate_cloud_mode_with_quota_no_extra_reason(self, gate, valid_payload):
        payload = {**valid_payload, "route_mode": "CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY"}
        quota_state = QuotaState(
            quota_known=True,
            budget_class=BudgetClass.CONSTRAINED,
            cloud_budget_remaining=5,
            local_available=True,
            committee_budget_remaining=10,
            source="env",
            confidence=1.0,
            reason="constraint_test",
        )
        decision = gate.validate(payload, quota_state=quota_state)
        assert "local_only_executed_with_quota" not in decision.reasons

    def test_claim_gate_existing_8_blockers_unchanged(self, gate):
        payload = {
            "verifier_status": "fail",
            "verifier_artifact": "",
            "source_hash": "",
            "candidate_hash_matches_applied": False,
            "candidate_target_file": "",
            "patch_applied": False,
            "artifact_refs": [],
            "route_mode": "LOCAL_ONLY_EXECUTED",
        }
        quota_state = QuotaState(
            quota_known=True,
            budget_class=BudgetClass.HEALTHY,
            cloud_budget_remaining=50,
            local_available=True,
            committee_budget_remaining=10,
            source="env",
            confidence=1.0,
            reason="test",
        )
        decision = gate.validate(payload, quota_state=quota_state)
        assert decision.claim_gate_passed is False
        for r in ("verifier_not_passed", "missing_verifier_artifact", "missing_source_hash"):
            assert r in decision.reasons
        assert "local_only_executed_with_quota" in decision.reasons
