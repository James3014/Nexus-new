"""P1: LocalAssist → real VAP on UnifiedRuntime main chain (ROUTING FREEZE)."""

from __future__ import annotations

import copy
import pickle
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import patch

import pytest

from nexus.contracts.canonical_execution import CanonicalTaskContext
from nexus.engine.canonical_execution import plan_canonical_task_bundle
from nexus.engine.capability_contracts import CapabilityPlan
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.services import verified_assist_contract as vap_contract
from nexus.services.mainchain_entry import run_mainchain
from nexus.services.online_nexus_context import (
    NEXUS_CODEINTEL_MARKER,
    NEXUS_ROUTE_MARKER,
    build_codeintel_preflight_invoker,
    build_online_nexus_context_from_runtime,
    build_plan_gated_postflight_invokers,
    make_with_nexus_online_invoker,
)
from nexus.services.unified_runtime import (
    UnifiedRuntime,
    UnifiedRuntimeRequest,
    canonical_execution_identity,
    normalize_online_invoker_payload,
)
from nexus.services.verified_assist_contract import (
    build_vap_from_local_receipt,
    build_verified_assist_packet,
    compute_consumption_proof,
    evaluate_assist_credit,
    packet_is_substantive,
    settle_main_chain,
    validate_vap_runtime_binding,
)


class _PlannerWithLocal:
    def plan(self, **_: object) -> CapabilityPlan:
        return CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            selected_capabilities=[
                "local_model_executor",
                "codeintel",
                "artifact_gate",
                "claim_gate",
                "delivery_gate",
            ],
            required_capabilities=["local_model_executor", "codeintel"],
            optional_capabilities=[],
            conditional_capabilities=[],
            pending_capabilities=[],
            forbidden_capabilities=[],
            constraints=["claim_fail_closed"],
            decision_trace=[],
            replan_trace=[],
            score=1.0,
            signal_snapshot={
                "route_truth_source": "CapabilityPlanner",
                "workforce_demands": {
                    "schema": "nexus.workforce_demands.v1",
                    "route_authority": "CapabilityPlanner",
                    "demands": [
                        {
                            "schema": "nexus.workforce_demand.v1",
                            "demand_id": "demand_local",
                            "execution_channel": "local",
                            "requested_role": "bounded_code_candidate",
                            "minimum_autonomy": "L1",
                            "context_class": "nexus_bounded",
                            "mutation_intent": True,
                            "external_verification_required": True,
                            "route_authority": "CapabilityPlanner",
                            "reasons": ["canonical_local_available"],
                        },
                        {
                            "schema": "nexus.workforce_demand.v1",
                            "demand_id": "demand_online",
                            "execution_channel": "online",
                            "requested_role": "main_engineering",
                            "minimum_autonomy": "L3_HISTORICAL",
                            "context_class": "nexus_full",
                            "mutation_intent": True,
                            "external_verification_required": True,
                            "route_authority": "CapabilityPlanner",
                            "reasons": ["canonical_online_available"],
                        },
                    ],
                },
            },
        )


class _LocalService:
    """Mimics LocalAssistService response shape (candidate / executor path)."""

    def handle(self, request: Any) -> dict[str, Any]:
        if hasattr(request, "task_id"):
            task_id = request.task_id
            action = request.action
            target = getattr(request, "target_file", "") or "candidate.py"
        else:
            task_id = request["task_id"]
            action = str(request.get("action") or "candidate")
            target = str(request.get("target_file") or "candidate.py")
        is_executor = action in {"candidate", "verified-subtask"}
        return {
            "schema": "nexus.local_assist.response.v1",
            "task_id": task_id,
            "action": action,
            "local_model_invoked": True,
            "output_delivered": True,
            "executor_invoked": is_executor,
            "physical_callable": "LocalModelExecutor.run" if is_executor else "LocalModelProvider.generate",
            "provider": "ollama",
            "model": "qwen2.5-coder:7b-instruct",
            "provider_call_count": 1,
            "model_call_count": 1,
            "receipt_path": f"/tmp/{task_id}-local.json",
            "evidence_refs": [f"local:{task_id}:invocation"],
            "target_file": target,
            "candidate_summary": {
                "isolation_status": "isolated" if is_executor else "not_run",
                "selected_candidate_hash": "abc123hash",
                "selected_candidate_hash_matches_applied": is_executor,
                "model_candidate_hash": "abc123hash",
            },
            "verifier_summary": {
                "verifier_status": "pass" if action == "verified-subtask" else "not_run",
                "verifier_reached": action == "verified-subtask",
            },
            "local_outputs": {
                "concise_summary": f"action={action};status=succeeded;evidence_count=1",
            },
            "outcome_contributed": True,
        }


def _canonical_workforce_bindings() -> dict[str, dict[str, Any]]:
    return {
        "local": {
            "worker_id": "local_coder_7b",
            "controls": [
                "small_scope",
                "parser",
                "compile",
                "focused_tests",
                "reversible_application",
            ],
        },
        "online": {
            "worker_id": "codex_luna",
            "controls": ["receipt", "independent_verification", "governed_adapter"],
        },
    }


