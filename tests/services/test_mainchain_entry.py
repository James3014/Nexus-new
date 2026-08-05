"""P4 mainchain entry + three-arm structural (ROUTING FREEZE)."""

import json
from typing import Any

import pytest

from nexus.engine.capability_contracts import CapabilityPlan
from nexus.services.mainchain_entry import (
    run_mainchain as _product_run_mainchain,
    run_mainchain_replan as _product_run_mainchain_replan,
    run_three_arm_structural,
    stamp_mainchain_route,
    summarize_arm_receipt,
    with_nexus_armor_enabled,
)
from nexus.evidence.receipt_base import validate_receipt_base
from nexus.services.online_nexus_context import NEXUS_CODEINTEL_MARKER, NEXUS_ROUTE_MARKER
from nexus.services.unified_runtime import UnifiedRuntime, UnifiedRuntimeRequest, normalize_online_invoker_payload


def _mainchain_workforce_binding(request: UnifiedRuntimeRequest) -> tuple[str, str, str, list[str]]:
    """Return the policy-admitted Online identity for this test request."""
    text = f"{request.task_type} {request.task_statement}".lower()
    complex_task = any(
        marker in text
        for marker in ("architecture", "security", "integration", "cross-module", "runtime-closure")
    )
    if complex_task:
        return (
            "codex_luna",
            "codex",
            "gpt-5.6-luna",
            ["governed_adapter", "independent_verification", "receipt"],
        )
    return (
        "agy_flash",
        "agy",
        "gemini-3.6-flash-high",
        ["task_card", "allowed_files", "mandatory_commands", "independent_verification"],
    )


def _admit_mainchain_request(request: UnifiedRuntimeRequest) -> UnifiedRuntimeRequest:
    worker, _provider, _model, controls = _mainchain_workforce_binding(request)
    route = dict(request.route)
    route.update(
        {
            "workforce_admission_enabled": True,
            "workforce_bindings": {
                **dict(route.get("workforce_bindings") or {}),
                "online": {
                    "worker_id": worker,
                    "controls": controls,
                },
            },
        }
    )
    fields = {
        field: getattr(request, field)
        for field in request.__dataclass_fields__
        if field != "route"
    }
    fields.update(route=route)
    return UnifiedRuntimeRequest(**fields)


def _tag_online_invoker(invoker: Any, provider: str) -> Any:
    """Tag fixture invokers and normalize their payload to admitted provider."""
    if not callable(invoker):
        return invoker

    def tagged(context: dict[str, Any]) -> dict[str, Any]:
        payload = dict(invoker(context))
        payload["provider"] = provider
        process = payload.get("process_evidence")
        if isinstance(process, dict):
            process["provider"] = provider
        return payload

    tagged.provider = provider  # type: ignore[attr-defined]
    tagged.online_invoker_provider = provider  # type: ignore[attr-defined]
    return tagged


def run_mainchain(request: UnifiedRuntimeRequest, **kwargs: Any) -> dict[str, Any]:
    admitted = _admit_mainchain_request(request)
    provider = _mainchain_workforce_binding(admitted)[1]
    if "online_invoker" in kwargs:
        kwargs["online_invoker"] = _tag_online_invoker(kwargs["online_invoker"], provider)
    return _product_run_mainchain(admitted, **kwargs)


def run_mainchain_replan(
    previous_receipt: dict[str, Any], request: UnifiedRuntimeRequest, **kwargs: Any
) -> dict[str, Any]:
    admitted = _admit_mainchain_request(request)
    provider = _mainchain_workforce_binding(admitted)[1]
    if "online_invoker" in kwargs:
        kwargs["online_invoker"] = _tag_online_invoker(kwargs["online_invoker"], provider)
    return _product_run_mainchain_replan(previous_receipt, admitted, **kwargs)


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
            "schema": "nexus.local_assist.response.v1",
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
    )
    assert result["routing_surface_changed"] is False
    assert result["public_claim_allowed"] is False
    assert result["benchmark_only"] is True
    assert result["production_decision_writeback_allowed"] is False
    assert result["production_route_mutated"] is False
    assert result["compare"]["bare_lacks_armor"] is True
    assert result["compare"]["nexus_has_armor"] is True
    assert result["compare"]["nexus_local_has_vap"] is True
    assert result["arms"]["nexus_local"]["local_physical_callable"] == "LocalModelExecutor.run"
    assert result["arms"]["nexus_local"]["assist_credited"] is True


