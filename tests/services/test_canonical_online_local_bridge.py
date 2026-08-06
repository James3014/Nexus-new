from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest

from nexus.contracts.canonical_execution import CanonicalPlanningBundle, CanonicalTaskContext
from nexus.engine.capability_contracts import CapabilityPlan
from nexus.engine.capability_planner import CapabilityPlanner
from nexus.engine.canonical_execution import plan_canonical_task_bundle
from nexus.services.mainchain_entry import run_mainchain, run_mainchain_replan
from nexus.services.unified_runtime import UnifiedRuntimeRequest, normalize_online_invoker_payload


def _plan() -> CapabilityPlan:
    return CapabilityPlan(
        schema_version="nexus_capability_plan_v1",
        selected_capabilities=[],
        required_capabilities=[],
        optional_capabilities=[],
        conditional_capabilities=[],
        pending_capabilities=[],
        forbidden_capabilities=[],
        constraints=["claim_fail_closed"],
        decision_trace=[],
        replan_trace=[],
        score=1.0,
        signal_snapshot={"route_truth_source": "CapabilityPlanner"},
        execution_depth="LIGHT",
    )


def _local_plan() -> CapabilityPlan:
    plan = _plan()
    plan.selected_capabilities.append("local_model_executor")
    plan.required_capabilities.append("local_model_executor")
    plan.signal_snapshot.update(
        {
            "executor_provider": "ollama",
            "executor_model": "qwen2.5-coder:7b-instruct",
            "model_call_allowed": True,
            "execution_topology": "single_local_model",
            "protocol_mode": "anchored_edit",
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
                    }
                ],
            },
        }
    )
    return plan


def _online_workforce_plan() -> CapabilityPlan:
    plan = _plan()
    plan.signal_snapshot["workforce_demands"] = {
        "schema": "nexus.workforce_demands.v1",
        "route_authority": "CapabilityPlanner",
        "demands": [
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
            }
        ],
    }
    return plan


def _online_worker_binding() -> dict[str, object]:
    return {
        "worker_id": "codex_luna",
        "controls": ["receipt", "independent_verification", "governed_adapter"],
    }


def _local_worker_binding() -> dict[str, object]:
    return {
        "worker_id": "local_coder_7b",
        "controls": [
            "small_scope",
            "parser",
            "compile",
            "focused_tests",
            "reversible_application",
        ],
    }


def _agy_worker_binding() -> dict[str, object]:
    return {
        "worker_id": "agy_flash",
        "controls": [
            "task_card",
            "allowed_files",
            "mandatory_commands",
            "independent_verification",
        ],
    }


def _hybrid_workforce_plan() -> CapabilityPlan:
    plan = _local_plan()
    plan.signal_snapshot["workforce_demands"]["demands"].append(
        _online_workforce_plan().signal_snapshot["workforce_demands"]["demands"][0]
    )
    return plan


def test_mainchain_online_consumes_one_canonical_planning_bundle(
    monkeypatch,
) -> None:
    planner_calls = 0
    online_context: dict[str, Any] = {}

    def plan_once(_self, **_kwargs):
        nonlocal planner_calls
        planner_calls += 1
        if planner_calls > 1:
            raise AssertionError("mainchain must not plan twice")
        return _online_workforce_plan()

    monkeypatch.setattr(CapabilityPlanner, "plan", plan_once)

    def online(context):
        online_context.update(context)
        return normalize_online_invoker_payload(
            provider="codex",
            task_id=context["task_id"],
            invoked=True,
            output_delivered=True,
            gate_passed=True,
            provider_call_count=1,
            response={"ok": True},
            evidence_refs=["online:canonical-bundle"],
        )

    online.provider = "codex"
    online.online_invoker_provider = "codex"

    request = UnifiedRuntimeRequest(
        task_id="canonical-online-1",
        workspace_revision="rev-canonical-online-1",
        task_statement="Inspect one bounded parser behavior.",
        task_type="bugfix",
        route={
            "route_features": {"risk_score": 20},
            "workforce_bindings": {"online": _online_worker_binding()},
        },
        online_enabled=True,
    )
    receipt = run_mainchain(
        request,
        online_invoker=online,
        verifier=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["verifier:canonical-bundle"],
        },
        learning=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["learning:canonical-bundle"],
        },
        with_nexus_armor=False,
    )

    assert planner_calls == 1
    assert receipt["canonical_execution"] == online_context["canonical_execution"]
    canonical = receipt["canonical_execution"]
    assert canonical["execution_decision_authority"] == "CapabilityPlanner"
    assert canonical["context_hash"] == canonical["execution_decision"]["context_hash"]
    assert canonical["plan_hash"] == canonical["execution_decision"]["plan_hash"]
    assert canonical["decision_hash"] == canonical["canonical_execution_projection"]["decision_hash"]
    assert canonical["projection_hash"]


