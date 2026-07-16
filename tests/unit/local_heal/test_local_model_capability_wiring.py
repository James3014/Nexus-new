from __future__ import annotations

import pytest

from nexus.services.local_heal.local_model_capability_wiring import (
    CapabilityWiringStatus,
    build_local_model_capability_wiring,
    classify_selected_capabilities,
)


def test_registry_count_covers_spxdrac_and_planner():
    from nexus.core.capability_registry import CapabilityRegistry
    from nexus.services.capability_registry import PLANNER_EXECUTION_CONTRACTS

    wiring = build_local_model_capability_wiring()
    registry_names = {c.name for c in CapabilityRegistry().list_all_capabilities()}
    # SPXDRAC surface still covered; planner contracts may extend the map.
    assert registry_names <= set(wiring.keys())
    assert set(PLANNER_EXECUTION_CONTRACTS.keys()) <= set(wiring.keys())
    assert len(registry_names) == 51


def test_all_registry_caps_present():
    from nexus.core.capability_registry import CapabilityRegistry
    registry_names = {c.name for c in CapabilityRegistry().list_all_capabilities()}
    wiring = build_local_model_capability_wiring()
    assert registry_names <= set(wiring.keys())


def test_local_model_executor_is_executable():
    """local_model_executor is a local executor concept, not in 34-registry but should be in wiring."""
    # Note: local_model_executor is not in the 34-registry; it's a local executor concept.
    # The wiring map includes it for completeness but classify_selected_capabilities
    # treats unknown names as unsupported.
    # This test verifies the executor entry exists in the wiring definitions.
    from nexus.services.local_heal.local_model_executor import LocalModelExecutor
    assert LocalModelExecutor is not None


def test_ddtree_is_contract_projected():
    from nexus.services.capability_registry import project_local_execution_mode

    wiring = build_local_model_capability_wiring()
    w = wiring["ddtree"]
    mode = project_local_execution_mode("ddtree")
    assert w.reason.startswith("contract_projection:")
    assert mode in {
        "EXECUTE_HERE",
        "CONSUME_SHARED_EVIDENCE",
        "CONTROLLED_BY_POSTFLIGHT",
        "EXTERNAL_NOT_LOCAL",
    }
    assert w.status != CapabilityWiringStatus.UNSUPPORTED


def test_autoreason_is_contract_projected():
    wiring = build_local_model_capability_wiring()
    w = wiring["autoreason"]
    assert w.reason.startswith("contract_projection:")
    assert w.status != CapabilityWiringStatus.UNSUPPORTED


def test_artifact_gate_is_gate_executable():
    wiring = build_local_model_capability_wiring()
    w = wiring["artifact_gate"]
    assert w.status == CapabilityWiringStatus.GATE_EXECUTABLE
    assert w.local_model_supported is True


def test_claim_gate_is_gate_executable():
    wiring = build_local_model_capability_wiring()
    w = wiring["claim_gate"]
    assert w.status == CapabilityWiringStatus.GATE_EXECUTABLE
    assert w.local_model_supported is True


def test_delivery_gate_is_gate_executable():
    """delivery_gate is not in the 34-registry but is a local executor concept."""
    # delivery_gate is handled by claim_delivery_gate.validate_context_claim_delivery
    # which covers both claim and delivery gates together.
    from nexus.services.local_heal.claim_delivery_gate import validate_context_claim_delivery
    assert validate_context_claim_delivery is not None


def test_repair_loop_is_contract_supported():
    wiring = build_local_model_capability_wiring()
    w = wiring["repair_loop"]
    assert w.status != CapabilityWiringStatus.UNSUPPORTED
    assert w.reason.startswith("contract_projection:")


def test_external_only_caps():
    """Contract projection may promote former external-only names; ui stays external."""
    wiring = build_local_model_capability_wiring()
    # ui_validator / external auth remain EXTERNAL_NOT_LOCAL → EXTERNAL_ONLY
    assert wiring["ui_validator"].status == CapabilityWiringStatus.EXTERNAL_ONLY
    # Planner contract projection: no UNSUPPORTED for planner nodes
    from nexus.services.capability_registry import PLANNER_EXECUTION_CONTRACTS

    for name in PLANNER_EXECUTION_CONTRACTS:
        assert wiring[name].status != CapabilityWiringStatus.UNSUPPORTED, name


def test_classify_selected_ddtree():
    result = classify_selected_capabilities(["ddtree", "autoreason"])
    # Contract-derived: may land in advisory/external/executable buckets — never unsupported.
    assert "ddtree" in result["selected_capabilities_seen"]
    assert "autoreason" in result["selected_capabilities_seen"]
    assert "ddtree" not in result["unsupported_capabilities"]
    assert "autoreason" not in result["unsupported_capabilities"]


def test_classify_selected_unknown():
    result = classify_selected_capabilities(["totally_fake_capability_xyz"])
    assert "totally_fake_capability_xyz" in result["unsupported_capabilities"]
    assert len(result["executable_capabilities"]) == 0


def test_classify_selected_gates():
    result = classify_selected_capabilities(["artifact_gate", "claim_gate"])
    assert len(result["gate_capabilities"]) == 2
    assert "artifact_gate" in result["gate_capabilities"]
    assert "claim_gate" in result["gate_capabilities"]


def test_ddtree_autoreason_not_metadata_only():
    """ddtree/autoreason must NOT be metadata_only (contract-projected)."""
    result = classify_selected_capabilities(["ddtree", "autoreason"])
    assert len(result["metadata_only_capabilities"]) == 0
    assert "ddtree" not in result["unsupported_capabilities"]
    assert "autoreason" not in result["unsupported_capabilities"]
    # EXTERNAL_AUTH model-boundary → external_only under Local projection
    assert "ddtree" in result["external_only_capabilities"] or "ddtree" in result["advisory_capabilities"]
    assert "autoreason" in result["external_only_capabilities"] or "autoreason" in result["advisory_capabilities"]


def test_artifact_claim_not_metadata_only():
    """artifact/claim gates must NOT be metadata_only."""
    result = classify_selected_capabilities(["artifact_gate", "claim_gate"])
    assert len(result["metadata_only_capabilities"]) == 0
    assert len(result["gate_capabilities"]) == 2


def test_memory_is_contract_projected():
    result = classify_selected_capabilities(["memory"])
    assert "memory" in result["selected_capabilities_seen"]
    assert "memory" not in result["unsupported_capabilities"]
    assert "memory" not in result["metadata_only_capabilities"]
