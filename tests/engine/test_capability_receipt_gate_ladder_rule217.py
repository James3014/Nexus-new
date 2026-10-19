"""RULE-217: gate_passed requires invoked and evidence_present (no false-green receipts)."""

from __future__ import annotations

from nexus.engine.capability_receipt_adapters import (
    RECEIPT_ADAPTERS,
    merge_capability_receipt,
)


def test_merge_receipt_gate_passed_requires_invoked_and_evidence():
    # 1. selected but never invoked, evidence present, gate claimed -> no pass
    not_invoked = merge_capability_receipt(
        name="codeintel",
        selected=True,
        invoked=False,
        evidence_refs=["r"],
        gate_passed=True,
    )
    assert not_invoked.gate_passed is False
    assert not_invoked.outcome_contributed is False
    assert not_invoked.failure_reason == "selected_without_invocation"

    # 2. invoked but no evidence -> no pass
    no_evidence = merge_capability_receipt(
        name="codeintel",
        selected=True,
        invoked=True,
        evidence_refs=[],
        gate_passed=True,
    )
    assert no_evidence.gate_passed is False
    assert no_evidence.outcome_contributed is False
    assert no_evidence.failure_reason == "invoked_without_evidence"

    # 3. swarm adapter repro: swarm_used=False but evidence_count>0 and claim verified
    swarm = RECEIPT_ADAPTERS["swarm"].build(
        claim_verified=True,
        payload={"swarm_used": False, "swarm_evidence_count": 3},
    )
    assert swarm.invoked is False
    assert swarm.gate_passed is False
    assert swarm.outcome_contributed is False
    # the adapter's own (more specific) reason is kept
    assert swarm.failure_reason == "selected_without_invocation"

    # 4. a fully valid receipt still passes
    valid = merge_capability_receipt(
        name="codeintel",
        selected=True,
        invoked=True,
        evidence_refs=["ev:1"],
        gate_passed=True,
        outcome_contributed=True,
    )
    assert valid.gate_passed is True
    assert valid.evidence_present is True
    assert valid.outcome_contributed is True
    assert valid.failure_reason == ""


def test_merge_receipt_keeps_existing_failure_reason_when_clamping():
    r = merge_capability_receipt(
        name="codeintel",
        selected=True,
        invoked=False,
        evidence_refs=["r"],
        gate_passed=True,
        failure_reason="adapter_specific_reason",
    )
    assert r.gate_passed is False
    assert r.failure_reason == "adapter_specific_reason"


def test_ddtree_receipt_gate_requires_invocation():
    # feature flag off but saved_steps>0 and claim verified: same shape as the swarm defect
    r = RECEIPT_ADAPTERS["ddtree"].build(
        claim_verified=True,
        payload={"enabled": False, "eligible": True, "actual_saved_steps": 3},
    )
    assert r.invoked is False
    assert r.gate_passed is False
    assert r.failure_reason == "feature_flag_disabled"


def test_merge_receipt_clamped_gate_gets_no_synthesized_telemetry():
    r = merge_capability_receipt(
        name="codeintel",
        selected=True,
        invoked=True,
        evidence_refs=[],
        gate_passed=True,
    )
    assert r.gate_passed is False
    assert r.failure_reason == "invoked_without_evidence"
    assert r.telemetries == {}