def test_mainchain_local_consumes_the_same_canonical_execution_identity(monkeypatch) -> None:
    monkeypatch.setattr(CapabilityPlanner, "plan", lambda _self, **_kwargs: _local_plan())
    captured: dict[str, Any] = {}

    class LocalService:
        def handle(self, request):
            captured.update(request)
            return {
                "task_id": request["task_id"],
                "action": "advisor",
                "local_model_invoked": True,
                "output_delivered": True,
                "provider_call_count": 1,
                "model_call_count": 1,
                "evidence_refs": ["local:canonical-bundle"],
                "outcome_contributed": True,
            }

    request = UnifiedRuntimeRequest(
        task_id="canonical-local-1",
        workspace_revision="rev-canonical-local-1",
        task_statement="Use a local advisor for one bounded parser behavior.",
        task_type="bugfix",
        route={
            "route_features": {"risk_score": 20},
            "workforce_bindings": {
                "local": _local_worker_binding()
            },
        },
        online_enabled=False,
        local_enabled=True,
        local_request={"task_id": "canonical-local-1", "action": "advisor"},
    )
    receipt = run_mainchain(
        request,
        online_invoker=lambda _context: (_ for _ in ()).throw(
            AssertionError("online must remain disabled")
        ),
        local_service=LocalService(),
        verifier=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["verifier:canonical-local"],
        },
        learning=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["learning:canonical-local"],
        },
        with_nexus_armor=False,
    )

    assert captured["planner_snapshot"]["canonical_execution"] == receipt["canonical_execution"]
    assert receipt["local"]["context_trace"]["canonical_execution"] == receipt["canonical_execution"]
    assert receipt["online"]["status"] == "NOT_REQUESTED"


def test_canonical_local_failure_is_incomplete_without_legacy_fallback(monkeypatch) -> None:
    monkeypatch.setattr(CapabilityPlanner, "plan", lambda _self, **_kwargs: _local_plan())
    local_calls = 0

    class FailingLocalService:
        def handle(self, _request):
            nonlocal local_calls
            local_calls += 1
            raise RuntimeError("bounded local failure")

    request = UnifiedRuntimeRequest(
        task_id="canonical-local-failure",
        workspace_revision="rev-canonical-local-failure",
        task_statement="Fail closed when the admitted Local edge fails.",
        task_type="bugfix",
        route={
            "route_features": {"risk_score": 20},
            "workforce_bindings": {"local": _local_worker_binding()},
        },
        online_enabled=False,
        local_enabled=True,
        local_request={"task_id": "canonical-local-failure", "action": "candidate"},
    )
    receipt = run_mainchain(
        request,
        online_invoker=lambda _context: (_ for _ in ()).throw(
            AssertionError("Online must remain disabled")
        ),
        local_service=FailingLocalService(),
        verifier=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["verifier:canonical-local-failure"],
        },
        learning=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["learning:canonical-local-failure"],
        },
        with_nexus_armor=False,
    )

    assert local_calls == 1
    assert receipt["local"]["status"] == "FAILED"
    assert receipt["local"]["reason"] == "local_exception:bounded local failure"
    assert receipt["online"]["status"] == "NOT_REQUESTED"
    assert receipt["terminal_status"] == "INCOMPLETE"
    assert receipt["receipt_complete"] is False