def _canonical_identity(task_id: str) -> dict[str, Any]:
    context = CanonicalTaskContext(
        task_id=task_id,
        task_type="repair",
        task_desc="Bind one verified assist packet to canonical execution.",
        execution_channels=("local", "online"),
        route_features={"bounded_allowed_file_count": 1},
        codeintel={"allowed_files": ["mod.py"]},
    )
    with patch.object(CapabilityPlanner, "plan", lambda _self, **_kwargs: _PlannerWithLocal().plan()):
        bundle = plan_canonical_task_bundle(context)
    return canonical_execution_identity(bundle)


def test_build_vap_from_local_receipt_uses_physical_fields_not_handwritten() -> None:
    resp = _LocalService().handle(
        {
            "task_id": "vap-src-001",
            "action": "candidate",
            "target_file": "mod.py",
        }
    )
    identity = _canonical_identity("vap-src-001")
    pkt = build_vap_from_local_receipt(
        resp,
        planner_decision_id="plan-1",
        plan_hash="plan-1",
        codeintel_hash="ci-1",
        canonical_execution=identity,
        execution_attempt={"attempt_id": "attempt-src-1", "attempt_number": 1},
        source_hash="source-src-1",
        execution_world=str(identity["execution_world"]),
    )
    assert pkt is not None
    assert packet_is_substantive(pkt)
    assert pkt.packet_hash
    assert "LocalModelExecutor.run" in pkt.reproduction_evidence
    assert "mod.py" in pkt.target_files or pkt.target_files
    # Must not smuggle free-text diagnosis labels from pilots
    assert "hand written" not in pkt.bounded_diagnosis.lower()


def test_build_vap_from_local_receipt_requires_runtime_owned_anchors() -> None:
    response = _LocalService().handle({
        "task_id": "vap-src-empty",
        "action": "candidate",
        "target_file": "mod.py",
    })
    assert build_vap_from_local_receipt(response) is None


def test_vap_producer_cross_binds_task_and_world_to_canonical_identity() -> None:
    identity = _canonical_identity("vap-producer-bound")
    response = _LocalService().handle({
        "task_id": "vap-producer-bound",
        "action": "candidate",
        "target_file": "mod.py",
    })
    common = {
        "canonical_execution": identity,
        "execution_attempt": {"attempt_id": "attempt-producer", "attempt_number": 1},
        "source_hash": "source-producer",
        "execution_world": str(identity["execution_world"]),
    }
    assert build_vap_from_local_receipt(response, **common) is not None

    wrong_task = dict(response)
    wrong_task["task_id"] = "other-producer-task"
    assert build_vap_from_local_receipt(wrong_task, **common) is None
    assert build_vap_from_local_receipt(
        response,
        **{**common, "execution_world": "other-product-world"},
    ) is None


def test_vap_runtime_binding_is_identity_bound_and_fail_closed() -> None:
    identity = _canonical_identity("vap-bind-001")
    packet = build_verified_assist_packet(
        task_id="vap-bind-001",
        target_files=("mod.py",),
        bounded_diagnosis="bounded",
        canonical_execution=identity,
        execution_attempt={"attempt_id": "attempt-1", "attempt_number": 1},
        source_hash="source-1",
        execution_world=str(identity["execution_world"]),
    )
    expected = validate_vap_runtime_binding(
        packet,
        task_id="vap-bind-001",
        canonical_execution=identity,
        execution_attempt={"attempt_id": "attempt-1", "attempt_number": 1},
        source_hash="source-1",
        execution_world=str(identity["execution_world"]),
    )
    assert expected["ok"] is True

    tampered = packet.to_dict()
    tampered["source_hash"] = "substituted"
    rejected = validate_vap_runtime_binding(
        tampered,
        task_id="vap-bind-001",
        canonical_execution=identity,
        execution_attempt={"attempt_id": "attempt-1", "attempt_number": 1},
        source_hash="source-1",
        execution_world=str(identity["execution_world"]),
    )
    assert rejected["ok"] is False
    assert rejected["reason"] == "source_hash_mismatch"

    integrity_tampered = packet.to_dict()
    integrity_tampered["bounded_diagnosis"] = "caller forged"
    integrity_rejected = validate_vap_runtime_binding(
        integrity_tampered,
        task_id="vap-bind-001",
        canonical_execution=identity,
        execution_attempt={"attempt_id": "attempt-1", "attempt_number": 1},
        source_hash="source-1",
        execution_world=str(identity["execution_world"]),
    )
    assert integrity_rejected["ok"] is False
    assert integrity_rejected["reason"] == "packet_hash_mismatch"

    for field, value, reason in (
        ("schema_version", None, "packet_schema_version_invalid"),
        ("schema_version", "wrong.schema", "packet_schema_version_invalid"),
        ("packet_role", None, "packet_role_invalid"),
        ("packet_role", "wrong-role", "packet_role_invalid"),
    ):
        noncanonical = packet.to_dict()
        if value is None:
            noncanonical.pop(field)
        else:
            noncanonical[field] = value
        verdict = validate_vap_runtime_binding(
            noncanonical,
            task_id="vap-bind-001",
            canonical_execution=identity,
            execution_attempt={"attempt_id": "attempt-1", "attempt_number": 1},
            source_hash="source-1",
            execution_world=str(identity["execution_world"]),
        )
        assert verdict == {"ok": False, "reason": reason}

    for field, value, reason in (
        ("task_id", "other-task", "task_id_mismatch"),
        ("execution_attempt", {"attempt_id": "other-attempt", "attempt_number": 1}, "execution_attempt_mismatch"),
        ("canonical_execution", {"context_hash": "route-override"}, "canonical_execution_mismatch"),
        ("source_hash", "stale-source", "source_hash_mismatch"),
        ("execution_world", "world-a", "execution_world_mismatch"),
    ):
        mismatched = packet.to_dict()
        mismatched[field] = value
        verdict = validate_vap_runtime_binding(
            mismatched,
            task_id="vap-bind-001",
            canonical_execution=identity,
            execution_attempt={"attempt_id": "attempt-1", "attempt_number": 1},
            source_hash="source-1",
            execution_world=str(identity["execution_world"]),
        )
        assert verdict == {"ok": False, "reason": reason}


