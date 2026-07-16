"""P4 mainchain entry + three-arm structural (ROUTING FREEZE)."""

from __future__ import annotations

from typing import Any

from nexus.engine.capability_contracts import CapabilityPlan
from nexus.services.mainchain_entry import (
    run_mainchain,
    run_three_arm_structural,
    stamp_mainchain_route,
    with_nexus_armor_enabled,
)
from nexus.services.online_nexus_context import NEXUS_CODEINTEL_MARKER, NEXUS_ROUTE_MARKER
from nexus.services.unified_runtime import UnifiedRuntimeRequest, normalize_online_invoker_payload


class _PlannerLocal:
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
            constraints=[],
            decision_trace=[],
            replan_trace=[],
            score=1.0,
            signal_snapshot={"route_truth_source": "CapabilityPlanner"},
        )


class _Local:
    def handle(self, request: Any) -> dict[str, Any]:
        tid = request["task_id"] if isinstance(request, dict) else request.task_id
        action = request.get("action") if isinstance(request, dict) else request.action
        return {
            "task_id": tid,
            "action": action,
            "local_model_invoked": True,
            "output_delivered": True,
            "executor_invoked": True,
            "physical_callable": "LocalModelExecutor.run",
            "provider": "injected",
            "receipt_path": f"/tmp/{tid}.json",
            "evidence_refs": [f"local:{tid}"],
            "target_file": "parse_kv.py",
            "candidate_summary": {
                "isolation_status": "isolated",
                "selected_candidate_hash": "h1",
                "selected_candidate_hash_matches_applied": True,
                "model_candidate_hash": "h1",
            },
            "verifier_summary": {"verifier_status": "not_run", "verifier_reached": False},
            "local_outputs": {"concise_summary": f"action={action};status=succeeded;evidence_count=1"},
            "outcome_contributed": True,
        }


def test_stamp_mainchain_route_freeze() -> None:
    route = stamp_mainchain_route(
        {"recommended_flow": "direct", "execution_topology": "nexus_full_stack"},
        product_entry="nexus_run",
    )
    assert route["with_nexus_armor"] is True
    assert route["mainchain_entry"] is True
    assert "execution_topology" not in route or route.get("execution_topology") != "nexus_full_stack"
    assert with_nexus_armor_enabled(route) is True
    assert with_nexus_armor_enabled({"recommended_flow": "direct"}) is False


def test_run_mainchain_with_nexus_prompt() -> None:
    seen: dict[str, str] = {}

    def base(context: dict[str, Any]) -> dict[str, Any]:
        seen["prompt"] = str(context.get("online_prompt") or "")
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
        task_id="p4-main-001",
        workspace_revision="rev-p4",
        task_statement="scan impact risk codeintel refactor module",
        task_type="codeintel",
        route={"recommended_flow": "direct", "injected_transport": True, "online_policy": "auto"},
        online_enabled=True,
        online_prompt="bare body",
        codeintel={
            "scan_report_present": True,
            "impact_report_present": True,
            "risk_score": 5,
            "impacted_files_count": 1,
        },
    )
    receipt = run_mainchain(
        req,
        online_invoker=base,
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
    assert NEXUS_ROUTE_MARKER in seen["prompt"]
    assert NEXUS_CODEINTEL_MARKER in seen["prompt"]
    assert receipt["context_trace"]["online_received_context"]["with_nexus_armor"] is True
    assert receipt["claim_boundary"]["public_claim_allowed"] is False


def test_three_arm_structural_distinguishable() -> None:
    local_req = {
        "task_id": "three-arm-nexus-local",
        "action": "candidate",
        "target_file": "parse_kv.py",
        "planner_snapshot": {
            "route_truth_source": "CapabilityPlanner",
            "executor_provider": "ollama",
            "executor_model": "qwen2.5-coder:7b-instruct",
            "model_call_allowed": True,
            "execution_topology": "local_only",
        },
    }
    result = run_three_arm_structural(
        task_statement="repair parse_kv with local model executor and scan impact",
        task_type="repair",
        local_service=_Local(),
        local_request=local_req,
        planner=_PlannerLocal(),
    )
    assert result["routing_surface_changed"] is False
    assert result["public_claim_allowed"] is False
    assert result["compare"]["bare_lacks_armor"] is True
    assert result["compare"]["nexus_has_armor"] is True
    assert result["compare"]["nexus_local_has_vap"] is True
    assert result["arms"]["nexus_local"]["local_physical_callable"] == "LocalModelExecutor.run"
    assert result["arms"]["nexus_local"]["assist_credited"] is True