def test_canonical_mainchain_requires_workforce_admission_before_online_call(monkeypatch) -> None:
    monkeypatch.setattr(CapabilityPlanner, "plan", lambda _self, **_kwargs: _online_workforce_plan())
    online_calls = 0

    def online(_context):
        nonlocal online_calls
        online_calls += 1
        raise AssertionError("missing Workforce Admission must block before Online")

    request = UnifiedRuntimeRequest(
        task_id="canonical-workforce-required",
        workspace_revision="rev-canonical-workforce-required",
        task_statement="Run one bounded Online implementation.",
        task_type="bugfix",
        route={"route_features": {"risk_score": 20}},
        online_enabled=True,
    )
    receipt = run_mainchain(
        request,
        online_invoker=online,
        verifier=lambda _context: (_ for _ in ()).throw(
            AssertionError("blocked admission must stop before verifier")
        ),
        learning=lambda _context: (_ for _ in ()).throw(
            AssertionError("blocked admission must stop before learning")
        ),
        with_nexus_armor=False,
    )

    assert online_calls == 0
    assert receipt["terminal_status"] == "BLOCKED"
    assert receipt["workforce_admission"]["overall_decision"] == "BLOCK"
    assert receipt["canonical_execution"]["execution_decision_authority"] == "CapabilityPlanner"


def test_workforce_admission_resolves_the_only_online_provider_and_model(monkeypatch) -> None:
    monkeypatch.setattr(CapabilityPlanner, "plan", lambda _self, **_kwargs: _online_workforce_plan())
    captured: dict[str, Any] = {}

    def online(context):
        captured.update(context)
        return normalize_online_invoker_payload(
            provider="codex",
            task_id=context["task_id"],
            invoked=True,
            output_delivered=True,
            gate_passed=True,
            provider_call_count=1,
            response={"ok": True},
            evidence_refs=["online:workforce-resolved"],
        )

    online.provider = "codex"
    online.online_invoker_provider = "codex"
    request = UnifiedRuntimeRequest(
        task_id="canonical-workforce-allow",
        workspace_revision="rev-canonical-workforce-allow",
        task_statement="Run one bounded Online implementation.",
        task_type="bugfix",
        route={
            "route_features": {"risk_score": 20},
            "workforce_bindings": {"online": _online_worker_binding()},
        },
        online_enabled=True,
    )
    receipt = run_mainchain(
        request,
        online_invoker=online,
        verifier=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["verifier:workforce-resolved"],
        },
        learning=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["learning:workforce-resolved"],
        },
        with_nexus_armor=False,
    )

    authority = receipt["gateway_invocation_authority"]
    assert authority["failure_reason"] == "", authority
    assert authority["status"] == "ALLOW", authority
    assert authority["resolved_provider"] == "codex"
    assert authority["resolved_model"] == "gpt-5.6-luna"
    assert captured["online_model_name"] == "gpt-5.6-luna"
    assert captured["canonical_execution"] == receipt["canonical_execution"]


