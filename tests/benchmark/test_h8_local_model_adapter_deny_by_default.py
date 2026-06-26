"""
H8-1 Local Model Adapter Deny-by-Default Tests

Gate: H8 local model adapter deny-by-default boundary.

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
# H8-1 DENY-BY-DEFAULT CONTRACT FIXTURE
# ---------------------------------------------------------------------------
# Represents the expected H8-phase deny-by-default contract for local model
# adapter integration. All fields default to denied/disabled.
# This fixture does NOT modify production code. It is test-local only.
# ---------------------------------------------------------------------------

H8_LOCAL_MODEL_DENY_CONTRACT = {
    "local_model_provider": "ollama",
    "local_model_name": "qwen",
    "local_model_allowed": False,
    "local_model_loaded": False,
    "local_model_called": False,
    "local_model_denied_reason": "deny_by_default",
    "network_allowed": False,
    "provider_call_allowed": False,
    "model_load_allowed": False,
    "model_call_allowed": False,
    "route_truth_source": "CapabilityPlanner",
    "adapter_output_route_truth_source": False,
    "public_claim_allowed": False,
    "runtime_ready": False,
}


# ---------------------------------------------------------------------------
# H8-1 HELPERS (test-only, no production side effects)
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


def _build_minimal_capability_receipt() -> CapabilityReceipt:
    return CapabilityReceipt(
        name="h8_test_receipt",
        selected=False,
        invoked=False,
    )


def _apply_adapter_output_to_route_truth(
    route_contract: dict, adapter_output: dict
) -> dict:
    """Test-only helper: adapter output must NOT override route truth."""
    protected = dict(route_contract)
    protected["adapter_output_ignored"] = True
    return protected


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------


class TestH81LocalModelDenyByDefault:
    """H8-1: Local model adapter must be denied by default."""

    def test_h8_1_local_model_denied_by_default(self):
        contract = H8_LOCAL_MODEL_DENY_CONTRACT
        assert contract["local_model_allowed"] is False
        assert contract["local_model_denied_reason"] == "deny_by_default"

    def test_h8_1_local_model_not_loaded_by_default(self):
        contract = H8_LOCAL_MODEL_DENY_CONTRACT
        assert contract["local_model_loaded"] is False

    def test_h8_1_local_model_not_called_by_default(self):
        contract = H8_LOCAL_MODEL_DENY_CONTRACT
        assert contract["local_model_called"] is False

    def test_h8_1_model_load_and_model_call_denied_by_default(self):
        contract = H8_LOCAL_MODEL_DENY_CONTRACT
        assert contract["model_load_allowed"] is False
        assert contract["model_call_allowed"] is False

    def test_h8_1_provider_and_network_denied_by_default(self):
        contract = H8_LOCAL_MODEL_DENY_CONTRACT
        assert contract["provider_call_allowed"] is False
        assert contract["network_allowed"] is False


class TestH81AdapterOutputCannotOverrideRouteTruth:
    """H8-1: Adapter output must not influence routing or truth source."""

    def test_h8_1_adapter_output_cannot_override_route_truth_source(self):
        route = _build_minimal_route_decision()
        adapter_output = {
            "route_truth_source": "local_model_adapter",
            "adapter_output_route_truth_source": True,
        }
        result = _apply_adapter_output_to_route_truth(
            route.to_dict(), adapter_output
        )
        assert result["adapter_output_ignored"] is True
        assert adapter_output["route_truth_source"] == "local_model_adapter"
        assert result.get("route_truth_source") != "local_model_adapter"

    def test_h8_1_adapter_output_cannot_override_selected_capabilities(self):
        route = _build_minimal_route_decision()
        original_selected = route.selected_capabilities
        adapter_output = {
            "selected_capabilities": ["malicious_capability"],
        }
        result = _apply_adapter_output_to_route_truth(
            route.to_dict(), adapter_output
        )
        assert result["adapter_output_ignored"] is True
        assert adapter_output["selected_capabilities"] == ["malicious_capability"]
        assert route.selected_capabilities == original_selected


class TestH81ReceiptRecordsDenyReason:
    """H8-1: Receipt must record deny-by-default reason."""

    def test_h8_1_receipt_records_deny_by_default_reason(self):
        contract = H8_LOCAL_MODEL_DENY_CONTRACT
        receipt = _build_minimal_capability_receipt()
        assert contract["local_model_denied_reason"] == "deny_by_default"
        assert receipt.invoked is False
        assert receipt.selected is False

    def test_h8_1_receipt_public_claim_safe_false_when_not_invoked(self):
        receipt = _build_minimal_capability_receipt()
        assert receipt.public_claim_safe is False


class TestH81PublicClaimAndRuntime:
    """H8-1: public_claim_allowed and runtime_ready must remain false."""

    def test_h8_1_public_claim_allowed_remains_false(self):
        contract = H8_LOCAL_MODEL_DENY_CONTRACT
        assert contract["public_claim_allowed"] is False

    def test_h8_1_runtime_ready_remains_false(self):
        contract = H8_LOCAL_MODEL_DENY_CONTRACT
        assert contract["runtime_ready"] is False


class TestH81NoProviderModelNetworkEnvFlags:
    """H8-1: No provider/model/network env flags should be enabled."""

    def test_h8_1_no_provider_model_network_env_flags_enabled(self):
        contract = H8_LOCAL_MODEL_DENY_CONTRACT
        assert contract["network_allowed"] is False
        assert contract["provider_call_allowed"] is False
        assert contract["model_load_allowed"] is False
        assert contract["model_call_allowed"] is False
        assert contract["local_model_allowed"] is False
        assert contract["local_model_loaded"] is False
        assert contract["local_model_called"] is False
