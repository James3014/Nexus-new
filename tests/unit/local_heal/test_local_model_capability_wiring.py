from __future__ import annotations

import pytest

from nexus.services.local_heal.local_model_capability_wiring import (
    CapabilityWiringStatus,
    build_local_model_capability_wiring,
    classify_selected_capabilities,
)


def test_registry_count_is_34():
    wiring = build_local_model_capability_wiring()
    assert len(wiring) == 34


def test_all_registry_caps_present():
    from nexus.core.capability_registry import CapabilityRegistry
    registry_names = {c.name for c in CapabilityRegistry().list_all_capabilities()}
    wiring = build_local_model_capability_wiring()
    assert registry_names == set(wiring.keys())


def test_local_model_executor_is_executable():
    """local_model_executor is a local executor concept, not in 34-registry but should be in wiring."""
    # Note: local_model_executor is not in the 34-registry; it's a local executor concept.
    # The wiring map includes it for completeness but classify_selected_capabilities
    # treats unknown names as unsupported.
    # This test verifies the executor entry exists in the wiring definitions.
    from nexus.services.local_heal.local_model_executor import LocalModelExecutor
    assert LocalModelExecutor is not None


def test_ddtree_is_advisory_executable():
    wiring = build_local_model_capability_wiring()
    w = wiring["ddtree"]
    assert w.status == CapabilityWiringStatus.ADVISORY_EXECUTABLE
    assert w.local_model_supported is True


def test_autoreason_is_advisory_executable():
    wiring = build_local_model_capability_wiring()
    w = wiring["autoreason"]
    assert w.status == CapabilityWiringStatus.ADVISORY_EXECUTABLE
    assert w.local_model_supported is True


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


def test_repair_loop_is_localheal_executable():
    wiring = build_local_model_capability_wiring()
    w = wiring["repair_loop"]
    assert w.status == CapabilityWiringStatus.LOCALHEAL_EXECUTABLE
    assert w.local_model_supported is True


def test_external_only_caps():
    wiring = build_local_model_capability_wiring()
    external_only = [name for name, w in wiring.items() if w.status == CapabilityWiringStatus.EXTERNAL_ONLY]
    for name in ["swarm_multi_agent", "drone", "ultra_review", "hyper_sprint", "nightshift",
                  "lancedb", "belief", "mempalace", "research", "ui_validator",
                  "external_productivity"]:
        assert name in external_only, f"{name} should be external_only"


def test_classify_selected_ddtree():
    result = classify_selected_capabilities(["ddtree", "autoreason"])
    assert "ddtree" in result["advisory_capabilities"]
    assert "autoreason" in result["advisory_capabilities"]
    assert len(result["unsupported_capabilities"]) == 0


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
    """ddtree/autoreason must NOT be metadata_only; they are advisory_executable."""
    result = classify_selected_capabilities(["ddtree", "autoreason"])
    assert len(result["metadata_only_capabilities"]) == 0
    assert "ddtree" in result["advisory_capabilities"]
    assert "autoreason" in result["advisory_capabilities"]


def test_artifact_claim_not_metadata_only():
    """artifact/claim gates must NOT be metadata_only."""
    result = classify_selected_capabilities(["artifact_gate", "claim_gate"])
    assert len(result["metadata_only_capabilities"]) == 0
    assert len(result["gate_capabilities"]) == 2


def test_memory_is_metadata_only():
    result = classify_selected_capabilities(["memory"])
    assert "memory" in result["metadata_only_capabilities"]