def test_online_response_provider_must_match_workforce_admission(monkeypatch) -> None:
    monkeypatch.setattr(CapabilityPlanner, "plan", lambda _self, **_kwargs: _online_workforce_plan())
    online_calls = 0

    def online(context):
        nonlocal online_calls
        online_calls += 1
        return normalize_online_invoker_payload(
            provider="grok",
            task_id=context["task_id"],
            invoked=True,
            output_delivered=True,
            gate_passed=True,
            provider_call_count=1,
            response={"ok": True},
            evidence_refs=["online:wrong-response-provider"],
        )

    # The physical callable is the admitted Codex edge, but the transport
    # response claims a different provider. That claim must fail closed.
    online.provider = "codex"
    online.online_invoker_provider = "codex"
    request = UnifiedRuntimeRequest(
        task_id="canonical-online-response-provider-mismatch",
        workspace_revision="rev-canonical-online-response-provider-mismatch",
        task_statement="Reject a response from the wrong Online provider.",
        task_type="bugfix",
        route={
            "route_features": {"risk_score": 20},
            "workforce_bindings": {"online": _online_worker_binding()},
        },
        online_enabled=True,
    )

    receipt = run_mainchain(
        request,
        online_invoker=online,
        verifier=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["verifier:wrong-response-provider"],
        },
        learning=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["learning:wrong-response-provider"],
        },
        with_nexus_armor=False,
    )

    assert online_calls == 1
    assert receipt["online"]["status"] == "FAILED"
    assert receipt["online"]["gate_passed"] is False
    assert receipt["online"]["reason"] == "online_response_provider_mismatch"
    assert receipt["online"]["response"]["error"] == "online_response_provider_mismatch"
    assert receipt["terminal_status"] != "COMPLETE"


def test_mainchain_replan_creates_one_fresh_source_bound_projection(monkeypatch) -> None:
    planner_calls: list[object] = []

    def plan_once_per_attempt(_self, **kwargs):
        authorization = kwargs.get("replan_authorization")
        planner_calls.append(authorization)
        plan = _online_workforce_plan()
        if authorization is not None:
            plan = replace(
                plan,
                execution_depth=authorization.requested_execution_depth,
                replan_trace=[{
                    "source_replan_request_id": authorization.source_replan_request_id,
                    "source_receipt_hash": authorization.source_receipt_hash,
                    "source_run_anchor_hash": authorization.source_run_anchor_hash,
                }],
            )
        return plan

    monkeypatch.setattr(CapabilityPlanner, "plan", plan_once_per_attempt)

    def online(context):
        return normalize_online_invoker_payload(
            provider="codex",
            task_id=context["task_id"],
            invoked=True,
            output_delivered=True,
            gate_passed=True,
            provider_call_count=1,
            response={"ok": True},
            evidence_refs=["online:canonical-replan"],
        )

    online.provider = "codex"
    online.online_invoker_provider = "codex"
    request = UnifiedRuntimeRequest(
        task_id="canonical-mainchain-replan",
        workspace_revision="rev-canonical-mainchain-replan",
        task_statement="Repair one bounded parser behavior.",
        task_type="bugfix",
        route={
            "execution_depth": "LIGHT",
            "route_features": {"risk_score": 20},
            "workforce_bindings": {"online": _online_worker_binding()},
        },
        online_enabled=True,
    )
    first = run_mainchain(
        request,
        online_invoker=online,
        verifier=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "status": "FAILED",
            "gate_passed": False,
            "evidence": "attempt one failed",
            "evidence_refs": ["verifier:canonical-replan:failed"],
        },
        learning=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "status": "SUCCEEDED",
            "gate_passed": True,
            "evidence": "attempt one observed",
            "evidence_refs": ["learning:canonical-replan:one"],
        },
    )

    assert first["terminal_status"] == "INCOMPLETE"
    assert first["execution_replan_request"]["replan_required"] is True
    second = run_mainchain_replan(
        first,
        request,
        online_invoker=online,
        verifier=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "status": "SUCCEEDED",
            "gate_passed": True,
            "evidence": "attempt two passed",
            "evidence_refs": ["verifier:canonical-replan:passed"],
        },
        learning=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "status": "SUCCEEDED",
            "gate_passed": True,
            "evidence": "attempt two observed",
            "evidence_refs": ["learning:canonical-replan:two"],
        },
    )

    assert len(planner_calls) == 2
    assert planner_calls[0] is None
    authorization = planner_calls[1]
    assert authorization is not None
    assert second["execution_attempt"]["attempt_number"] == 2
    assert second["canonical_execution"]["decision_hash"] != first["canonical_execution"]["decision_hash"]
    assert second["canonical_execution"]["projection_hash"] != first["canonical_execution"]["projection_hash"]
    assert second["execution_attempt"]["source_planner_decision_id"] == first["planner_decision_id"]
    assert second["execution_attempt"]["parent_receipt_hash"] == first["receipt_hash"]
    assert (
        second["execution_attempt"]["source_replan_request_id"]
        == first["execution_replan_request"]["replan_request_id"]
    )
    assert second["workforce_admission_lineage"]["status"] == "UNCHANGED"
    assert second["workforce_admission_lineage"]["binding_changed"] is False


