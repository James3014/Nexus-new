from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from nexus.services.product_capability_closure import (
    BLOCKED_DEPENDENCY,
    EVIDENCE_INCOMPLETE,
    EXECUTION_FAILED,
    LIVE_EXECUTED_PASS,
    POLICY_SKIP_VERIFIED,
    PRODUCT_CAPABILITIES,
    VERIFIER_FAILED,
    summarize_origin_matrix,
    expected_resolution_type,
    verify_product_capability_resolution,
)
from nexus.services.capability_registry import coverage_counts_from_receipt


def _hash_payload(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _valid_record(
    capability: str = "codeintel",
    *,
    origin: str = "online",
) -> dict[str, object]:
    resolution = expected_resolution_type(origin, capability)
    evidence_payload = {"capability": capability, "effect": "observed"}
    effect_payload = {"effect_type": "workspace_fingerprint", "value": "fp-1"}
    receipt_payload = {
        "capability": capability,
        "origin": origin,
        "run_id": f"run-{origin}-{capability}",
    }
    verifier_evidence = {"command": "pytest -q", "exit_code": 0}
    verifier_artifact = {"status": "VERIFIED", "capability": capability}
    record: dict[str, object] = {
        "capability": capability,
        "origin": origin,
        "resolution_type": resolution,
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "skipped": False,
        "status": "INVOKED",
        "gate_passed": True,
        "physical_callable": "nexus.core.capability_executor_registry:codeintel",
        "provider": "production",
        "evidence_refs": [
            {
                "path": "/tmp/evidence/codeintel.json",
                "sha256": _hash_payload(evidence_payload),
                "payload": evidence_payload,
            }
        ],
        "observable_effect": {
            "effect_type": "workspace_fingerprint",
            "artifact_hash": _hash_payload(effect_payload),
            "artifact_payload": effect_payload,
        },
        "receipt_hash": _hash_payload(receipt_payload),
        "receipt_payload": receipt_payload,
        "receipt_hash_verified": True,
        "structured_evidence_verified": True,
        "verifier": {
            "invoked": True,
            "passed": True,
            "evidence_hash": _hash_payload(verifier_evidence),
            "evidence_payload": verifier_evidence,
            "artifact_hash": _hash_payload(verifier_artifact),
            "artifact_payload": verifier_artifact,
        },
        "public_claim_allowed": False,
        "route_surface_changed": False,
    }
    if origin == "local":
        record["assist_lineage"] = {
            "packet_hash": "1" * 64,
            "fragment_hash": "2" * 64,
            "final_prompt_hash": "3" * 64,
            "online_candidate_hash": "4" * 64,
            "applied_artifact_hash": "5" * 64,
            "verifier_artifact_hash": "6" * 64,
            "final_receipt_hash": "7" * 64,
        }
    if capability in {"local_model_executor", "repair_loop"}:
        record["resolution_type"] = (
            "ONLINE_TO_LOCAL_GOVERNED_BRIDGE" if origin == "online" else "LOCAL_NATIVE"
        )
        record["local_execution"] = {
            "provider_family": "ollama",
            "model_name": "qwen-local",
            "model_called": True,
            "output_delivered": True,
            "candidate_isolated": True,
            "candidate_hash": "8" * 64,
            "selected_hash": "9" * 64,
            "applied_hash": "9" * 64,
            "network_invoked": False,
            "loop_entered": capability == "repair_loop",
        }
        if origin == "local":
            record.pop("assist_lineage", None)
    return record


def test_product_denominator_is_frozen_to_34_contract_nodes() -> None:
    assert len(PRODUCT_CAPABILITIES) == 34
    assert PRODUCT_CAPABILITIES == (
        "acceptance_check",
        "architecture_scout",
        "artifact_gate",
        "asi_constraint_extractor",
        "bdd_acceptance_skill",
        "belief",
        "benchmark",
        "claim_gate",
        "codeintel",
        "delivery_gate",
        "drone",
        "file_lock",
        "forecast_gate",
        "formal_report",
        "harness_preflight_sensor",
        "jit_validation",
        "lancedb",
        "learn_mode",
        "learn_phase_slo",
        "local_model_executor",
        "memory",
        "mempalace_gate",
        "meta_opt",
        "plan_quality_gate",
        "pregate",
        "prompt_compression",
        "repair_loop",
        "research",
        "sandbox",
        "semantic_failure_sensor",
        "semantic_searcher",
        "stress_test",
        "ultra_review",
        "xray",
    )


def test_valid_resolution_is_live_executed_pass() -> None:
    verdict = verify_product_capability_resolution(_valid_record())
    assert verdict["status"] == LIVE_EXECUTED_PASS
    assert verdict["live_pass"] is True
    assert verdict["missing_evidence_reasons"] == []


def test_policy_skip_never_counts_as_live_pass() -> None:
    record = _valid_record()
    record.update(
        skipped=True,
        status="SKIPPED_POLICY_NOT_TRIGGERED",
        invoked=False,
        live_closure_pass=True,
    )
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] == POLICY_SKIP_VERIFIED
    assert verdict["live_pass"] is False