def test_vap_runtime_binding_rejects_empty_runtime_owned_anchors() -> None:
    identity = _canonical_identity("vap-empty-anchor")
    packet_defaults: dict[str, Any] = {
        "task_id": "vap-empty-anchor",
        "target_files": ("mod.py",),
        "bounded_diagnosis": "bounded",
        "canonical_execution": identity,
        "execution_attempt": {"attempt_id": "attempt-anchor", "attempt_number": 1},
        "source_hash": "source-anchor",
        "execution_world": str(identity["execution_world"]),
    }
    runtime_defaults: dict[str, Any] = {
        "task_id": "vap-empty-anchor",
        "canonical_execution": identity,
        "execution_attempt": {"attempt_id": "attempt-anchor", "attempt_number": 1},
        "source_hash": "source-anchor",
        "execution_world": str(identity["execution_world"]),
    }
    cases = (
        ({}, {"task_id": ""}, "task_id_missing"),
        (
            {"canonical_execution": {}},
            {"canonical_execution": {}},
            "canonical_execution_missing",
        ),
        (
            {"execution_attempt": {}},
            {"execution_attempt": {}},
            "execution_attempt_missing",
        ),
        ({"source_hash": ""}, {"source_hash": ""}, "source_hash_missing"),
        (
            {"execution_world": ""},
            {"execution_world": ""},
            "execution_world_missing",
        ),
    )
    for packet_overrides, runtime_overrides, reason in cases:
        packet_values = {**packet_defaults, **packet_overrides}
        runtime_values = {**runtime_defaults, **runtime_overrides}
        packet = build_verified_assist_packet(**packet_values)
        verdict = validate_vap_runtime_binding(packet, **runtime_values)
        assert verdict == {"ok": False, "reason": reason}


def test_runtime_raw_task_and_world_must_match_canonical_identity() -> None:
    identity = _canonical_identity("vap-runtime-canonical")
    attempt = {"attempt_id": "attempt-runtime-canonical", "attempt_number": 1}
    for task_id, world, reason in (
        (
            "other-runtime-task",
            str(identity["execution_world"]),
            "runtime_task_canonical_mismatch",
        ),
        (
            "vap-runtime-canonical",
            "other-product-world",
            "runtime_world_canonical_mismatch",
        ),
    ):
        packet = build_verified_assist_packet(
            task_id=task_id,
            target_files=("mod.py",),
            bounded_diagnosis="bounded",
            canonical_execution=identity,
            execution_attempt=attempt,
            source_hash="source-runtime-canonical",
            execution_world=world,
        )
        verdict = validate_vap_runtime_binding(
            packet,
            task_id=task_id,
            canonical_execution=identity,
            execution_attempt=attempt,
            source_hash="source-runtime-canonical",
            execution_world=world,
        )
        assert verdict == {"ok": False, "reason": reason}