def test_online_and_local_share_one_projection_and_admitted_identities(monkeypatch) -> None:
    monkeypatch.setattr(CapabilityPlanner, "plan", lambda _self, **_kwargs: _hybrid_workforce_plan())
    online_context: dict[str, Any] = {}
    local_request: dict[str, Any] = {}

    def online(context):
        online_context.update(context)
        return normalize_online_invoker_payload(
            provider="codex",
            task_id=context["task_id"],
            invoked=True,
            output_delivered=True,
            gate_passed=True,
            provider_call_count=1,
            response={"ok": True},
            evidence_refs=["online:canonical-hybrid"],
        )

    online.provider = "codex"
    online.online_invoker_provider = "codex"

    class LocalService:
        def handle(self, request):
            local_request.update(request)
            return {
                "task_id": request["task_id"],
                "action": "candidate",
                "local_model_invoked": True,
                "output_delivered": True,
                "provider_call_count": 1,
                "model_call_count": 1,
                "evidence_refs": ["local:canonical-hybrid"],
                "outcome_contributed": True,
            }

    request = UnifiedRuntimeRequest(
        task_id="canonical-hybrid-1",
        workspace_revision="rev-canonical-hybrid-1",
        task_statement="Run one bounded Online and Local implementation.",
        task_type="runtime-closure",
        route={
            "route_features": {"risk_score": 20},
            "workforce_bindings": {
                "online": _online_worker_binding(),
                "local": _local_worker_binding(),
            },
        },
        online_enabled=True,
        local_enabled=True,
        local_request={"task_id": "canonical-hybrid-1", "action": "candidate"},
    )
    receipt = run_mainchain(
        request,
        online_invoker=online,
        local_service=LocalService(),
        verifier=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["verifier:canonical-hybrid"],
        },
        learning=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["learning:canonical-hybrid"],
        },
        with_nexus_armor=False,
    )

    canonical = receipt["canonical_execution"]
    assert online_context["canonical_execution"] == canonical
    assert local_request["planner_snapshot"]["canonical_execution"] == canonical
    assert receipt["local"]["context_trace"]["canonical_execution"] == canonical
    assert receipt["gateway_invocation_authority"]["resolved_provider"] == "codex"
    assert receipt["gateway_invocation_authority"]["resolved_model"] == "gpt-5.6-luna"
    assert receipt["local_model_invocation_authority"]["resolved_provider"] == "ollama"
    assert (
        local_request["planner_snapshot"]["executor_model"]
        == receipt["local_model_invocation_authority"]["resolved_model"]
    )


