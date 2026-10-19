"""Online A/B gap A: escalate-only executors fire on the planner's task signals."""

from __future__ import annotations

from typing import Any

import pytest

from nexus.research.sprint_service import PLANNER_ROUTE_SIGNAL_KEYS, planner_route_signals
from nexus.services.capability_registry import (
    PLANNER_SIGNAL_TRIGGER_SOURCE,
    PLANNER_SIGNAL_TRIGGERS,
    SKIP_POLICY_NOT_TRIGGERED,
    build_escalate_gated_invoker,
    planner_signal_trigger,
)


def _context(
    name: str,
    *,
    reasons: list[str],
    snapshot: dict[str, Any],
    selected: bool = True,
    should_research: bool = False,
) -> dict[str, Any]:
    return {
        "task_id": "sprint-abc-s0-a1",
        "route": {
            "mainchain_entry": True,
            "recommended_flow": "direct",
            "should_research": should_research,
        },
        "planner": {
            "selected_capabilities": [name] if selected else [],
            "decision_trace": [{"capability": name, "reasons": reasons, "state": "conditional"}],
            "signal_snapshot": snapshot,
        },
    }


def _real(calls: list[str]):
    def invoke(context):
        calls.append(str(context.get("task_id")))
        return {
            "task_id": context.get("task_id"),
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": ["ev_real"],
        }

    return invoke


@pytest.mark.parametrize(
    ("name", "reasons", "snapshot", "signal"),
    [
        (
            "learn_mode",
            ["claim_or_citation_learning_signal"],
            {"learning_signal": True},
            "learning_signal",
        ),
        (
            "learn_phase_slo",
            ["learn_phase_policy_needed"],
            {"learning_signal": True},
            "learning_signal",
        ),
        (
            "multi_agent",
            ["coordinated_ownership_required"],
            {"multi_agent_signal": True},
            "multi_agent_signal",
        ),
        ("research", ["context_or_retrieval_gap"], {"memory_hits": 3}, "memory_hits"),
        ("research_route", ["routing_contract_required"], {"doc_scout_hits": 2}, "doc_scout_hits"),
        (
            "research_route",
            ["routing_contract_required"],
            {"plateau_detected": True},
            "plateau_detected",
        ),
    ],
)
def test_planner_task_signal_triggers_real_executor(name, reasons, snapshot, signal) -> None:
    calls: list[str] = []
    invoker = build_escalate_gated_invoker(name, real_invoker=_real(calls))

    out = invoker(_context(name, reasons=reasons, snapshot=snapshot))

    assert calls == ["sprint-abc-s0-a1"]
    assert out["invoked"] is True
    assert out["trigger_source"] == f"{PLANNER_SIGNAL_TRIGGER_SOURCE}:{signal}"


@pytest.mark.parametrize("name", ["research", "research_route"])
def test_flow_route_research_decision_triggers_research(name) -> None:
    calls: list[str] = []
    invoker = build_escalate_gated_invoker(name, real_invoker=_real(calls))
    reasons = ["context_or_retrieval_gap"] if name == "research" else ["routing_contract_required"]

    out = invoker(_context(name, reasons=reasons, snapshot={}, should_research=True))

    assert calls == ["sprint-abc-s0-a1"]
    assert out["trigger_source"] == f"{PLANNER_SIGNAL_TRIGGER_SOURCE}:route_should_research"


@pytest.mark.parametrize(
    ("name", "reasons", "snapshot", "selected"),
    [
        # signal false -> no trigger even though the planner listed the reason
        ("learn_mode", ["claim_or_citation_learning_signal"], {"learning_signal": False}, True),
        # signal true but the planner selected it for an unrelated reason
        ("multi_agent", ["tier_l3_deep_governance"], {"multi_agent_signal": True}, True),
        # research_route is required on every routed task; without a lookup signal it stays skipped
        (
            "research_route",
            ["routing_contract_required"],
            {"doc_scout_hits": 0, "plateau_detected": False},
            True,
        ),
        # not selected by the planner
        ("research", ["context_or_retrieval_gap"], {"memory_hits": 2}, False),
        # candidate-dependent / release-dependent executors are not signal-triggered here
        ("ultra_review", ["high_risk_or_governance_route"], {"governance_signal": True}, True),
        ("sandbox", ["high_risk_isolated_execution"], {"governance_signal": True}, True),
        ("file_lock", ["multi_agent_write_boundary"], {"multi_agent_signal": True}, True),
    ],
)
def test_no_task_signal_keeps_policy_skip(name, reasons, snapshot, selected) -> None:
    calls: list[str] = []
    invoker = build_escalate_gated_invoker(name, real_invoker=_real(calls))

    out = invoker(_context(name, reasons=reasons, snapshot=snapshot, selected=selected))

    assert calls == []
    assert out["invoked"] is False
    assert SKIP_POLICY_NOT_TRIGGERED in str(out.get("skip_reason") or out.get("reason"))
    assert (
        planner_signal_trigger(
            name, _context(name, reasons=reasons, snapshot=snapshot, selected=selected)
        )
        == ""
    )


