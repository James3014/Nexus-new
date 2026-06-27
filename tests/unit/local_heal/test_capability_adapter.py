from __future__ import annotations

from nexus.contracts.hybrid_route import RouteMode, Authority, VerifierResult
from nexus.services.local_heal.capability_adapter import (
    LocalHealCapabilityAdapter,
    LocalHealCapabilityRequest,
)


def test_capability_adapter_disabled() -> None:
    request = LocalHealCapabilityRequest(
        task_id="t1",
        problem_statement="fix syntax",
        evidence_refs=("ref1",),
        executor_controls={"enable_local_heal": False, "local_heal_mode": "disabled"},
    )
    response = LocalHealCapabilityAdapter.run(request)
    assert response.task_id == "t1"
    assert response.invoked is False
    assert response.hybrid_route.route_mode == RouteMode.CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY
    assert response.hybrid_route.authority == Authority.TRACE_ONLY
    assert response.hybrid_route.local_model_called is False
    assert response.hybrid_route.verifier_result == VerifierResult.NOT_RUN
    assert response.capability_payload["invoked"] is False
    assert response.capability_payload["adapter_invoked"] is False
    assert response.capability_payload["gate_passed"] is False


def test_capability_adapter_shadow_only_with_evidence() -> None:
    request = LocalHealCapabilityRequest(
        task_id="t2",
        problem_statement="fix syntax",
        evidence_refs=("ref1",),
        executor_controls={"enable_local_heal": True, "local_heal_mode": "shadow_only"},
    )
    response = LocalHealCapabilityAdapter.run(request)
    assert response.invoked is True
    assert response.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert response.hybrid_route.authority == Authority.TRACE_ONLY
    assert response.hybrid_route.local_model_called is False
    assert response.hybrid_route.fallback_block_reason == "shadow_only_no_runtime"
    assert response.hybrid_route.evidence_refs == ("ref1",)
    assert response.capability_payload["invoked"] is False
    assert response.capability_payload["adapter_invoked"] is True
    assert response.capability_payload["gate_passed"] is False


def test_capability_adapter_shadow_only_missing_evidence() -> None:
    request = LocalHealCapabilityRequest(
        task_id="t3",
        problem_statement="fix syntax",
        evidence_refs=(),
        executor_controls={"enable_local_heal": True, "local_heal_mode": "shadow_only"},
    )
    response = LocalHealCapabilityAdapter.run(request)
    assert response.invoked is True
    assert response.hybrid_route.route_mode == RouteMode.LOCAL_ONLY_BLOCKED
    assert "missing_evidence_refs" in response.hybrid_route.fallback_block_reason
    assert "shadow_only_no_runtime" in response.hybrid_route.fallback_block_reason
    assert response.capability_payload["invoked"] is False
    assert response.capability_payload["adapter_invoked"] is True
    assert response.capability_payload["gate_passed"] is False