def test_gateway_defers_transport_and_model_binding_until_after_admission(
    monkeypatch,
    tmp_path,
) -> None:
    from nexus.services.gateway import BattlesuitGateway

    monkeypatch.setattr(CapabilityPlanner, "plan", lambda _self, **_kwargs: _online_workforce_plan())
    script = tmp_path / "fake-codex"
    call_log = tmp_path / "call.json"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        f"pathlib.Path({str(call_log)!r}).write_text(json.dumps({{'argv': sys.argv}}))\n"
        "print('canonical gateway ok')\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    request = UnifiedRuntimeRequest(
        task_id="canonical-gateway-deferred",
        workspace_revision="rev-canonical-gateway-deferred",
        task_statement="Run one bounded Online implementation.",
        task_type="runtime-closure",
        route={
            "workforce_bindings": {"online": _online_worker_binding()},
            "online_policy": "auto",
            "online_command": str(script),
            "workspace_root": str(tmp_path),
        },
        online_enabled=True,
    )

    receipt = BattlesuitGateway(project_root=tmp_path).ask_unified(
        request,
        verifier=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["verifier:gateway-deferred"],
        },
        learning=lambda context: {
            "task_id": context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["learning:gateway-deferred"],
        },
    )

    assert receipt["gateway_invocation_authority"]["status"] == "ALLOW"
    assert receipt["online"]["status"] == "SUCCEEDED"
    called = json.loads(call_log.read_text(encoding="utf-8"))
    assert called["argv"][1:4] == ["exec", "-m", "gpt-5.6-luna"]


def test_canonical_bundle_continues_through_runtime_without_replanning(monkeypatch) -> None:
    bundle = plan_canonical_task_bundle(CanonicalTaskContext(
        task_id="mcp-runtime-continuation",
        task_type="repair",
        task_desc="Inspect one bounded parser behavior",
        execution_channels=("online",),
        route_features={"bounded_allowed_file_count": 1},
        codeintel={"allowed_files": ["README.md"]},
        phase_trace={"request_why": "Prove the same decision reaches Online"},
    ))
    bundle = CanonicalPlanningBundle.from_dict(bundle.to_dict())
    context = bundle.context.to_dict()
    monkeypatch.setattr(
        CapabilityPlanner,
        "plan",
        lambda _self, **_kwargs: (_ for _ in ()).throw(
            AssertionError("MCP continuation must not replan")
        ),
    )
    online_context: dict[str, Any] = {}

    def online(runtime_context):
        online_context.update(runtime_context)
        return normalize_online_invoker_payload(
            provider="agy",
            task_id=runtime_context["task_id"],
            invoked=True,
            output_delivered=True,
            gate_passed=True,
            provider_call_count=1,
            response={"ok": True},
            evidence_refs=["online:mcp-continuation"],
        )

    online.provider = "agy"
    online.online_invoker_provider = "agy"
    request = UnifiedRuntimeRequest(
        task_id=context["task_id"],
        workspace_revision="rev-mcp-runtime-continuation",
        task_statement=context["task_desc"],
        task_type=context["task_type"],
        route={
            "route_features": context["route_features"],
            "workforce_bindings": {"online": _agy_worker_binding()},
        },
        online_enabled=True,
        pillars=context["pillars"],
        codeintel=context["codeintel"],
        phase_trace=context["phase_trace"],
        budget=context["budget"],
        canonical_planning_bundle=bundle,
    )
    receipt = run_mainchain(
        request,
        online_invoker=online,
        verifier=lambda runtime_context: {
            "task_id": runtime_context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["verifier:mcp-continuation"],
        },
        learning=lambda runtime_context: {
            "task_id": runtime_context["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["learning:mcp-continuation"],
        },
        with_nexus_armor=False,
    )

    assert receipt["canonical_execution"]["decision_hash"] == bundle.decision.decision_hash
    assert receipt["canonical_execution"]["projection_hash"] == bundle.projection.projection_hash
    assert online_context["canonical_execution"] == receipt["canonical_execution"]


def test_mainchain_rejects_caller_injected_planner_before_execution() -> None:
    request = UnifiedRuntimeRequest(
        task_id="canonical-planner-injection",
        workspace_revision="rev-canonical-planner-injection",
        task_statement="Reject a second route authority.",
        task_type="bugfix",
        route={},
        online_enabled=True,
    )

    with pytest.raises(ValueError, match="mainchain_planner_injection_forbidden"):
        run_mainchain(
            request,
            online_invoker=lambda _context: (_ for _ in ()).throw(
                AssertionError("planner injection must block before Online")
            ),
            planner=object(),
            with_nexus_armor=False,
        )