# Milestone B Tests — Mainchain Controlled Replan Seam & Route Identity

def test_mainchain_replan_delegates_to_unified_runtime_once():
    seen = {}
    def online(ctx):
        seen["invoked"] = True
        return normalize_online_invoker_payload(
            provider="fixture",
            task_id=ctx["task_id"],
            invoked=True,
            output_delivered=True,
            gate_passed=True,
            provider_call_count=1,
            response="attempt1",
            raw_response="attempt1",
            evidence_refs=["o:1"],
        )

    all_caps = ["baseline", "harness_preflight_sensor", "delivery_gate", "mempalace_gate", "artifact_gate", "claim_gate"]
    cap_invokers = {
        name: lambda ctx, n=name: {
            "task_id": ctx.get("task_id", "mc-replan-1"),
            "status": "SUCCEEDED",
            "invoked": True,
            "evidence": "ok",
            "evidence_refs": [f"c:{n}:ok"],
            "gate_passed": True,
            "outcome_contributed": True,
        }
        for name in all_caps
    }

    req = UnifiedRuntimeRequest(
        task_id="mc-replan-1",
        workspace_revision="rev-mc-1",
        task_statement="inspect codeintel",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = run_mainchain(
        req,
        online_invoker=online,
        capability_invokers=cap_invokers,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail1", "evidence_refs": ["v:1"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True, "evidence_refs": ["l:1"]},
    )
    assert r1["terminal_status"] == "INCOMPLETE"
    assert r1["execution_replan_request"]["replan_required"] is True

    r2 = run_mainchain_replan(
        r1,
        req,
        online_invoker=online,
        capability_invokers=cap_invokers,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "pass2", "evidence_refs": ["v:2"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True, "evidence_refs": ["l:2"]},
    )
    assert r2["terminal_status"] == "SUCCEEDED"
    assert r2["execution_depth"] == "STANDARD"
    assert r2["execution_attempt"]["attempt_number"] == 2


def test_mainchain_replan_preserves_planner_authority():
    all_caps = ["baseline", "harness_preflight_sensor", "delivery_gate", "mempalace_gate", "artifact_gate", "claim_gate"]
    cap_invokers = {
        name: lambda ctx, n=name: {
            "task_id": ctx.get("task_id", "mc-replan-authority"),
            "status": "SUCCEEDED",
            "invoked": True,
            "evidence": "ok",
            "evidence_refs": [f"c:{n}:ok"],
            "gate_passed": True,
            "outcome_contributed": True,
        }
        for name in all_caps
    }
    req = UnifiedRuntimeRequest(
        task_id="mc-replan-authority",
        workspace_revision="rev-mc-2",
        task_statement="inspect module",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = run_mainchain(
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="r1", raw_response="r1", evidence_refs=["o:1"]),
        capability_invokers=cap_invokers,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:fail"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    r2 = run_mainchain_replan(
        r1,
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="r2", raw_response="r2", evidence_refs=["o:2"]),
        capability_invokers=cap_invokers,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "pass", "evidence_refs": ["v:pass"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    assert r2["context_trace"]["selection_authority"] == "CapabilityPlanner"
    assert r2["planner_decision_id"] != r1["planner_decision_id"]


def test_mainchain_replan_stamps_attempt_two_route():
    all_caps = ["baseline", "harness_preflight_sensor", "delivery_gate", "mempalace_gate", "artifact_gate", "claim_gate"]
    cap_invokers = {
        name: lambda ctx, n=name: {
            "task_id": ctx.get("task_id", "mc-replan-stamps"),
            "status": "SUCCEEDED",
            "invoked": True,
            "evidence": "ok",
            "evidence_refs": [f"c:{n}:ok"],
            "gate_passed": True,
            "outcome_contributed": True,
        }
        for name in all_caps
    }
    req = UnifiedRuntimeRequest(
        task_id="mc-replan-stamps",
        workspace_revision="rev-mc-3",
        task_statement="inspect module",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = run_mainchain(
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="r1", raw_response="r1", evidence_refs=["o:1"]),
        capability_invokers=cap_invokers,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:fail"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    r2 = run_mainchain_replan(
        r1,
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="r2", raw_response="r2", evidence_refs=["o:2"]),
        capability_invokers=cap_invokers,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "pass", "evidence_refs": ["v:pass"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    route = r2["context_trace"]["route"]
    assert route["mainchain_entry"] is True
    assert route["with_nexus_armor"] is True


def test_mainchain_replan_rejects_non_mainchain_prior_receipt():
    fake_r1 = {
        "schema": "nexus.unified_receipt.v1",
        "task_id": "mc-non-mainchain",
        "workspace_revision": "rev-mc-4",
        "planner_decision_id": "p1",
        "execution_depth": "LIGHT",
        "terminal_status": "INCOMPLETE",
        "receipt_complete": False,
        "public_claim_allowed": False,
        "receipt_base": {
            "schema": "nexus.receipt_base.v3",
            "task_id": "mc-non-mainchain",
            "workspace_revision": "rev-mc-4",
            "planner_decision_id": "p1",
            "receipt_hash": "sha256:1111",
            "run_anchor_hash": "sha256:2222",
            "public_claim_allowed": False,
            "production_ready": False,
            "source_world": "A",
            "source_component": "unified_runtime",
        },
        "execution_replan_request": {
            "schema": "nexus.execution_replan_request.v1",
            "task_id": "mc-non-mainchain",
            "source_planner_decision_id": "p1",
            "current_execution_depth": "LIGHT",
            "requested_execution_depth": "STANDARD",
            "replan_required": True,
            "verifier_outcome_trusted": True,
            "manual_review_required": False,
            "public_claim_allowed": False,
            "replan_request_id": "sha256:req1",
        },
        "context_trace": {
            "route": {"recommended_flow": "direct"},  # Missing mainchain_entry
        },
        "verifier": {"task_id": "mc-non-mainchain", "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:fail"]},
    }
    req = UnifiedRuntimeRequest(
        task_id="mc-non-mainchain",
        workspace_revision="rev-mc-4",
        task_statement="inspect module",
        task_type="public_bugfix",
        route={"recommended_flow": "direct"},
        online_enabled=True,
        local_enabled=False,
    )
    with pytest.raises(ValueError, match="previous_receipt_not_mainchain|previous_receipt_integrity_invalid"):
        run_mainchain_replan(
            fake_r1,
            req,
            online_invoker=lambda c: {},
            verifier=lambda c: {},
            learning=lambda c: {},
        )


def test_mainchain_replan_rejects_tampered_prior_receipt():
    all_caps = ["baseline", "harness_preflight_sensor", "delivery_gate", "mempalace_gate", "artifact_gate", "claim_gate"]
    cap_invokers = {
        name: lambda ctx, n=name: {
            "task_id": ctx.get("task_id", "mc-tampered"),
            "status": "SUCCEEDED",
            "invoked": True,
            "evidence": "ok",
            "evidence_refs": [f"c:{n}:ok"],
            "gate_passed": True,
            "outcome_contributed": True,
        }
        for name in all_caps
    }
    req = UnifiedRuntimeRequest(
        task_id="mc-tampered",
        workspace_revision="rev-mc-5",
        task_statement="inspect module",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = run_mainchain(
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="r1", raw_response="r1", evidence_refs=["o:1"]),
        capability_invokers=cap_invokers,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:fail"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    tampered = dict(r1)
    tampered["execution_depth"] = "FULL"  # Tamper depth
    with pytest.raises(ValueError):
        run_mainchain_replan(
            tampered,
            req,
            online_invoker=lambda c: {},
            verifier=lambda c: {},
            learning=lambda c: {},
        )


def test_mainchain_replan_rejects_caller_route_spoof():
    all_caps = ["baseline", "harness_preflight_sensor", "delivery_gate", "mempalace_gate", "artifact_gate", "claim_gate"]
    cap_invokers = {
        name: lambda ctx, n=name: {
            "task_id": ctx.get("task_id", "mc-spoof"),
            "status": "SUCCEEDED",
            "invoked": True,
            "evidence": "ok",
            "evidence_refs": [f"c:{n}:ok"],
            "gate_passed": True,
            "outcome_contributed": True,
        }
        for name in all_caps
    }
    req1 = UnifiedRuntimeRequest(
        task_id="mc-spoof",
        workspace_revision="rev-mc-6",
        task_statement="inspect module",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = run_mainchain(
        req1,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="r1", raw_response="r1", evidence_refs=["o:1"]),
        capability_invokers=cap_invokers,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:fail"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    req_spoof = UnifiedRuntimeRequest(
        task_id="mc-spoof",
        workspace_revision="rev-mc-6",
        task_statement="inspect module",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
            "with_nexus_armor": False,
        },
        online_enabled=True,
        local_enabled=False,
    )
    r2 = run_mainchain_replan(
        r1,
        req_spoof,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="r2", raw_response="r2", evidence_refs=["o:2"]),
        capability_invokers=cap_invokers,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "pass", "evidence_refs": ["v:pass"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
        with_nexus_armor=True,
    )
    assert r2["context_trace"]["route"]["with_nexus_armor"] is True


def test_mainchain_replan_uses_new_planner_decision():
    all_caps = ["baseline", "harness_preflight_sensor", "delivery_gate", "mempalace_gate", "artifact_gate", "claim_gate"]
    cap_invokers = {
        name: lambda ctx, n=name: {
            "task_id": ctx.get("task_id", "mc-new-planner"),
            "status": "SUCCEEDED",
            "invoked": True,
            "evidence": "ok",
            "evidence_refs": [f"c:{n}:ok"],
            "gate_passed": True,
            "outcome_contributed": True,
        }
        for name in all_caps
    }
    req = UnifiedRuntimeRequest(
        task_id="mc-new-planner",
        workspace_revision="rev-mc-7",
        task_statement="inspect module",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = run_mainchain(
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="r1", raw_response="r1", evidence_refs=["o:1"]),
        capability_invokers=cap_invokers,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:fail"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    r2 = run_mainchain_replan(
        r1,
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="r2", raw_response="r2", evidence_refs=["o:2"]),
        capability_invokers=cap_invokers,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "pass", "evidence_refs": ["v:pass"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    assert r2["planner_decision_id"] != r1["planner_decision_id"]


def test_mainchain_replan_preserves_parent_receipt_identity():
    all_caps = ["baseline", "harness_preflight_sensor", "delivery_gate", "mempalace_gate", "artifact_gate", "claim_gate"]
    cap_invokers = {
        name: lambda ctx, n=name: {
            "task_id": ctx.get("task_id", "mc-parent-id"),
            "status": "SUCCEEDED",
            "invoked": True,
            "evidence": "ok",
            "evidence_refs": [f"c:{n}:ok"],
            "gate_passed": True,
            "outcome_contributed": True,
        }
        for name in all_caps
    }
    req = UnifiedRuntimeRequest(
        task_id="mc-parent-id",
        workspace_revision="rev-mc-8",
        task_statement="inspect module",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = run_mainchain(
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="r1", raw_response="r1", evidence_refs=["o:1"]),
        capability_invokers=cap_invokers,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:fail"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    r2 = run_mainchain_replan(
        r1,
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="r2", raw_response="r2", evidence_refs=["o:2"]),
        capability_invokers=cap_invokers,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "pass", "evidence_refs": ["v:pass"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    assert r2["execution_attempt"]["parent_receipt_hash"] == r1["receipt_base"]["receipt_hash"]


def test_mainchain_replan_stops_after_attempt_two():
    all_caps = ["baseline", "harness_preflight_sensor", "delivery_gate", "mempalace_gate", "artifact_gate", "claim_gate"]
    cap_invokers = {
        name: lambda ctx, n=name: {
            "task_id": ctx.get("task_id", "mc-max-two"),
            "status": "SUCCEEDED",
            "invoked": True,
            "evidence": "ok",
            "evidence_refs": [f"c:{n}:ok"],
            "gate_passed": True,
            "outcome_contributed": True,
        }
        for name in all_caps
    }
    req = UnifiedRuntimeRequest(
        task_id="mc-max-two",
        workspace_revision="rev-mc-9",
        task_statement="inspect module",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = run_mainchain(
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="r1", raw_response="r1", evidence_refs=["o:1"]),
        capability_invokers=cap_invokers,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail1", "evidence_refs": ["v:fail1"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    r2 = run_mainchain_replan(
        r1,
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="r2", raw_response="r2", evidence_refs=["o:2"]),
        capability_invokers=cap_invokers,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail2", "evidence_refs": ["v:fail2"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    assert r2["terminal_status"] == "INCOMPLETE"
    assert r2["execution_attempt"]["attempt_number"] == 2
    with pytest.raises(ValueError, match="replan_attempt_budget_exhausted"):
        run_mainchain_replan(
            r2,
            req,
            online_invoker=lambda c: {},
            verifier=lambda c: {},
            learning=lambda c: {},
        )


def test_mainchain_summary_exposes_only_safe_process_identity():
    req = UnifiedRuntimeRequest(
        task_id="mc-summary-safe",
        workspace_revision="rev-mc-10",
        task_statement="my secret prompt 123",
        task_type="public_bugfix",
        route={"recommended_flow": "direct"},
        online_enabled=True,
        local_enabled=False,
    )
    r1 = run_mainchain(
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="ok", raw_response="ok", evidence_refs=["o:ok"]),
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "pass", "evidence_refs": ["v:pass"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True},
    )
    summary = summarize_arm_receipt(r1, prompt=req.task_statement)
    summary_str = json.dumps(summary)
    assert "my secret prompt 123" not in summary_str
    assert "attempt_number" in summary
    assert "is_replan" in summary


# Milestone A Identity Seal & Prior Receipt Contract Tests

def test_stamp_mainchain_route_sets_canonical_frozen_identity():
    route = stamp_mainchain_route({})
    assert route["mainchain_entry"] is True
    assert route["route_freeze"] is True
    assert route["mainchain_route_version"] == "mainchain.v1"
    assert route["product_entry"] == "mainchain"
    assert route["with_nexus_armor"] is True


def test_stamp_mainchain_route_overwrites_false_spoof():
    spoof = {
        "mainchain_entry": False,
        "route_freeze": False,
        "mainchain_route_version": "evil.v9",
    }
    route = stamp_mainchain_route(spoof)
    assert route["mainchain_entry"] is True
    assert route["route_freeze"] is True
    assert route["mainchain_route_version"] == "mainchain.v1"


def test_stamp_mainchain_route_normalizes_none_product_entry():
    for invalid_val in ["None", "null", "", None]:
        route = stamp_mainchain_route({"product_entry": invalid_val})
        assert route["product_entry"] == "mainchain"


def test_run_mainchain_receipt_contains_route_freeze():
    req = UnifiedRuntimeRequest(
        task_id="mc-freeze-1",
        workspace_revision="rev-1",
        task_statement="inspect module",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    receipt = run_mainchain(
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="ok", raw_response="ok", evidence_refs=["o:ok"]),
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "pass", "evidence_refs": ["v:pass"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True, "evidence_refs": ["l:pass"]},
    )
    assert receipt["context_trace"]["route"]["route_freeze"] is True
    assert receipt["context_trace"]["route"]["mainchain_route_version"] == "mainchain.v1"
    assert receipt["receipt_base"]["route_freeze"] is True
    assert receipt["receipt_base"]["mainchain_route_version"] == "mainchain.v1"


def test_run_mainchain_receipt_base_matches_route_identity():
    req = UnifiedRuntimeRequest(
        task_id="mc-base-match-1",
        workspace_revision="rev-1",
        task_statement="inspect module",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    receipt = run_mainchain(
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="ok", raw_response="ok", evidence_refs=["o:ok"]),
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": True, "status": "SUCCEEDED", "evidence": "pass", "evidence_refs": ["v:pass"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True, "evidence_refs": ["l:pass"]},
    )
    rb = receipt["receipt_base"]
    route = receipt["context_trace"]["route"]
    assert rb["mainchain_entry"] == route["mainchain_entry"]
    assert rb["route_freeze"] == route["route_freeze"]
    assert rb["mainchain_route_version"] == route["mainchain_route_version"]
    assert rb["with_nexus_armor"] == route["with_nexus_armor"]


def test_mainchain_replan_rejects_pseudo_mainchain_runtime_receipt():
    req = UnifiedRuntimeRequest(
        task_id="mc-pseudo-1",
        workspace_revision="rev-1",
        task_statement="inspect module",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
            "mainchain_entry": True,
            "with_nexus_armor": True,
        },
        online_enabled=True,
        local_enabled=False,
    )
    invocations = {"count": 0}
    def online_invoker(c):
        invocations["count"] += 1
        return normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="attempt1", raw_response="attempt1", evidence_refs=["o:1"])

    r1 = UnifiedRuntime().run(
        req,
        online_invoker=online_invoker,
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:fail"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True, "evidence_refs": ["l:1"]},
    )
    assert r1["terminal_status"] == "INCOMPLETE"
    assert validate_receipt_base(r1, mode="strict")["ok"] is True

    invocations_before = invocations["count"]
    with pytest.raises(ValueError, match="previous_receipt_route_freeze_missing"):
        run_mainchain_replan(
            r1,
            req,
            online_invoker=online_invoker,
            verifier=lambda c: {},
            learning=lambda c: {},
        )
    assert invocations["count"] == invocations_before


def test_mainchain_replan_rejects_missing_route_freeze():
    req = UnifiedRuntimeRequest(
        task_id="mc-no-freeze",
        workspace_revision="rev-1",
        task_statement="inspect module",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = run_mainchain(
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="ok", raw_response="ok", evidence_refs=["o:ok"]),
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:fail"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True, "evidence_refs": ["l:1"]},
    )
    r1["context_trace"]["route"].pop("route_freeze", None)
    r1["receipt_base"].pop("route_freeze", None)
    with pytest.raises(ValueError, match="previous_receipt_route_freeze_missing|previous_receipt_integrity_invalid"):
        run_mainchain_replan(
            r1,
            req,
            online_invoker=lambda c: {},
            verifier=lambda c: {},
            learning=lambda c: {},
        )


def test_mainchain_replan_rejects_missing_mainchain_version():
    req = UnifiedRuntimeRequest(
        task_id="mc-no-ver",
        workspace_revision="rev-1",
        task_statement="inspect module",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = run_mainchain(
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="ok", raw_response="ok", evidence_refs=["o:ok"]),
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:fail"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True, "evidence_refs": ["l:1"]},
    )
    r1["context_trace"]["route"].pop("mainchain_route_version", None)
    r1["receipt_base"].pop("mainchain_route_version", None)
    with pytest.raises(ValueError, match="previous_receipt_mainchain_version_missing|previous_receipt_integrity_invalid"):
        run_mainchain_replan(
            r1,
            req,
            online_invoker=lambda c: {},
            verifier=lambda c: {},
            learning=lambda c: {},
        )


def test_mainchain_replan_rejects_wrong_mainchain_version():
    req = UnifiedRuntimeRequest(
        task_id="mc-bad-ver",
        workspace_revision="rev-1",
        task_statement="inspect module",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = run_mainchain(
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="ok", raw_response="ok", evidence_refs=["o:ok"]),
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:fail"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True, "evidence_refs": ["l:1"]},
    )
    r1["context_trace"]["route"]["mainchain_route_version"] = "mainchain.v99"
    r1["receipt_base"]["mainchain_route_version"] = "mainchain.v99"
    with pytest.raises(ValueError, match="previous_receipt_mainchain_version_unsupported|prior_receipt_base_invalid|previous_receipt_integrity_invalid"):
        run_mainchain_replan(
            r1,
            req,
            online_invoker=lambda c: {},
            verifier=lambda c: {},
            learning=lambda c: {},
        )


def test_mainchain_replan_rejects_false_nexus_armor_argument():
    req = UnifiedRuntimeRequest(
        task_id="mc-armor-false",
        workspace_revision="rev-1",
        task_statement="inspect module",
        task_type="public_bugfix",
        route={
            "execution_depth": "LIGHT",
            "recommended_flow": "baseline",
            "route_features": {"risk_score": 10},
            "capability_stack": {"selected_capabilities": ["baseline"]},
        },
        online_enabled=True,
        local_enabled=False,
    )
    r1 = run_mainchain(
        req,
        online_invoker=lambda c: normalize_online_invoker_payload(provider="fixture", task_id=c["task_id"], invoked=True, output_delivered=True, gate_passed=True, provider_call_count=1, response="ok", raw_response="ok", evidence_refs=["o:ok"]),
        verifier=lambda c: {"task_id": c["task_id"], "invoked": True, "gate_passed": False, "status": "FAILED", "evidence": "fail", "evidence_refs": ["v:fail"]},
        learning=lambda c: {"status": "SUCCEEDED", "invoked": True, "evidence_present": True, "gate_passed": True, "evidence_refs": ["l:1"]},
    )
    invocations = {"count": 0}
    def online_invoker(c):
        invocations["count"] += 1
        return {}

    with pytest.raises(ValueError, match="mainchain_replan_requires_nexus_armor"):
        run_mainchain_replan(
            r1,
            req,
            online_invoker=online_invoker,
            verifier=lambda c: {},
            learning=lambda c: {},
            with_nexus_armor=False,
        )
    assert invocations["count"] == 0


def test_mainchain_summary_does_not_default_missing_freeze_to_true():
    receipt = {
        "task_id": "mc-sum-1",
        "context_trace": {
            "route": {
                "mainchain_entry": True,
                "with_nexus_armor": True,
            }
        },
    }
    summary = summarize_arm_receipt(receipt)
    assert summary["route_freeze"] is False
    assert summary["mainchain_identity_complete"] is False


def test_mainchain_summary_marks_incomplete_identity_false():
    incomplete_receipt = {
        "task_id": "mc-sum-2",
        "context_trace": {
            "route": {
                "mainchain_entry": True,
                "route_freeze": True,
                "mainchain_route_version": "mainchain.v1",
                "product_entry": "None",
                "with_nexus_armor": True,
            }
        },
    }
    summary = summarize_arm_receipt(incomplete_receipt)
    assert summary["mainchain_identity_complete"] is False


# Milestone A — Summary Truth Separation Tests

def test_mainchain_summary_rejects_prompt_armor_substitution():
    receipt = {
        "task_id": "mc-sum-sub-1",
        "context_trace": {
            "route": {
                "mainchain_entry": True,
                "route_freeze": True,
                "mainchain_route_version": "mainchain.v1",
                "product_entry": "mainchain",
                "with_nexus_armor": False,
            }
        },
    }
    prompt = "Some prompt\n[WITH_NEXUS_ROUTE]\narmor"
    summary = summarize_arm_receipt(receipt, prompt=prompt)
    assert summary["with_nexus_armor"] is False
    assert summary["route_with_nexus_armor"] is False
    assert summary["prompt_armor_present"] is True
    assert summary["mainchain_identity_complete"] is False


def test_mainchain_summary_rejects_online_context_armor_substitution():
    receipt = {
        "task_id": "mc-sum-sub-2",
        "context_trace": {
            "route": {
                "mainchain_entry": True,
                "route_freeze": True,
                "mainchain_route_version": "mainchain.v1",
                "product_entry": "mainchain",
                "with_nexus_armor": False,
            },
            "online_received_context": {"with_nexus_armor": True},
        },
    }
    summary = summarize_arm_receipt(receipt)
    assert summary["with_nexus_armor"] is False
    assert summary["route_with_nexus_armor"] is False
    assert summary["online_context_with_nexus_armor"] is True
    assert summary["mainchain_identity_complete"] is False


def test_mainchain_summary_route_armor_is_authoritative():
    receipt = {
        "task_id": "mc-sum-sub-3",
        "context_trace": {
            "route": {
                "mainchain_entry": True,
                "route_freeze": True,
                "mainchain_route_version": "mainchain.v1",
                "product_entry": "mainchain",
                "with_nexus_armor": True,
            },
            "online_received_context": {"with_nexus_armor": False},
        },
    }
    summary = summarize_arm_receipt(receipt)
    assert summary["with_nexus_armor"] is True
    assert summary["route_with_nexus_armor"] is True
    assert summary["mainchain_identity_complete"] is True


def test_mainchain_summary_reports_prompt_armor_separately():
    receipt = {
        "task_id": "mc-sum-sub-4",
        "context_trace": {
            "route": {
                "mainchain_entry": True,
                "route_freeze": True,
                "mainchain_route_version": "mainchain.v1",
                "product_entry": "mainchain",
                "with_nexus_armor": True,
            }
        },
    }
    summary = summarize_arm_receipt(receipt, prompt="hello world\n[WITH_NEXUS_ROUTE]\n...")
    assert summary["prompt_armor_present"] is True
    assert summary["route_with_nexus_armor"] is True


def test_mainchain_summary_reports_online_context_armor_separately():
    receipt = {
        "task_id": "mc-sum-sub-5",
        "context_trace": {
            "route": {
                "mainchain_entry": True,
                "route_freeze": True,
                "mainchain_route_version": "mainchain.v1",
                "product_entry": "mainchain",
                "with_nexus_armor": True,
            },
            "online_received_context": {"with_nexus_armor": True},
        },
    }
    summary = summarize_arm_receipt(receipt)
    assert summary["online_context_with_nexus_armor"] is True