def test_live_mint_provenance_is_content_bound_and_not_copyable() -> None:
    identity = _canonical_identity("vap-live-mint")
    attempt = {"attempt_id": "attempt-live-mint", "attempt_number": 1}
    packet = build_verified_assist_packet(
        task_id="vap-live-mint",
        target_files=("mod.py",),
        bounded_diagnosis="bounded",
        canonical_execution=identity,
        execution_attempt=attempt,
        source_hash="source-live-mint",
        execution_world=str(identity["execution_world"]),
    )
    fragment = packet.compact_injection()
    record = vap_contract._mint_packet_consumption(
        packet,
        runtime_task_id="vap-live-mint",
        runtime_canonical_execution=identity,
        runtime_execution_attempt=attempt,
        runtime_source_hash="source-live-mint",
        runtime_execution_world=str(identity["execution_world"]),
        injected_prompt_fragment=fragment,
        expected_packet_hash=packet.packet_hash,
        final_prompt="provider input\n" + fragment,
    )
    assert evaluate_assist_credit(record)["assist_credited"] is True

    other_identity = _canonical_identity("vap-live-mint-other")
    base_mint_kwargs = {
        "runtime_task_id": "vap-live-mint",
        "runtime_canonical_execution": identity,
        "runtime_execution_attempt": attempt,
        "runtime_source_hash": "source-live-mint",
        "runtime_execution_world": str(identity["execution_world"]),
    }
    for field, value, reason in (
        (
            "runtime_task_id",
            "other-task",
            "runtime_task_canonical_mismatch",
        ),
        (
            "runtime_canonical_execution",
            other_identity,
            "runtime_task_canonical_mismatch",
        ),
        (
            "runtime_execution_attempt",
            {"attempt_id": "other-attempt", "attempt_number": 1},
            "execution_attempt_mismatch",
        ),
        ("runtime_source_hash", "other-source", "source_hash_mismatch"),
        (
            "runtime_execution_world",
            "other-product-world",
            "runtime_world_canonical_mismatch",
        ),
    ):
        rejected = vap_contract._mint_packet_consumption(
            packet,
            **{**base_mint_kwargs, field: value},
            injected_prompt_fragment=fragment,
            expected_packet_hash=packet.packet_hash,
            final_prompt="provider input\n" + fragment,
        )
        assert rejected.consumption_status == "blocked"
        assert rejected.reason == f"runtime_binding_invalid:{reason}"
        rejected_credit = evaluate_assist_credit(rejected)
        assert rejected_credit["physical_proof_ok"] is False
        assert rejected_credit["assist_credited"] is False
        assert settle_main_chain(
            treatment_run_id="run-rejected-anchor",
            consumption=rejected,
        )["claim_boundary"]["assist_contributed"] is False

    forged_fields = {
        "packet_hash": "a" * 64,
        "packet_id": "vap-forged-copy",
        "consumer_stage": record.consumer_stage,
        "injection_slot": record.injection_slot,
        "allowed_fields_hash": "b" * 64,
        "assembled_fragment_hash": "c" * 64,
        "final_prompt_hash": "d" * 64,
    }
    forged = replace(
        record,
        **forged_fields,
        consumption_proof=compute_consumption_proof(**forged_fields),
    )
    copies = (
        forged,
        copy.copy(record),
        copy.deepcopy(record),
        pickle.loads(pickle.dumps(record)),
    )
    for candidate in copies:
        assert evaluate_assist_credit(candidate)["assist_credited"] is False
        settlement = settle_main_chain(
            treatment_run_id="run-forged-copy",
            consumption=candidate,
        )
        assert settlement["claim_boundary"]["assist_contributed"] is False


def test_tampered_vap_is_not_forwarded_to_online_prompt() -> None:
    identity = _canonical_identity("vap-bind-002")
    packet = build_verified_assist_packet(
        task_id="vap-bind-002",
        target_files=("mod.py",),
        bounded_diagnosis="bounded",
        canonical_execution=identity,
        execution_attempt={"attempt_id": "attempt-2", "attempt_number": 1},
        source_hash="source-2",
        execution_world=str(identity["execution_world"]),
    ).to_dict()
    packet["execution_attempt"] = {"attempt_id": "substituted", "attempt_number": 1}
    with pytest.raises(ValueError, match="execution_attempt_mismatch"):
        build_online_nexus_context_from_runtime(
            {
                "task_id": "vap-bind-002",
                "task_statement": "use local evidence",
                "task_type": "repair",
                "online_prompt": "online body",
                "source_hash": "source-2",
                "canonical_execution": identity,
                "execution_attempt": {"attempt_id": "attempt-2", "attempt_number": 1},
                "local": {"invoked": True, "response": {"task_id": "vap-bind-002", "verified_assist_packet": packet}},
                "planner": {},
            }
        )


def test_declared_vap_without_packet_blocks_before_online_provider() -> None:
    calls: list[Mapping[str, Any]] = []

    def base(context: Mapping[str, Any]) -> dict[str, Any]:
        calls.append(context)
        return {"response": "must not run"}

    invoker = make_with_nexus_online_invoker(base, provider="fixture")
    with pytest.raises(ValueError, match="vap_runtime_binding_failed|packet"):
        invoker(
            {
                "task_id": "vap-bind-003",
                "task_statement": "declared local evidence",
                "task_type": "repair",
                "online_prompt": "online body",
                "source_hash": "source-3",
                "canonical_execution": {"context_hash": "ctx-3", "execution_world": "world-c"},
                "execution_attempt": {"attempt_id": "attempt-3", "attempt_number": 1},
                "local": {
                    "invoked": True,
                    "response": {
                        "task_id": "vap-bind-003",
                        "consume_verified_assist": True,
                    },
                },
            }
        )
    assert calls == []


def test_expected_packet_hash_substitution_blocks_before_online_provider() -> None:
    calls: list[Mapping[str, Any]] = []

    def base(context: Mapping[str, Any]) -> dict[str, Any]:
        calls.append(context)
        return {"response": "must not run"}

    packet = build_verified_assist_packet(
        task_id="vap-bind-004",
        target_files=("mod.py",),
        bounded_diagnosis="bounded",
        canonical_execution={"context_hash": "ctx-id-ok"},
        execution_attempt={"attempt_id": "attempt-id-ok", "attempt_number": 1},
        source_hash="source-4",
        execution_world="product_runtime",
    ).to_dict()
    invoker = make_with_nexus_online_invoker(base, provider="fixture")
    with pytest.raises(ValueError, match="packet_hash_substitution"):
        invoker(
            {
                "task_id": "vap-bind-004",
                "task_statement": "substituted packet",
                "task_type": "repair",
                "online_prompt": "online body",
                "source_hash": "source-4",
                "local": {
                    "invoked": True,
                    "verified_assist_packet_expected_hash": "expected-runtime-hash",
                    "response": {"task_id": "vap-bind-004", "verified_assist_packet": packet},
                },
            }
        )
    assert calls == []


