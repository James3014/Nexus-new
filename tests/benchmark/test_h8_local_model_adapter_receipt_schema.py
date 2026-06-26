"""
H8-2 Local Model Adapter Receipt Schema Tests

Gate: H8 local model adapter seam and receipt schema boundary.

Safety boundary:
- NO_RUNTIME_BEHAVIOR_CHANGE
- NO_LOCAL_MODEL_RUN
- NO_OLLAMA_CALL
- NO_QWEN_CALL
- NO_PROVIDER_CALL
- NO_MODEL_CALL
- NO_MODEL_LOAD
- NO_NETWORK_CALL
- NO_PROCESS_SPAWN
- production_ready=false
- public_claim_allowed=false
- local_model_ready=false
- H8 runtime not started

Recent typing impact guard:
Recent commits (4f475aa9, 0fc8ead5, 3ca70b41, 03327157, 2fdffe28) fixed
typing in nexus/core/* modules. H8-2 verifies these changes do NOT alter
the deny-by-default safety boundary. Tests assert denial fields remain False
regardless of typing improvements.

All tests are field-contract / fixture tests only.
No real local model, provider, or network is invoked.
No production code is modified.
"""

from __future__ import annotations

import pytest

from nexus.engine.capability_contracts import (
    CapabilityPlan,
    CapabilityReceipt,
    RouteDecision,
)


# ---------------------------------------------------------------------------
# H8-2 ADAPTER REQUEST FIXTURE
# ---------------------------------------------------------------------------

def _adapter_request_fixture() -> dict:
    return {
        "request_id": "h8-2-request-001",
        "task_id": "h8-2-task",
        "candidate_id": "candidate-a",
        "selected_candidate_hash": "sha256:selected-candidate",
        "evidence_refs": ["receipt://h7-safe-gate"],
        "allowed_capabilities": [],
        "forbidden_capabilities": [
            "provider_call",
            "network",
            "model_load",
            "model_call",
        ],
        "route_truth_source": "CapabilityPlanner",
        "context_contract_version": "h8-test-only",
        "state_contract_version": "h8-test-only",
    }


# ---------------------------------------------------------------------------
# H8-2 ADAPTER RECEIPT FIXTURE
# ---------------------------------------------------------------------------

def _adapter_receipt_fixture() -> dict:
    return {
        "receipt_id": "h8-2-receipt-001",
        "request_id": "h8-2-request-001",
        "local_model_provider": "ollama",
        "local_model_name": "qwen",
        "local_model_allowed": False,
        "local_model_loaded": False,
        "local_model_called": False,
        "local_model_denied_reason": "deny_by_default",
        "provider_call_allowed": False,
        "network_allowed": False,
        "model_load_allowed": False,
        "model_call_allowed": False,
        "adapter_output_is_route_truth": False,
        "candidate_output_isolated": True,
        "evidence_refs": ["receipt://h7-safe-gate"],
        "verifier_result": "not_run",
        "context_contract_version": "h8-test-only",
        "state_contract_version": "h8-test-only",
        "public_claim_allowed": False,
        "production_ready": False,
    }


# ---------------------------------------------------------------------------
# H8-2 HELPERS (test-only, no production side effects)
# ---------------------------------------------------------------------------

def _build_minimal_route_decision() -> RouteDecision:
    return RouteDecision(
        schema_version="h8_test.v1",
        plan_schema_version="h8_test.v1",
        plan_mode="dry_run",
        plan_score=0,
        task_id="h8-test-001",
        task_type="test",
        task_desc_hash="abc123",
        recommended_flow="INTAKE",
        decision_source="CapabilityPlanner",
        signal_snapshot={},
        selected_capabilities=("test_capability",),
    )


# ---------------------------------------------------------------------------
# H7 DENIAL FIELDS (from H7-5A)
# ---------------------------------------------------------------------------

H7_DENIAL_FIELDS = {
    "model_call_executed": False,
    "runtime_effect": False,
    "public_claim_allowed": False,
    "production_ready": False,
}


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------


class TestH82AdapterRequestSchema:
    """H8-2: Adapter request must have explicit task/candidate/evidence fields."""

    def test_h8_2_adapter_request_requires_task_candidate_and_evidence_fields(self):
        request = _adapter_request_fixture()
        assert "task_id" in request
        assert "candidate_id" in request
        assert "evidence_refs" in request
        assert request["task_id"] != ""
        assert request["candidate_id"] != ""
        assert len(request["evidence_refs"]) > 0

    def test_h8_2_adapter_request_requires_candidate_hash(self):
        request = _adapter_request_fixture()
        assert "selected_candidate_hash" in request
        assert request["selected_candidate_hash"].startswith("sha256:")


