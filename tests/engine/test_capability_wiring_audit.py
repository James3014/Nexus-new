from __future__ import annotations

from nexus.engine.capability_wiring_audit import build_capability_wiring_audit, unused_reason_for_row


def test_capability_wiring_audit_has_no_high_priority_registry_only_capabilities():
    audit = build_capability_wiring_audit().to_dict()

    assert audit["passed"] is True
    assert audit["high_priority_registry_only"] == []
    assert audit["high_priority_missing_receipt_policy"] == []
    assert audit["pending_executor_without_spec"] == []


def test_capability_wiring_audit_tracks_msa_jit_and_core_pillars():
    rows = {item["name"]: item for item in build_capability_wiring_audit().rows}

    for name in (
        "artifact_gate",
        "belief",
        "claim_gate",
        "jit_validation",
        "lancedb",
        "memory",
        "mempalace_gate",
        "msa_router",
        "repair_loop",
    ):
        assert rows[name]["adapter_exists"] is True, name
        assert rows[name]["receipt_policy_backed"] is True, name
        assert rows[name]["status"] in {"runtime_backed", "receipt_backed_pending_executor"}, name


def test_former_pending_executor_capabilities_are_runtime_claimable():
    rows = {item["name"]: item for item in build_capability_wiring_audit().rows}

    for name in ("swarm", "drone", "nightshift"):
        spec = rows[name]["executor_spec"]
        assert rows[name]["pending_executor"] is False
        assert rows[name]["status"] == "runtime_backed"
        assert spec["required"] is False
        assert spec["status"] == "not_applicable"
        assert spec["runtime_claim_allowed"] is True
        assert spec["allowed_claim_scope"] == "runtime_backed"


def test_unused_reason_classifier_separates_wiring_failures():
    assert unused_reason_for_row({"selected": False}) == "not_selected_by_signal"
    assert unused_reason_for_row({"selected": True, "adapter_exists": False}) == "selected_no_adapter"
    assert unused_reason_for_row({"selected": True, "adapter_exists": True, "pending_executor": True}) == "pending_executor"
    assert unused_reason_for_row({"selected": True, "adapter_exists": True, "maturity": "legacy_alias"}) == "deprecated_alias"
    assert unused_reason_for_row({"selected": True, "adapter_exists": True}) == "selected_no_runtime_payload"
    assert unused_reason_for_row({"selected": True, "adapter_exists": True, "invoked": True}) == "invoked_no_evidence"
    assert (
        unused_reason_for_row({"selected": True, "adapter_exists": True, "invoked": True, "evidence_present": True})
        == "evidence_no_gate"
    )
    assert (
        unused_reason_for_row(
            {"selected": True, "adapter_exists": True, "invoked": True, "evidence_present": True, "gate_passed": True}
        )
        == "gate_no_outcome"
    )
    assert (
        unused_reason_for_row(
            {
                "selected": True,
                "adapter_exists": True,
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
            }
        )
        == ""
    )