def test_expected_packet_id_substitution_blocks_before_online_provider() -> None:
    calls: list[Mapping[str, Any]] = []

    def custom(context: Mapping[str, Any]) -> dict[str, Any]:
        calls.append(context)
        return {"response": "must not run"}

    identity = _canonical_identity("vap-bind-id")
    packet = build_verified_assist_packet(
        task_id="vap-bind-id",
        packet_id="runtime-id",
        target_files=("mod.py",),
        bounded_diagnosis="bounded",
        canonical_execution=identity,
        execution_attempt={"attempt_id": "attempt-id-ok", "attempt_number": 1},
        source_hash="source-id",
        execution_world=str(identity["execution_world"]),
    ).to_dict()
    stage = {
        "invoked": True,
        "verified_assist_packet_expected_hash": packet["packet_hash"],
        "verified_assist_packet_id": "substituted-id",
        "response": {"task_id": "vap-bind-id", "verified_assist_packet": packet},
    }
    request = UnifiedRuntimeRequest(
        task_id="vap-bind-id",
        workspace_revision="rev-id",
        task_statement="packet id substitution",
        task_type="repair",
        route={},
        online_enabled=True,
    )
    result = UnifiedRuntime._run_online(
        request,
        custom,
        {
            "task_id": request.task_id,
            "local": stage,
            "source_hash": "source-id",
            "canonical_execution": identity,
            "execution_attempt": {"attempt_id": "attempt-id-ok", "attempt_number": 1},
        },
    )
    assert result["status"] == "FAILED"
    assert result["response"]["provider_call_count"] == 0
    assert calls == []


def test_runtime_owned_custom_packet_id_is_accepted() -> None:
    identity = _canonical_identity("vap-bind-id-ok")
    packet = build_verified_assist_packet(
        task_id="vap-bind-id-ok",
        packet_id="runtime-custom-id",
        target_files=("mod.py",),
        bounded_diagnosis="bounded",
        canonical_execution=identity,
        execution_attempt={"attempt_id": "attempt-id-ok", "attempt_number": 1},
        source_hash="source-id-ok",
        execution_world=str(identity["execution_world"]),
    ).to_dict()
    calls: list[Mapping[str, Any]] = []

    def custom(context: Mapping[str, Any]) -> dict[str, Any]:
        calls.append(context)
        return {"task_id": context["task_id"], "invoked": True, "output_delivered": True, "gate_passed": True}

    request = UnifiedRuntimeRequest(
        task_id="vap-bind-id-ok",
        workspace_revision="rev-id-ok",
        task_statement="packet id accepted",
        task_type="repair",
        route={},
        online_enabled=True,
    )
    result = UnifiedRuntime._run_online(
        request,
        custom,
        {
            "task_id": request.task_id,
            "local": {
                "invoked": True,
                "verified_assist_packet_expected_hash": packet["packet_hash"],
                "verified_assist_packet_id": "runtime-custom-id",
                "response": {"task_id": request.task_id, "verified_assist_packet": packet},
            },
            "source_hash": "source-id-ok",
            "canonical_execution": identity,
            "execution_attempt": {"attempt_id": "attempt-id-ok", "attempt_number": 1},
        },
    )
    assert result["invoked"] is True
    assert len(calls) == 1


def test_runtime_preprovider_gate_blocks_custom_invoker_for_missing_vap() -> None:
    calls: list[Mapping[str, Any]] = []

    def custom(context: Mapping[str, Any]) -> dict[str, Any]:
        calls.append(context)
        return {"task_id": context["task_id"], "response": "must not run"}

    request = UnifiedRuntimeRequest(
        task_id="vap-bind-005",
        workspace_revision="rev-5",
        task_statement="missing declared packet",
        task_type="repair",
        route={},
        online_enabled=True,
    )
    stage = UnifiedRuntime._run_online(
        request,
        custom,
        {
            "task_id": request.task_id,
            "local": {
                "invoked": True,
                "response": {"task_id": request.task_id, "consume_verified_assist": True},
            },
            "source_hash": "source-5",
            "canonical_execution": {},
            "execution_attempt": {},
        },
    )
    assert stage["status"] == "FAILED"
    assert stage["invoked"] is False
    assert stage["response"]["provider_call_count"] == 0
    assert calls == []


def test_runtime_preprovider_gate_preserves_online_only_custom_invoker() -> None:
    calls: list[Mapping[str, Any]] = []

    def custom(context: Mapping[str, Any]) -> dict[str, Any]:
        calls.append(context)
        return {
            "task_id": context["task_id"],
            "invoked": True,
            "output_delivered": True,
            "gate_passed": True,
            "evidence_refs": ["online:ordinary"],
        }

    request = UnifiedRuntimeRequest(
        task_id="vap-bind-006",
        workspace_revision="rev-6",
        task_statement="ordinary online only",
        task_type="content",
        route={},
        online_enabled=True,
    )
    stage = UnifiedRuntime._run_online(request, custom, {"task_id": request.task_id})
    assert stage["invoked"] is True
    assert len(calls) == 1


