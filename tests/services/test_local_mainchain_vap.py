"""P1: LocalAssist → real VAP on UnifiedRuntime main chain (ROUTING FREEZE)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nexus.engine.capability_contracts import CapabilityPlan
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
    normalize_online_invoker_payload,
)
from nexus.services.verified_assist_contract import (
    build_vap_from_local_receipt,
    build_verified_assist_packet,
    packet_is_substantive,
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
            signal_snapshot={"route_truth_source": "CapabilityPlanner"},
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
            "task_id": task_id,
            "action": action,
            "local_model_invoked": True,
            "output_delivered": True,
            "executor_invoked": is_executor,
            "physical_callable": "LocalModelExecutor.run" if is_executor else "LocalModelProvider.generate",
            "provider": "injected",
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


def test_build_vap_from_local_receipt_uses_physical_fields_not_handwritten() -> None:
    resp = _LocalService().handle(
        {
            "task_id": "vap-src-001",
            "action": "candidate",
            "target_file": "mod.py",
        }
    )
    pkt = build_vap_from_local_receipt(
        resp,
        planner_decision_id="plan-1",
        plan_hash="plan-1",
        codeintel_hash="ci-1",
    )
    assert pkt is not None
    assert packet_is_substantive(pkt)
    assert pkt.packet_hash
    assert "LocalModelExecutor.run" in pkt.reproduction_evidence
    assert "mod.py" in pkt.target_files or pkt.target_files
    # Must not smuggle free-text diagnosis labels from pilots
    assert "hand written" not in pkt.bounded_diagnosis.lower()


def test_vap_runtime_binding_is_identity_bound_and_fail_closed() -> None:
    packet = build_verified_assist_packet(
        task_id="vap-bind-001",
        target_files=("mod.py",),
        bounded_diagnosis="bounded",
        canonical_execution={"context_hash": "ctx-1", "decision_hash": "dec-1"},
        execution_attempt={"attempt_id": "attempt-1", "attempt_number": 1},
        source_hash="source-1",
        execution_world="world-c",
    )
    expected = validate_vap_runtime_binding(
        packet,
        task_id="vap-bind-001",
        canonical_execution={"context_hash": "ctx-1", "decision_hash": "dec-1"},
        execution_attempt={"attempt_id": "attempt-1", "attempt_number": 1},
        source_hash="source-1",
        execution_world="world-c",
    )
    assert expected["ok"] is True

    tampered = packet.to_dict()
    tampered["source_hash"] = "substituted"
    rejected = validate_vap_runtime_binding(
        tampered,
        task_id="vap-bind-001",
        canonical_execution={"context_hash": "ctx-1", "decision_hash": "dec-1"},
        execution_attempt={"attempt_id": "attempt-1", "attempt_number": 1},
        source_hash="source-1",
        execution_world="world-c",
    )
    assert rejected["ok"] is False
    assert rejected["reason"] == "source_hash_mismatch"

    integrity_tampered = packet.to_dict()
    integrity_tampered["bounded_diagnosis"] = "caller forged"
    integrity_rejected = validate_vap_runtime_binding(
        integrity_tampered,
        task_id="vap-bind-001",
        canonical_execution={"context_hash": "ctx-1", "decision_hash": "dec-1"},
        execution_attempt={"attempt_id": "attempt-1", "attempt_number": 1},
        source_hash="source-1",
        execution_world="world-c",
    )
    assert integrity_rejected["ok"] is False
    assert integrity_rejected["reason"] == "packet_hash_mismatch"

    for field, value, reason in (
        ("task_id", "other-task", "task_id_mismatch"),
        ("execution_attempt", {"attempt_id": "other-attempt", "attempt_number": 1}, "execution_attempt_mismatch"),
        ("canonical_execution", {"context_hash": "route-override"}, "canonical_execution_mismatch"),
        ("source_hash", "stale-source", "source_hash_mismatch"),
    ):
        mismatched = packet.to_dict()
        mismatched[field] = value
        verdict = validate_vap_runtime_binding(
            mismatched,
            task_id="vap-bind-001",
            canonical_execution={"context_hash": "ctx-1", "decision_hash": "dec-1"},
            execution_attempt={"attempt_id": "attempt-1", "attempt_number": 1},
            source_hash="source-1",
            execution_world="world-c",
        )
        assert verdict == {"ok": False, "reason": reason}


def test_tampered_vap_is_not_forwarded_to_online_prompt() -> None:
    packet = build_verified_assist_packet(
        task_id="vap-bind-002",
        target_files=("mod.py",),
        bounded_diagnosis="bounded",
        canonical_execution={"context_hash": "ctx-2", "execution_world": "world-c"},
        execution_attempt={"attempt_id": "attempt-2", "attempt_number": 1},
        source_hash="source-2",
        execution_world="world-c",
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
                "canonical_execution": {"context_hash": "ctx-2", "execution_world": "world-c"},
                "execution_attempt": {"attempt_id": "attempt-2", "attempt_number": 1},
                "local": {"invoked": True, "response": {"task_id": "vap-bind-002", "verified_assist_packet": packet}},
                "planner": {},
            }
        )


def test_declared_vap_without_packet_blocks_before_online_provider() -> None:
    calls: list[dict[str, Any]] = []

    def base(context: dict[str, Any]) -> dict[str, Any]:
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
    calls: list[dict[str, Any]] = []

    def base(context: dict[str, Any]) -> dict[str, Any]:
        calls.append(context)
        return {"response": "must not run"}

    packet = build_verified_assist_packet(
        task_id="vap-bind-004",
        target_files=("mod.py",),
        bounded_diagnosis="bounded",
        canonical_execution={},
        execution_attempt={},
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
    calls: list[dict[str, Any]] = []

    def custom(context: dict[str, Any]) -> dict[str, Any]:
        calls.append(context)
        return {"response": "must not run"}

    packet = build_verified_assist_packet(
        task_id="vap-bind-id",
        packet_id="runtime-id",
        target_files=("mod.py",),
        bounded_diagnosis="bounded",
        canonical_execution={},
        execution_attempt={},
        source_hash="source-id",
        execution_world="product_runtime",
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
            "canonical_execution": {},
            "execution_attempt": {},
        },
    )
    assert result["status"] == "FAILED"
    assert result["response"]["provider_call_count"] == 0
    assert calls == []


def test_runtime_owned_custom_packet_id_is_accepted() -> None:
    packet = build_verified_assist_packet(
        task_id="vap-bind-id-ok",
        packet_id="runtime-custom-id",
        target_files=("mod.py",),
        bounded_diagnosis="bounded",
        canonical_execution={},
        execution_attempt={},
        source_hash="source-id-ok",
        execution_world="product_runtime",
    ).to_dict()
    calls: list[dict[str, Any]] = []

    def custom(context: dict[str, Any]) -> dict[str, Any]:
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
            "canonical_execution": {},
            "execution_attempt": {},
        },
    )
    assert result["invoked"] is True
    assert len(calls) == 1


def test_runtime_preprovider_gate_blocks_custom_invoker_for_missing_vap() -> None:
    calls: list[dict[str, Any]] = []

    def custom(context: dict[str, Any]) -> dict[str, Any]:
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
    calls: list[dict[str, Any]] = []

    def custom(context: dict[str, Any]) -> dict[str, Any]:
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
@pytest.mark.parametrize("nested_task_id", ["other-task", ""])
def test_nested_verifier_task_binding_is_required_for_final_contribution(
    nested_task_id: str,
) -> None:
    receipt = _receipt_for_nested_verifier_binding()
    verifier = {
        "task_id": "vap-bind-final",
        "invoked": True,
        "gate_passed": True,
        "evidence_refs": ["verifier:evidence"],
        "response": {
            "task_id": nested_task_id,
            "attempt_id": "attempt-final",
            "source_hash": "source-final",
        },
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


@pytest.mark.parametrize("nested_verifier_task_id", ["p1-main-001", "wrong-task", ""])
def test_unified_runtime_local_produces_vap_and_bd_fingerprints_matrix(
    tmp_path: Path,
    nested_verifier_task_id: str,
) -> None:
    captured: dict[str, str] = {}

    def base_online(context: dict[str, Any]) -> dict[str, Any]:
        captured["prompt"] = str(context.get("online_prompt") or "")
        return normalize_online_invoker_payload(
            provider="fixture",
            task_id=str(context["task_id"]),
            invoked=True,
            output_delivered=True,
            gate_passed=True,
            provider_call_count=1,
            response={"status": "ok", "arm": "nexus+local"},
            raw_response="ok",
            evidence_refs=[f"online:{context['task_id']}:base"],
        )

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
    receipt = UnifiedRuntime(planner=_PlannerWithLocal(), local_service=_LocalService()).run(
        req,
        online_invoker=make_with_nexus_online_invoker(base_online, provider="fixture"),
        capability_invokers=invokers,
        verifier=lambda c: {
            "task_id": c["task_id"],
            "invoked": True,
            "gate_passed": True,
            "attempt_id": c["execution_attempt"]["attempt_id"],
            "source_hash": c["source_hash"],
            "response": {
                "task_id": nested_verifier_task_id,
                "attempt_id": c["execution_attempt"]["attempt_id"],
                "source_hash": c["source_hash"],
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
    assert receipt["claim_boundary"]["outcome_contributed"] is (
        nested_verifier_task_id == "p1-main-001"
    )
    assert receipt["local"]["substitution_trace"]["final_outcome_contributed"] is (
        nested_verifier_task_id == "p1-main-001"
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
    )


def test_bare_online_without_local_has_no_vap() -> None:
    def bare(context: dict[str, Any]) -> dict[str, Any]:
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
