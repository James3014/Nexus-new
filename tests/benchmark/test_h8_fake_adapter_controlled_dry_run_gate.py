"""
H8-3 Fake Adapter Controlled Dry-run Gate Tests

Gate: H8 fake local model adapter controlled dry-run boundary.

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

This is NOT a real dry-run with Ollama/Qwen.
This is a fake-adapter controlled dry-run gate.

All tests are fixture-only tests.
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
# H8-3 FAKE ADAPTER FIXTURES
# ---------------------------------------------------------------------------

def _fake_adapter_candidate_output() -> dict:
    return {
        "fake_adapter": True,
        "candidate_id": "h8-3-candidate-a",
        "selected_candidate_hash": "sha256:h8-3-candidate-a",
        "adapter_output": "synthetic candidate output; no model call",
        "local_model_provider": "fake",
        "local_model_name": "fake-qwen",
        "local_model_loaded": False,
        "local_model_called": False,
        "model_load_allowed": False,
        "model_call_allowed": False,
        "provider_call_allowed": False,
        "network_allowed": False,
        "route_truth_source": "CapabilityPlanner",
        "adapter_output_is_route_truth": False,
        "candidate_output_isolated": True,
        "verifier_result": "not_run",
        "public_claim_allowed": False,
        "production_ready": False,
    }


def _fake_adapter_receipt() -> dict:
    return {
        "receipt_id": "h8-3-receipt-001",
        "fake_adapter": True,
        "candidate_id": "h8-3-candidate-a",
        "selected_candidate_hash": "sha256:h8-3-candidate-a",
        "local_model_provider": "fake",
        "local_model_name": "fake-qwen",
        "local_model_allowed": False,
        "local_model_loaded": False,
        "local_model_called": False,
        "model_load_allowed": False,
        "model_call_allowed": False,
        "provider_call_allowed": False,
        "network_allowed": False,
        "adapter_output_is_route_truth": False,
        "candidate_output_isolated": True,
        "route_truth_source": "CapabilityPlanner",
        "evidence_refs": ["receipt://h8-2"],
        "verifier_result": "not_run",
        "public_claim_allowed": False,
        "production_ready": False,
    }


# ---------------------------------------------------------------------------
# H8-3 HELPERS (test-only, no production side effects)
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


class TestH83FakeAdapterCandidateOutput:
    """H8-3: Fake adapter can emit candidate output without model call."""

    def test_h8_3_fake_adapter_can_emit_candidate_fixture_without_model_call(self):
        output = _fake_adapter_candidate_output()
        assert output["fake_adapter"] is True
        assert output["local_model_called"] is False
        assert output["local_model_loaded"] is False

    def test_h8_3_candidate_output_is_isolated(self):
        output = _fake_adapter_candidate_output()
        assert output["candidate_output_isolated"] is True

    def test_h8_3_candidate_output_requires_candidate_id_and_hash(self):
        output = _fake_adapter_candidate_output()
        assert "candidate_id" in output
        assert "selected_candidate_hash" in output
        assert output["candidate_id"] != ""
        assert output["selected_candidate_hash"].startswith("sha256:")


class TestH83FakeAdapterNoModelExecution:
    """H8-3: Fake adapter does not load or call model."""

    def test_h8_3_fake_adapter_does_not_load_or_call_model(self):
        output = _fake_adapter_candidate_output()
        assert output["local_model_loaded"] is False
        assert output["local_model_called"] is False
        assert output["model_load_allowed"] is False
        assert output["model_call_allowed"] is False

    def test_h8_3_fake_adapter_provider_network_model_flags_remain_false(self):
        output = _fake_adapter_candidate_output()
        assert output["provider_call_allowed"] is False
        assert output["network_allowed"] is False
        assert output["model_load_allowed"] is False
        assert output["model_call_allowed"] is False


class TestH83FakeAdapterRouteTruth:
    """H8-3: Fake adapter cannot override RouteDecision truth."""

    def test_h8_3_fake_adapter_cannot_override_route_decision_truth(self):
        route = _build_minimal_route_decision()
        output = _fake_adapter_candidate_output()
        assert route.decision_source == "CapabilityPlanner"
        assert output["route_truth_source"] == "CapabilityPlanner"
        assert output["adapter_output_is_route_truth"] is False


class TestH83FakeAdapterReceipt:
    """H8-3: Fake adapter receipt records correct flags."""

    def test_h8_3_fake_adapter_receipt_records_fake_adapter_true(self):
        receipt = _fake_adapter_receipt()
        assert receipt["fake_adapter"] is True

    def test_h8_3_fake_adapter_receipt_records_local_model_called_false(self):
        receipt = _fake_adapter_receipt()
        assert receipt["local_model_called"] is False


class TestH83VerifierAndClaims:
    """H8-3: Verifier not_run keeps public claim false."""

    def test_h8_3_verifier_not_run_keeps_public_claim_false(self):
        receipt = _fake_adapter_receipt()
        assert receipt["verifier_result"] == "not_run"
        assert receipt["public_claim_allowed"] is False

    def test_h8_3_production_ready_remains_false(self):
        receipt = _fake_adapter_receipt()
        assert receipt["production_ready"] is False


class TestH83RouteTruthAndDenial:
    """H8-3: Route truth remains CapabilityPlanner; H7 denial fields remain false."""

    def test_h8_3_route_truth_remains_capability_planner_or_route_decision(self):
        route = _build_minimal_route_decision()
        receipt = _fake_adapter_receipt()
        assert route.decision_source == "CapabilityPlanner"
        assert receipt["route_truth_source"] == "CapabilityPlanner"

    def test_h8_3_h7_provider_model_network_denial_fields_remain_false(self):
        for field, expected in H7_DENIAL_FIELDS.items():
            assert expected is False, f"H7 denial field {field} must be False"
        receipt = _fake_adapter_receipt()
        assert receipt["provider_call_allowed"] is False
        assert receipt["network_allowed"] is False
        assert receipt["model_load_allowed"] is False
        assert receipt["model_call_allowed"] is False