def _receipt_for_nested_verifier_binding() -> dict[str, Any]:
    stage = {
        "status": "SUCCEEDED",
        "invoked": True,
        "evidence_present": True,
        "gate_passed": True,
        "evidence_refs": ["stage:evidence"],
        "outcome_contributed": True,
    }
    return {
        "schema": "nexus.unified_runtime.receipt.v1",
        "task_id": "vap-bind-final",
        "planner_decision_id": "planner-final",
        "execution_depth": "LIGHT",
        "execution_attempt": {"attempt_id": "attempt-final", "attempt_number": 1},
        "context_trace": {},
        "planner": dict(stage),
        "local": {**stage, "substitution_trace": {"online_consumed": True}},
        "online": dict(stage),
        "stages": [],
        "capability_results": {},
        "capability_evidence_bundle": {"source_hash": "source-final"},
        "verified_assist": {"credit": {"assist_credited": True}},
        "claim_boundary": {},
        "evidence_refs": ["stage:evidence"],
    }


@pytest.mark.parametrize("local_stage", [{"status": "NOT_REQUESTED"}, {}])
def test_online_only_or_not_requested_local_does_not_require_vap_credit(
    local_stage: dict[str, Any],
) -> None:
    receipt = _receipt_for_nested_verifier_binding()
    receipt["local"] = local_stage
    receipt.pop("verified_assist", None)
    finalized = UnifiedRuntime().finalize_receipt(
        receipt,
        verifier={
            "task_id": receipt["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["verifier:evidence"],
            "response": {
                "task_id": receipt["task_id"],
                "attempt_id": "attempt-final",
                "source_hash": "source-final",
            },
        },
        learning={"task_id": receipt["task_id"], "invoked": True, "gate_passed": True, "evidence_refs": ["learning:evidence"]},
    )
    assert finalized["claim_boundary"]["outcome_contributed"] is True


def test_invoked_local_vap_without_physical_credit_stays_false() -> None:
    receipt = _receipt_for_nested_verifier_binding()
    receipt.pop("verified_assist", None)
    receipt["local"]["verified_assist_packet_expected_hash"] = "expected"
    finalized = UnifiedRuntime().finalize_receipt(
        receipt,
        verifier={
            "task_id": receipt["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["verifier:evidence"],
            "response": {
                "task_id": receipt["task_id"],
                "attempt_id": "attempt-final",
                "source_hash": "source-final",
            },
        },
        learning={"task_id": receipt["task_id"], "invoked": True, "gate_passed": True, "evidence_refs": ["learning:evidence"]},
    )
    assert finalized["claim_boundary"]["outcome_contributed"] is False
    assert finalized["local"]["substitution_trace"]["final_outcome_contributed"] is False
@pytest.mark.parametrize(
    "response_overrides",
    [
        {"task_id": "other-task"},
        {"task_id": ""},
        {"attempt_id": "other-attempt"},
        {"attempt_id": ""},
        {"source_hash": "other-source"},
        {"source_hash": ""},
    ],
)
def test_nested_verifier_identity_binding_is_required_for_final_contribution(
    response_overrides: dict[str, str],
) -> None:
    receipt = _receipt_for_nested_verifier_binding()
    response = {
        "task_id": "vap-bind-final",
        "attempt_id": "attempt-final",
        "source_hash": "source-final",
    }
    response.update(response_overrides)
    verifier = {
        "task_id": "vap-bind-final",
        "invoked": True,
        "gate_passed": True,
        "evidence_refs": ["verifier:evidence"],
        "response": response,
    }
    finalized = UnifiedRuntime().finalize_receipt(
        receipt,
        verifier=verifier,
        learning={"task_id": "vap-bind-final", "invoked": True, "gate_passed": True, "evidence_refs": ["learning:evidence"]},
    )
    assert finalized["claim_boundary"]["outcome_contributed"] is False
    assert finalized["local"]["substitution_trace"]["final_outcome_contributed"] is False


def test_nested_verifier_exact_task_binding_allows_final_contribution() -> None:
    receipt = _receipt_for_nested_verifier_binding()
    verifier = {
        "task_id": "vap-bind-final",
        "invoked": True,
        "gate_passed": True,
        "evidence_refs": ["verifier:evidence"],
        "response": {
            "task_id": "vap-bind-final",
            "attempt_id": "attempt-final",
            "source_hash": "source-final",
        },
    }
    finalized = UnifiedRuntime().finalize_receipt(
        receipt,
        verifier=verifier,
        learning={"task_id": "vap-bind-final", "invoked": True, "gate_passed": True, "evidence_refs": ["learning:evidence"]},
    )
    assert finalized["claim_boundary"]["outcome_contributed"] is True


@pytest.mark.parametrize(
    (
        "nested_verifier_task_id",
        "nested_verifier_attempt_id",
        "nested_verifier_source_hash",
        "expected_contribution",
    ),
    [
        ("p1-main-001", None, None, True),
        ("wrong-task", None, None, False),
        ("p1-main-001", "wrong-attempt", None, False),
        ("p1-main-001", None, "wrong-source", False),
    ],
)
def test_unified_runtime_local_produces_vap_and_bd_fingerprints_matrix(
    tmp_path: Path,
    nested_verifier_task_id: str,
    nested_verifier_attempt_id: str | None,
    nested_verifier_source_hash: str | None,
    expected_contribution: bool,
) -> None:
    captured: dict[str, str] = {}

    def base_online(context: Mapping[str, Any]) -> dict[str, Any]:
        captured["prompt"] = str(context.get("online_prompt") or "")
        return normalize_online_invoker_payload(
            provider="codex",
            task_id=str(context["task_id"]),
            invoked=True,
            output_delivered=True,
            gate_passed=True,
            provider_call_count=1,
            response={"status": "ok", "arm": "nexus+local"},
            raw_response="ok",
            evidence_refs=[f"online:{context['task_id']}:base"],
        )

    base_online.provider = "codex"  # type: ignore[attr-defined]
    base_online.online_invoker_provider = "codex"  # type: ignore[attr-defined]

    codeintel = {
        "scan_report_present": True,
        "impact_report_present": True,
        "risk_score": 5,
        "impacted_files_count": 1,
    }
    req = UnifiedRuntimeRequest(
        task_id="p1-main-001",
        workspace_revision="rev-p1",
        task_statement="repair parse_kv with local model executor",
        task_type="repair",
        route={
            "recommended_flow": "hybrid",
            "local_enabled": True,
            "injected_transport": True,
            "online_policy": "auto",
            "workforce_bindings": _canonical_workforce_bindings(),
        },
        online_enabled=True,
        local_enabled=True,
        online_prompt="online task body",
        codeintel=codeintel,
        local_request={
            "task_id": "p1-main-001",
            "action": "candidate",
            "target_file": "parse_kv.py",
            "planner_snapshot": {
                "route_truth_source": "CapabilityPlanner",
                "executor_provider": "ollama",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "model_call_allowed": True,
                "execution_topology": "local_only",
            },
        },
    )
    invokers = {
        "codeintel": build_codeintel_preflight_invoker(codeintel=codeintel),
        **build_plan_gated_postflight_invokers(),
    }
    with patch.object(CapabilityPlanner, "plan", lambda _self, **_kwargs: _PlannerWithLocal().plan()):
        receipt = run_mainchain(
            req,
            online_invoker=base_online,
            local_service=_LocalService(),
            capability_invokers=invokers,
            verifier=lambda c: {
            "task_id": c["task_id"],
            "invoked": True,
            "gate_passed": True,
            "attempt_id": c["execution_attempt"]["attempt_id"],
            "source_hash": c["source_hash"],
            "response": {
                "task_id": nested_verifier_task_id,
                "attempt_id": (
                    nested_verifier_attempt_id
                    if nested_verifier_attempt_id is not None
                    else c["execution_attempt"]["attempt_id"]
                ),
                "source_hash": (
                    nested_verifier_source_hash
                    if nested_verifier_source_hash is not None
                    else c["source_hash"]
                ),
            },
            "evidence_refs": [f"verifier:{c['task_id']}"],
            },
            learning=lambda c: {
            "task_id": c["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"learning:{c['task_id']}"],
            },
            receipt_path=tmp_path / "p1_receipt.json",
        )

    assert receipt["local"]["invoked"] is True
    assert receipt["local"]["status"] == "SUCCEEDED"
    local_resp = receipt["local"]["response"]
    assert local_resp.get("verified_assist_packet")
    packet_hash = local_resp["verified_assist_packet"]["packet_hash"]
    assert packet_hash
    assert receipt["context_trace"]["online_received_context"]["vap_attached"] is True
    assert receipt["context_trace"]["online_received_context"]["vap_packet_hash"] == packet_hash

    # Local physical callable / executor path
    local_cap = next(c for c in receipt["capabilities"] if c["name"] == "local_model_executor")
    assert local_cap["status"] == "INVOKED"
    assert local_cap["physical_callable"] == "LocalModelExecutor.run"

    # with_nexus sections present
    assert NEXUS_ROUTE_MARKER in captured["prompt"]
    assert NEXUS_CODEINTEL_MARKER in captured["prompt"]
    assert packet_hash[:16] in captured["prompt"] or f"[VAP]{packet_hash}" in captured["prompt"]

    # B/D fingerprints share plan+codeintel core
    assert receipt["treatment_core_equal"]["equal"] is True
    assert receipt["treatment_fingerprint_b"]["assist_packet_attached"] is False
    assert receipt["treatment_fingerprint_d"]["assist_packet_attached"] is True
    assert receipt["claim_boundary"]["public_claim_allowed"] is False

    # VAP consumption credit on main chain
    va = receipt.get("verified_assist") or {}
    assert va.get("packet", {}).get("packet_hash") == packet_hash
    assert va.get("credit", {}).get("assist_credited") is True
    assert receipt["local"]["substitution_trace"]["online_consumed"] is True
    assert receipt["claim_boundary"]["outcome_contributed"] is expected_contribution
    assert (
        receipt["local"]["substitution_trace"]["final_outcome_contributed"]
        is expected_contribution
    )

    # P2: plan-selected gates invoked
    assert "codeintel" in receipt["capability_results"]
    assert receipt["capability_results"]["codeintel"]["invoked"] is True
    for gate in ("artifact_gate", "claim_gate", "delivery_gate"):
        assert gate in receipt["capability_results"], gate
        assert receipt["capability_results"][gate]["invoked"] is True
        assert receipt["capability_results"][gate]["evidence_refs"]


def test_unified_runtime_local_produces_vap_and_bd_fingerprints(tmp_path: Path) -> None:
    """Retain the pre-matrix node id for exact-base impact comparison."""

    test_unified_runtime_local_produces_vap_and_bd_fingerprints_matrix(
        tmp_path,
        "p1-main-001",
        None,
        None,
        True,
    )


@pytest.mark.parametrize("provider_prompt", ["provider input without local evidence", ""])
def test_custom_online_prompt_without_vap_cannot_receive_consumption_credit(
    tmp_path: Path,
    provider_prompt: str,
) -> None:
    captured: dict[str, str] = {}

    def custom_online(context: Mapping[str, Any]) -> dict[str, Any]:
        captured["prompt"] = str(context.get("online_prompt") or "")
        return normalize_online_invoker_payload(
            provider="codex",
            task_id=str(context["task_id"]),
            invoked=True,
            output_delivered=True,
            gate_passed=True,
            provider_call_count=1,
            response={"status": "ok", "arm": "custom-without-vap"},
            raw_response="ok",
            evidence_refs=[f"online:{context['task_id']}:custom"],
        )

    custom_online.provider = "codex"  # type: ignore[attr-defined]
    custom_online.online_invoker_provider = "codex"  # type: ignore[attr-defined]

    codeintel = {
        "scan_report_present": True,
        "impact_report_present": True,
        "risk_score": 5,
        "impacted_files_count": 1,
    }
    request = UnifiedRuntimeRequest(
        task_id="p1-custom-no-vap",
        workspace_revision="rev-custom-no-vap",
        task_statement="repair parse_kv without VAP forwarding",
        task_type="repair",
        route={
            "recommended_flow": "hybrid",
            "local_enabled": True,
            "injected_transport": True,
            "online_policy": "auto",
            "workforce_bindings": _canonical_workforce_bindings(),
        },
        online_enabled=True,
        local_enabled=True,
        online_prompt=provider_prompt,
        codeintel=codeintel,
        local_request={
            "task_id": "p1-custom-no-vap",
            "action": "candidate",
            "target_file": "parse_kv.py",
            "planner_snapshot": {
                "route_truth_source": "CapabilityPlanner",
                "executor_provider": "ollama",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "model_call_allowed": True,
                "execution_topology": "local_only",
            },
        },
    )
    invokers = {
        "codeintel": build_codeintel_preflight_invoker(codeintel=codeintel),
        **build_plan_gated_postflight_invokers(),
    }
    with patch.object(CapabilityPlanner, "plan", lambda _self, **_kwargs: _PlannerWithLocal().plan()):
        receipt = run_mainchain(
            request,
            online_invoker=custom_online,
            local_service=_LocalService(),
            capability_invokers=invokers,
            verifier=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "attempt_id": context["execution_attempt"]["attempt_id"],
            "source_hash": context["source_hash"],
            "response": {
                "task_id": context["task_id"],
                "attempt_id": context["execution_attempt"]["attempt_id"],
                "source_hash": context["source_hash"],
            },
            "evidence_refs": [f"verifier:{context['task_id']}"],
            },
            learning=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"learning:{context['task_id']}"],
            },
            receipt_path=tmp_path / "custom_no_vap_receipt.json",
            with_nexus_armor=False,
        )

    packet_hash = receipt["local"]["response"]["verified_assist_packet"]["packet_hash"]
    assert packet_hash
    assert "[VAP]" not in captured["prompt"]
    consumption = receipt["verified_assist"]["consumption"]
    credit = receipt["verified_assist"]["credit"]
    assert consumption["consumption_status"] != "consumed"
    assert credit["physical_proof_ok"] is False
    assert credit["assist_credited"] is False
    assert receipt["local"]["substitution_trace"]["online_consumed"] is False
    assert receipt["local"]["substitution_trace"]["final_outcome_contributed"] is False
    assert receipt["claim_boundary"]["outcome_contributed"] is False


def test_bare_online_without_local_has_no_vap() -> None:
    def bare(context: Mapping[str, Any]) -> dict[str, Any]:
        return normalize_online_invoker_payload(
            provider="fixture",
            task_id=context["task_id"],
            invoked=True,
            output_delivered=True,
            gate_passed=True,
            provider_call_count=1,
            response={"ok": True},
            raw_response="ok",
            evidence_refs=[f"online:{context['task_id']}"],
        )

    req = UnifiedRuntimeRequest(
        task_id="p1-bare-001",
        workspace_revision="rev-p1",
        task_statement="simple online only",
        task_type="content",
        route={"recommended_flow": "direct", "injected_transport": True, "online_policy": "auto"},
        online_enabled=True,
        local_enabled=False,
        online_prompt="bare only",
    )
    receipt = UnifiedRuntime().run(
        req,
        online_invoker=bare,
        verifier=lambda c: {
            "task_id": c["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"v:{c['task_id']}"],
        },
        learning=lambda c: {
            "task_id": c["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"l:{c['task_id']}"],
        },
    )
    assert receipt["context_trace"]["online_received_context"].get("vap_attached") is False
    assert not receipt.get("verified_assist")