def test_selected_not_executed_is_blocked() -> None:
    record = _valid_record()
    record.update(status="SELECTED_NOT_EXECUTED", invoked=False)
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] == BLOCKED_DEPENDENCY
    assert "selected_not_executed" in verdict["missing_evidence_reasons"]


def test_blocker_evidence_never_counts_as_pass() -> None:
    record = _valid_record()
    record["evidence_refs"] = ["blocker:online_not_invoked"]
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] == BLOCKED_DEPENDENCY
    assert "blocker_evidence_present" in verdict["missing_evidence_reasons"]


def test_receipt_hash_mismatch_and_fixture_transport_fail_closed() -> None:
    mismatch = _valid_record()
    mismatch["receipt_hash"] = "0" * 64
    verdict = verify_product_capability_resolution(mismatch)
    assert verdict["status"] == EVIDENCE_INCOMPLETE
    assert "receipt_hash_not_verified" in verdict["missing_evidence_reasons"]

    fixture = _valid_record()
    fixture.update(
        provider="fixture",
        physical_callable="test:fixture_invoker",
        live_closure_pass=True,
    )
    verdict = verify_product_capability_resolution(fixture)
    assert verdict["status"] == EVIDENCE_INCOMPLETE
    assert "synthetic_or_fixture_execution" in verdict["missing_evidence_reasons"]


def test_verifier_failure_is_not_terminal_pass() -> None:
    record = _valid_record()
    record["verifier"] = {
        "invoked": True,
        "passed": False,
        "evidence_hash": "d" * 64,
        "artifact_hash": "e" * 64,
    }
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] == VERIFIER_FAILED
    assert verdict["live_pass"] is False


def test_local_model_requires_real_call_isolation_hash_match_and_verifier() -> None:
    record = _valid_record("local_model_executor", origin="local")
    local = dict(record["local_execution"])
    local["model_called"] = False
    record["local_execution"] = local
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] == EXECUTION_FAILED
    assert "local_model_not_called" in verdict["missing_evidence_reasons"]

    record = _valid_record("repair_loop", origin="online")
    local = dict(record["local_execution"])
    local["applied_hash"] = "0" * 64
    record["local_execution"] = local
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] == EVIDENCE_INCOMPLETE
    assert "selected_applied_hash_mismatch" in verdict["missing_evidence_reasons"]


def test_consumed_assist_without_result_lineage_is_not_attribution_pass() -> None:
    record = _valid_record(origin="local")
    record["assist_lineage"] = {
        "packet_hash": "1" * 64,
        "consumption_status": "consumed",
    }
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] == EVIDENCE_INCOMPLETE
    assert "assist_lineage_incomplete" in verdict["missing_evidence_reasons"]