def test_signal_trigger_table_excludes_candidate_dependent_capabilities() -> None:
    assert not {"ultra_review", "sandbox", "hyper", "file_lock"} & set(PLANNER_SIGNAL_TRIGGERS)


def test_planner_route_signals_forward_task_evidence_not_escalation_switches() -> None:
    route = {
        "should_research": 1,
        "route_features": {
            "risk_score": 55,
            "has_hard_signal": True,
            "nested": {"a": [1, 2], "worker_id": "w"},
            "obj": object(),
            # canonical seam rejects these keys -> they must never be forwarded
            "local_reflex_provider": "ollama",
            "route_lane": "hardened",
            "model_name": "x",
            "target_path": "/tmp/x",
        },
        "research_context": {"role": "claim_scout"},
        "recommended_flow": "hyper_sprint",
        "escalate": True,
        "distant_scout_plan": {"x": 1},
    }

    out = planner_route_signals(route)

    assert set(out) == set(PLANNER_ROUTE_SIGNAL_KEYS)
    assert out["should_research"] is True
    assert out["route_features"]["risk_score"] == 55
    assert out["route_features"]["obj"] is None
    assert out["route_features"]["nested"] == {"a": [1, 2]}
    for key in ("local_reflex_provider", "route_lane", "model_name", "target_path"):
        assert key not in out["route_features"]
    assert "research_context" not in out
    assert "recommended_flow" not in out and "escalate" not in out
    assert planner_route_signals(None) == {}


def test_forwarded_route_signals_pass_the_canonical_planning_seam() -> None:
    """The forwarded route must be accepted by the canonical seam and reach the planner."""

    from nexus.services.runtime_compat import (
        build_canonical_runtime_context,
        plan_canonical_task_bundle,
    )
    from nexus.services.unified_runtime import UnifiedRuntimeRequest, build_online_route

    flow_route = {
        "should_research": True,
        "route_features": {
            "risk_score": 72,
            "doc_scout_hits": 2,
            "local_reflex_provider": "ollama",
            "route_lane": "hardened",
        },
    }
    route = build_online_route(
        recommended_flow="direct", gateway_provider="agy", local_enabled=False
    )
    for key, value in planner_route_signals(flow_route).items():
        route.setdefault(key, value)
    request = UnifiedRuntimeRequest(
        task_id="sprint-seam-s0-a1",
        workspace_revision="fixture-rev",
        task_statement="Fix the parser so the hidden verification test passes.",
        task_type="repair",
        route=route,
        online_prompt="p",
        online_payload="x",
        online_phase="R",
        online_model_name="m",
        online_output_schema={"status": "APPROVED | FAIL"},
    )

    bundle = plan_canonical_task_bundle(build_canonical_runtime_context(request))
    snapshot = bundle.plan_payload["signal_snapshot"]

    assert snapshot["doc_scout_hits"] == 2
    assert snapshot["risk_score_0_100"] == 72


@pytest.mark.parametrize(
    ("snapshot", "signal"),
    [({"xray_signal": True}, "xray_signal"), ({"cross_module": True, "risk_score": 60}, "cross_module")],
)
def test_xray_fires_on_the_planners_deep_scan_selection(snapshot, signal) -> None:
    """#2688: xray was selected on high-risk cross-module tasks but always skipped."""
    calls: list[str] = []
    invoker = build_escalate_gated_invoker("xray", real_invoker=_real(calls))

    receipt = invoker(_context("xray", reasons=["deep_scan_or_dependency_signal"], snapshot=snapshot))

    assert calls == ["sprint-abc-s0-a1"]
    assert receipt["trigger_source"] == f"{PLANNER_SIGNAL_TRIGGER_SOURCE}:{signal}"


def test_xray_needs_the_planners_deep_scan_reason() -> None:
    calls: list[str] = []
    invoker = build_escalate_gated_invoker("xray", real_invoker=_real(calls))

    receipt = invoker(
        _context("xray", reasons=["available_but_not_selected"], snapshot={"cross_module": True})
    )

    assert calls == [] and receipt["skip_reason"] == SKIP_POLICY_NOT_TRIGGERED


def test_hyper_sprint_flow_name_triggers_the_gate() -> None:
    """route_decider/planner emit "hyper_sprint"; the gate only accepted "hyper" (#2688)."""
    calls: list[str] = []
    invoker = build_escalate_gated_invoker("hyper", real_invoker=_real(calls))
    context = _context("hyper", reasons=[], snapshot={}, selected=False)
    context["route"]["recommended_flow"] = "hyper_sprint"

    invoker(context)

    assert calls == ["sprint-abc-s0-a1"]
