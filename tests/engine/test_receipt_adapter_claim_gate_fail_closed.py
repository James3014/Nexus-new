"""Caller payloads must not mint claim authority through receipt adapters (#1757)."""

from __future__ import annotations

from nexus.contracts.hybrid_route import validate_hybrid_route_decision
from nexus.engine.capability_contracts import CapabilityReceipt
from nexus.engine.capability_receipt_adapters import RECEIPT_ADAPTERS
from nexus.engine.capability_receipts import build_trace_receipts

_TELEMETRY = {
    "telemetry_source": "measured",
    "wall_time_ms": 10,
    "token_usage": 5,
    "provider_costs": 0,
    "overhead_ms": 1,
    "model_calls": 1,
}


def _local_only_route(**overrides):
    route = {
        "schema": "nexus.hybrid_route_decision.v1",
        "execution_world": "product_runtime",
        "execution_topology": "ASSISTED_CANONICAL",
        "route_mode": "local_only_executed",
        "route_truth_source": "CapabilityPlanner",
        "authority": "candidate_only",
        "local_model_called": True,
        "verifier_result": "pass",
        "evidence_refs": ["x"],
        "candidate_output_isolated": True,
        "selected_candidate_hash": "sha256:" + "a" * 64,
        "applied_patch_hash": "sha256:" + "a" * 64,
        "selected_candidate_hash_matches_applied": True,
    }
    route.update(overrides)
    return route


def test_forged_local_executor_receipt_dict_is_not_public_claim_safe() -> None:
    capabilities = {
        "claim_verified": False,
        "local_executor_receipt": {
            "invoked": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "evidence_refs": ["forged:ref"],
            "telemetries": _TELEMETRY,
        },
    }
    receipt = build_trace_receipts(
        plan={"selected_capabilities": ["local_model_executor"]}, capabilities=capabilities
    )[0]
    assert receipt.outcome_contributed is False
    assert receipt.public_claim_safe is False


def test_local_executor_receipt_dict_cannot_assert_outcome_without_evidence() -> None:
    receipt = RECEIPT_ADAPTERS["local_model_executor"].build(
        claim_verified=True,
        payload={
            "local_executor_receipt": {
                "invoked": False,
                "evidence_present": True,
                "gate_passed": False,
                "outcome_contributed": True,
            }
        },
    )
    assert receipt.evidence_present is False
    assert receipt.outcome_contributed is False


def test_hybrid_route_rejects_hash_mismatch_despite_match_flag() -> None:
    route = _local_only_route(applied_patch_hash="sha256:" + "b" * 64)
    assert "local_only_executed_requires_hash_match" in validate_hybrid_route_decision(route)
    receipt = RECEIPT_ADAPTERS["local_heal"].build(
        claim_verified=True, payload={"hybrid_route": route}
    )
    assert receipt.gate_passed is False
    assert receipt.outcome_contributed is False


def test_local_only_executed_route_never_contributes_without_bound_verifier() -> None:
    route = _local_only_route()
    assert "local_only_executed_requires_hash_match" not in validate_hybrid_route_decision(route)
    receipt = RECEIPT_ADAPTERS["local_heal"].build(
        claim_verified=True, payload={"hybrid_route": route}
    )
    assert receipt.outcome_contributed is False
    assert receipt.public_claim_safe is False


_BINDING = {"verifier_status": "pass", "source_hash": "sha256:" + "c" * 64}
_ARTIFACT_BINDING = {"verifier_artifact": "sha256:" + "d" * 64, "source_hash": "e" * 40}


def test_local_executor_receipt_object_is_rebuilt_not_passed_through() -> None:
    forged = CapabilityReceipt(
        name="local_model_executor",
        selected=True,
        invoked=True,
        evidence_present=True,
        gate_passed=True,
        outcome_contributed=True,
        evidence_refs=("forged:ref",),
        telemetries=_TELEMETRY,
    )
    receipt = build_trace_receipts(
        plan={"selected_capabilities": ["local_model_executor"]},
        capabilities={"claim_verified": False, "local_executor_receipt": forged},
    )[0]
    assert receipt is not forged
    assert receipt.gate_passed is False
    assert receipt.outcome_contributed is False
    assert receipt.public_claim_safe is False