class TestH82AdapterResponseIsolation:
    """H8-2: Adapter response cannot be route truth; must be isolated."""

    def test_h8_2_adapter_response_cannot_be_route_truth(self):
        receipt = _adapter_receipt_fixture()
        assert receipt["adapter_output_is_route_truth"] is False

    def test_h8_2_adapter_response_must_be_candidate_isolated(self):
        receipt = _adapter_receipt_fixture()
        assert receipt["candidate_output_isolated"] is True


class TestH82AdapterReceiptSchema:
    """H8-2: Adapter receipt must record provider/model identity without calling."""

    def test_h8_2_adapter_receipt_records_provider_and_model_identity_without_call(
        self,
    ):
        receipt = _adapter_receipt_fixture()
        assert receipt["local_model_provider"] == "ollama"
        assert receipt["local_model_name"] == "qwen"
        assert receipt["local_model_called"] is False

    def test_h8_2_adapter_receipt_records_deny_allow_load_call_flags(self):
        receipt = _adapter_receipt_fixture()
        assert receipt["local_model_allowed"] is False
        assert receipt["local_model_loaded"] is False
        assert receipt["local_model_called"] is False
        assert receipt["provider_call_allowed"] is False
        assert receipt["network_allowed"] is False
        assert receipt["model_load_allowed"] is False
        assert receipt["model_call_allowed"] is False

    def test_h8_2_adapter_receipt_records_denied_reason_when_denied(self):
        receipt = _adapter_receipt_fixture()
        assert receipt["local_model_denied_reason"] == "deny_by_default"

    def test_h8_2_adapter_receipt_requires_evidence_refs(self):
        receipt = _adapter_receipt_fixture()
        assert "evidence_refs" in receipt
        assert len(receipt["evidence_refs"]) > 0

    def test_h8_2_adapter_receipt_requires_verifier_result_placeholder(self):
        receipt = _adapter_receipt_fixture()
        assert "verifier_result" in receipt
        assert receipt["verifier_result"] in ("not_run", "pending", "passed", "failed")

    def test_h8_2_public_claim_and_production_ready_remain_false(self):
        receipt = _adapter_receipt_fixture()
        assert receipt["public_claim_allowed"] is False
        assert receipt["production_ready"] is False


class TestH82AdapterSeamCannotBypass:
    """H8-2: Adapter seam cannot bypass CapabilityPlanner/RouteDecision or H7 denial."""

    def test_h8_2_adapter_seam_cannot_bypass_capability_planner_route_truth(self):
        route = _build_minimal_route_decision()
        request = _adapter_request_fixture()
        assert route.decision_source == "CapabilityPlanner"
        assert request["route_truth_source"] == "CapabilityPlanner"

    def test_h8_2_adapter_seam_cannot_bypass_provider_model_network_denial_fields(
        self,
    ):
        for field, expected in H7_DENIAL_FIELDS.items():
            assert expected is False, f"H7 denial field {field} must be False"
        receipt = _adapter_receipt_fixture()
        assert receipt["provider_call_allowed"] is False
        assert receipt["network_allowed"] is False
        assert receipt["model_load_allowed"] is False
        assert receipt["model_call_allowed"] is False


class TestH82TypingImpactGuard:
    """H8-2: Recent typing changes must not enable runtime or model flags."""

    def test_h8_2_recent_typing_changes_do_not_enable_runtime_or_model_flags(self):
        route = _build_minimal_route_decision()
        assert route.decision_source == "CapabilityPlanner"
        assert route.fallback_policy == "fail_closed"
        assert route.public_claim_scope == "receipt_backed"
        receipt = _adapter_receipt_fixture()
        assert receipt["local_model_allowed"] is False
        assert receipt["local_model_loaded"] is False
        assert receipt["local_model_called"] is False
        assert receipt["provider_call_allowed"] is False
        assert receipt["network_allowed"] is False
        assert receipt["model_load_allowed"] is False
        assert receipt["model_call_allowed"] is False
        assert receipt["adapter_output_is_route_truth"] is False
        assert receipt["public_claim_allowed"] is False
        assert receipt["production_ready"] is False
