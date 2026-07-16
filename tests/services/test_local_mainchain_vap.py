"""P1: LocalAssist → real VAP on UnifiedRuntime main chain (ROUTING FREEZE)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus.engine.capability_contracts import CapabilityPlan
from nexus.services.online_nexus_context import (
    NEXUS_CODEINTEL_MARKER,
    NEXUS_ROUTE_MARKER,
    build_codeintel_preflight_invoker,
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
    packet_is_substantive,
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


def test_unified_runtime_local_produces_vap_and_bd_fingerprints(tmp_path: Path) -> None:
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

    # P2: plan-selected gates invoked
    assert "codeintel" in receipt["capability_results"]
    assert receipt["capability_results"]["codeintel"]["invoked"] is True
    for gate in ("artifact_gate", "claim_gate", "delivery_gate"):
        assert gate in receipt["capability_results"], gate
        assert receipt["capability_results"][gate]["invoked"] is True
        assert receipt["capability_results"][gate]["evidence_refs"]


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