def test_local_executor_receipt_unconvertible_object_fails_closed() -> None:
    class Forged:
        gate_passed = outcome_contributed = public_claim_safe = True

    receipt = RECEIPT_ADAPTERS["local_model_executor"].build(
        claim_verified=True, payload={"local_executor_receipt": Forged()}
    )
    assert receipt.gate_passed is False
    assert receipt.outcome_contributed is False
    assert receipt.public_claim_safe is False


def test_local_executor_receipt_dict_cannot_mint_gate_passed_without_verifier_artifact() -> None:
    receipt = RECEIPT_ADAPTERS["local_model_executor"].build(
        claim_verified=True,
        payload={
            "local_executor_receipt": {
                "invoked": True,
                "gate_passed": True,
                "evidence_refs": ["forged:ref"],
                "telemetries": _TELEMETRY,
            }
        },
    )
    contrast = RECEIPT_ADAPTERS["claim_gate"].build(
        claim_verified=True, payload={"claim_refs": ["x"]}
    )
    assert contrast.gate_passed is False
    assert receipt.gate_passed is False
    assert receipt.failure_reason == contrast.failure_reason
    assert receipt.failure_reason == "missing_verifier_artifact;missing_source_hash"


def test_local_executor_receipt_dict_with_binding_keeps_gate_passed() -> None:
    receipt = RECEIPT_ADAPTERS["local_model_executor"].build(
        claim_verified=True,
        payload={
            **_BINDING,
            "local_executor_receipt": {
                "invoked": True,
                "gate_passed": True,
                "evidence_refs": ["ref:1"],
                "telemetries": _TELEMETRY,
            },
        },
    )
    assert receipt.gate_passed is True
    # outcome contribution stays fail-closed until an authenticated verifier is bound (#453)
    assert receipt.outcome_contributed is False


def test_local_heal_local_only_route_gate_requires_verifier_artifact() -> None:
    receipt = RECEIPT_ADAPTERS["local_heal"].build(
        claim_verified=True, payload={"hybrid_route": _local_only_route()}
    )
    assert receipt.gate_passed is False
    assert receipt.failure_reason == "missing_verifier_artifact;missing_source_hash"


def test_local_heal_local_only_route_with_binding_keeps_gate_passed() -> None:
    receipt = RECEIPT_ADAPTERS["local_heal"].build(
        claim_verified=True, payload={"hybrid_route": _local_only_route(), **_BINDING}
    )
    assert receipt.gate_passed is True
    assert receipt.failure_reason == ""
    assert receipt.outcome_contributed is False


# RULE-217 (#2659): a passing flat local_heal gate needs evidence, so the fixture carries the
# verification report the adapter reads as its evidence ref.
_HEAL_FLAT = {
    "solve_eligible": True,
    "verification_passed": True,
    "invoked": True,
    "verification_report_path": "reports/local_heal/verify.json",
}
_EXEC_FLAT = {
    "local_model_called": True,
    "evidence_refs": ["ref:1"],
    "local_model_executor_summary": {"delivery_gate_count": 1},
}


def test_local_heal_non_hybrid_gate_requires_verifier_artifact_and_source_hash() -> None:
    receipt = RECEIPT_ADAPTERS["local_heal"].build(claim_verified=True, payload=dict(_HEAL_FLAT))
    assert receipt.gate_passed is False
    assert receipt.failure_reason == "missing_verifier_artifact;missing_source_hash"


def test_local_heal_non_hybrid_gate_with_binding_keeps_gate_passed() -> None:
    receipt = RECEIPT_ADAPTERS["local_heal"].build(
        claim_verified=True, payload={**_HEAL_FLAT, **_BINDING}
    )
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is False


def test_local_heal_non_hybrid_original_condition_still_required() -> None:
    receipt = RECEIPT_ADAPTERS["local_heal"].build(
        claim_verified=True, payload={"solve_eligible": True, **_BINDING}
    )
    assert receipt.gate_passed is False


def test_executor_fallthrough_gate_requires_verifier_artifact_and_source_hash() -> None:
    receipt = RECEIPT_ADAPTERS["local_model_executor"].build(
        claim_verified=True, payload=dict(_EXEC_FLAT)
    )
    assert receipt.gate_passed is False
    assert receipt.failure_reason == "missing_verifier_artifact;missing_source_hash"