def test_68_entry_matrix_requires_one_live_pass_per_origin_capability() -> None:
    records = [
        _valid_record(capability, origin=origin)
        for origin in ("online", "local")
        for capability in PRODUCT_CAPABILITIES
    ]
    summary = summarize_origin_matrix(records)
    assert summary["online_origin_pass"] == 34
    assert summary["local_origin_pass"] == 34
    assert summary["matrix_pass"] == 68
    assert summary["matrix_total"] == 68
    assert summary["complete"] is True
    assert summary["receipt_hash_verified_count"] == 68
    assert summary["synthetic_live_pass"] == 0
    assert summary["public_claim_allowed"] is False

    bad = deepcopy(records)
    bad[0].update(
        skipped=True,
        invoked=False,
        status="SKIPPED_POLICY_NOT_TRIGGERED",
    )
    summary = summarize_origin_matrix(bad)
    assert summary["complete"] is False
    assert summary["matrix_pass"] == 67
    assert summary["policy_skip_pass_count"] == 0
    assert summary["policy_skip_count"] == 1

    bad_hash = deepcopy(records)
    bad_hash[0]["receipt_hash"] = "0" * 64
    summary = summarize_origin_matrix(bad_hash)
    assert summary["complete"] is False
    assert summary["receipt_hash_verified_count"] == 67


def test_runtime_coverage_keeps_surface_coverage_but_rejects_all_skip_live_green() -> None:
    receipt = {
        "context_trace": {"selected_capabilities": ["architecture_scout"]},
        "capabilities": [
            {
                "name": "architecture_scout",
                "status": "SKIPPED",
                "skipped": True,
                "skip_reason": "SKIPPED_POLICY_NOT_TRIGGERED",
                "evidence_refs": ["policy:architecture_scout:skip"],
                "gate_passed": True,
            }
        ],
    }
    coverage = coverage_counts_from_receipt(receipt)
    assert coverage["surface_coverage_ok"] is True
    assert coverage["real_execution_coverage_ok"] is False
    assert coverage["verified_outcome_ok"] is False
    assert coverage["strict_closure_complete"] is False
    assert coverage["policy_skip_count"] == 1
    assert coverage["live_execution_pass_count"] == 0


def test_runtime_coverage_rejects_blocker_and_fixture_evidence_as_live_execution() -> None:
    receipt = {
        "context_trace": {
            "selected_capabilities": ["artifact_gate", "sandbox", "xray"],
        },
        "capabilities": [
            {
                "name": "artifact_gate",
                "status": "INVOKED",
                "invoked": True,
                "gate_passed": True,
                "physical_callable": "online_nexus_context.evaluate_postflight_gate",
                "evidence_refs": [{"type": "blocker", "ref": "missing_artifact_lineage"}],
            },
            {
                "name": "sandbox",
                "status": "INVOKED",
                "invoked": True,
                "gate_passed": True,
                "physical_callable": "nexus.core.capability_executor_registry:sandbox",
                "evidence_refs": ["fixture:sandbox"],
            },
            {
                "name": "xray",
                "status": "INVOKED",
                "invoked": True,
                "gate_passed": True,
                "physical_callable": "",
                "evidence_refs": ["production:xray"],
            },
        ],
    }
    coverage = coverage_counts_from_receipt(receipt)
    assert coverage["surface_coverage_ok"] is True
    assert coverage["real_execution_coverage_ok"] is False
    assert coverage["verified_outcome_ok"] is False
    assert coverage["strict_closure_complete"] is False
    assert coverage["blocker_evidence_count"] == 1
    assert coverage["synthetic_execution_count"] == 1
    assert coverage["missing_physical_callable_count"] == 1
    assert coverage["live_execution_pass_count"] == 0


def test_phase2_lineage_negative_controls() -> None:
    # 1. Tampered lineage payload / hash mismatch
    record = _valid_record("codeintel", origin="local")
    record["assist_lineage"]["packet_payload"] = {"tampered": True}
    record["assist_lineage"]["packet_hash"] = "1" * 64
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert verdict["gate_verdict"] == "BLOCK_OR_RETURN"

    # 2. Task ID mismatch in assist lineage
    record = _valid_record("codeintel", origin="local")
    record["task_id"] = "task-A"
    record["assist_lineage"]["task_id"] = "task-B"
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False

    # 3. Synthetic / fixture execution
    record = _valid_record("codeintel", origin="online")
    record["provider"] = "fixture_provider"
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "synthetic_or_fixture_execution" in verdict["missing_evidence_reasons"]

    # 4. Receipt hash recomputation mismatch
    record = _valid_record("codeintel", origin="online")
    record["receipt_hash"] = "f" * 64
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "receipt_hash_not_verified" in verdict["missing_evidence_reasons"]