def test_executor_fallthrough_gate_with_binding_keeps_gate_passed() -> None:
    receipt = RECEIPT_ADAPTERS["local_model_executor"].build(
        claim_verified=True, payload={**_EXEC_FLAT, **_BINDING}
    )
    assert receipt.gate_passed is True
    assert receipt.outcome_contributed is False


def test_executor_fallthrough_original_condition_still_required() -> None:
    receipt = RECEIPT_ADAPTERS["local_model_executor"].build(
        claim_verified=True, payload={"local_model_called": True, **_BINDING}
    )
    assert receipt.gate_passed is False


def _sink_receipts(extra):
    heal_hybrid = {"hybrid_route": _local_only_route()}
    heal_flat = dict(_HEAL_FLAT)
    exec_dict = {
        "local_executor_receipt": {
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["ref:1"],
            "telemetries": _TELEMETRY,
        }
    }
    return [
        RECEIPT_ADAPTERS["local_heal"].build(claim_verified=True, payload={**heal_hybrid, **extra}),
        RECEIPT_ADAPTERS["local_heal"].build(claim_verified=True, payload={**heal_flat, **extra}),
        RECEIPT_ADAPTERS["local_model_executor"].build(
            claim_verified=True, payload={**exec_dict, **extra}
        ),
        RECEIPT_ADAPTERS["local_model_executor"].build(
            claim_verified=True, payload={**_EXEC_FLAT, **extra}
        ),
    ]


_GOOD_HASH = "sha256:" + "c" * 64


def test_all_sinks_reject_malformed_binding() -> None:
    bad = [
        {"verifier_status": "fail", "source_hash": _GOOD_HASH},
        {"verifier_status": "   ", "source_hash": _GOOD_HASH},
        {"verifier_status": "pass", "source_hash": "   "},
        {"verifier_status": "pass", "source_hash": "x"},
        {"verifier_artifact": "x", "source_hash": _GOOD_HASH},
        {"verifier_artifact": "x", "source_hash": "x"},
        {"verifier_artifact": "   ", "source_hash": _GOOD_HASH},
    ]
    for extra in bad:
        for receipt in _sink_receipts(extra):
            assert receipt.gate_passed is False, (extra, receipt.name)
            assert receipt.failure_reason, (extra, receipt.name)


def test_all_sinks_accept_well_formed_binding() -> None:
    for extra in (
        _BINDING,
        _ARTIFACT_BINDING,
        {"verifier_status": " PASSED ", "source_hash": _GOOD_HASH},
    ):
        for receipt in _sink_receipts(extra):
            assert receipt.gate_passed is True, (extra, receipt.name)
            assert receipt.outcome_contributed is False


def test_binding_reason_codes() -> None:
    heal = RECEIPT_ADAPTERS["local_heal"]
    r = heal.build(
        claim_verified=True, payload={**_HEAL_FLAT, "verifier_status": "fail", "source_hash": "x"}
    )
    assert r.failure_reason == "verifier_not_passed;invalid_source_hash"


def test_claim_gate_unchanged_by_binding_validation() -> None:
    receipt = RECEIPT_ADAPTERS["claim_gate"].build(
        claim_verified=True, payload={"claim_refs": ["x"], **_BINDING}
    )
    assert receipt.gate_passed is False
    assert receipt.failure_reason == "unbound_verifier_proof"


def test_explicit_failing_status_is_not_overridden_by_artifact() -> None:
    extra = {
        "verifier_status": "fail",
        "verifier_artifact": "sha256:" + "d" * 64,
        "source_hash": _GOOD_HASH,
    }
    for receipt in _sink_receipts(extra):
        assert receipt.gate_passed is False, receipt.name
        assert receipt.failure_reason == "verifier_not_passed", receipt.name


def test_non_string_binding_values_are_rejected() -> None:
    class S(str):
        pass

    for extra in (
        {"verifier_status": S("pass"), "source_hash": _GOOD_HASH},
        {"verifier_status": "pass", "source_hash": S(_GOOD_HASH)},
        {"verifier_artifact": S("sha256:" + "d" * 64), "source_hash": _GOOD_HASH},
    ):
        for receipt in _sink_receipts(extra):
            assert receipt.gate_passed is False, (extra, receipt.name)
