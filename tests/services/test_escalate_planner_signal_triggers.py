"""Online A/B gap A: escalate-only executors fire on the planner's task signals."""

from __future__ import annotations

from pathlib import Path
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
    [
        ({"xray_signal": True}, "xray_signal"),
        ({"cross_module": True, "risk_score": 60}, "cross_module"),
    ],
)
def test_xray_fires_on_the_planners_deep_scan_selection(snapshot, signal) -> None:
    """#2688: xray was selected on high-risk cross-module tasks but always skipped."""
    calls: list[str] = []
    invoker = build_escalate_gated_invoker("xray", real_invoker=_real(calls))

    receipt = invoker(
        _context("xray", reasons=["deep_scan_or_dependency_signal"], snapshot=snapshot)
    )

    assert calls == ["sprint-abc-s0-a1"]
    assert receipt["trigger_source"] == f"{PLANNER_SIGNAL_TRIGGER_SOURCE}:{signal}"


def test_xray_needs_the_planners_deep_scan_reason() -> None:
    calls: list[str] = []
    invoker = build_escalate_gated_invoker("xray", real_invoker=_real(calls))

    receipt = invoker(
        _context("xray", reasons=["available_but_not_selected"], snapshot={"cross_module": True})
    )

    assert calls == [] and receipt["skip_reason"] == SKIP_POLICY_NOT_TRIGGERED


def test_xray_executor_leaves_the_scanned_worktree_and_cwd_clean(tmp_path, monkeypatch) -> None:
    """#2688 reviews: the report followed cwd, then landed in the candidate worktree."""
    import subprocess

    from nexus.core.belief_contracts import CapabilityExecutionPlan
    from nexus.core.capability_executor_registry import _exec_xray

    workspace = tmp_path / "ws"
    (workspace / "pkg").mkdir(parents=True)
    imports = "".join(f"import mod{i}\n" for i in range(20))  # > 15 crossings
    (workspace / "pkg" / "hub.py").write_text(
        imports + "def f():\n    return 1\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q", str(workspace)], check=True)  # no .nexus ignore
    subprocess.run(["git", "-C", str(workspace), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-q",
            "-m",
            "c",
        ],
        check=True,
    )
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    plan = CapabilityExecutionPlan(
        plan_id="p-xray",
        task_id="t-xray",
        constraints={"workspace_root": str(workspace), "target_file": "pkg/hub.py"},
    )

    receipt = _exec_xray(plan, "deep scan pkg")

    assert receipt.gate_passed is True
    status = subprocess.run(
        ["git", "-C", str(workspace), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert status == "", f"xray left files in the candidate worktree: {status}"
    assert not any(elsewhere.rglob("*")), "xray wrote under cwd"


def test_triggers_read_the_plan_inside_the_worker_path_envelope() -> None:
    """#2688 live witness: the Gateway worker path passes the planning-bundle envelope
    (plan under ``plan_payload``); the trigger read the envelope top level and skipped."""
    calls: list[str] = []
    invoker = build_escalate_gated_invoker("xray", real_invoker=_real(calls))
    flat = _context(
        "xray", reasons=["deep_scan_or_dependency_signal"], snapshot={"xray_signal": True}
    )
    envelope = dict(flat)
    envelope["planner"] = {
        "schema": "nexus.canonical_planning_bundle.v1",
        "plan_hash": "0" * 64,
        "context": {"task_desc": "x"},
        "plan_payload": flat["planner"],
    }

    receipt = invoker(envelope)

    assert calls == ["sprint-abc-s0-a1"]
    assert receipt["trigger_source"] == f"{PLANNER_SIGNAL_TRIGGER_SOURCE}:xray_signal"


def test_envelope_shape_matches_a_real_worker_dispatch_state() -> None:
    """The envelope keys come from a recorded live task (i2604 worker-dispatch canary)."""
    from nexus.services.capability_registry import _planner_plan

    envelope = {
        "canonical_execution_projection": {},
        "context": {},
        "plan_hash": "0" * 64,
        "plan_payload": {"selected_capabilities": ["xray"], "signal_snapshot": {}},
        "schema": "nexus.canonical_planning_bundle.v1",
    }

    assert _planner_plan({"planner": envelope}, "xray") == envelope["plan_payload"]
    assert _planner_plan({"planner": envelope["plan_payload"]}, "xray") == envelope["plan_payload"]
    assert _planner_plan({}, "xray") is None


@pytest.mark.parametrize(
    ("name", "reasons", "snapshot"),
    [
        ("research", ["context_or_retrieval_gap"], {"memory_hits": 3}),
        ("learn_mode", ["claim_or_citation_learning_signal"], {"learning_signal": True}),
        ("learn_phase_slo", ["learn_phase_policy_needed"], {"learning_signal": True}),
        ("multi_agent", ["coordinated_ownership_required"], {"multi_agent_signal": True}),
    ],
)
def test_unscoped_writers_stay_skipped_on_the_worker_envelope(name, reasons, snapshot) -> None:
    """research / learn_* / multi_agent would write under cwd or block on the worker path
    (#2697 Codex review); they keep their pre-#2688 behaviour there until scoped."""
    calls: list[str] = []
    invoker = build_escalate_gated_invoker(name, real_invoker=_real(calls))
    flat = _context(name, reasons=reasons, snapshot=snapshot)
    envelope = dict(flat)
    envelope["planner"] = {"plan_hash": "0" * 64, "plan_payload": flat["planner"]}

    receipt = invoker(envelope)

    assert calls == [] and receipt["skip_reason"] == SKIP_POLICY_NOT_TRIGGERED


def test_xray_scans_the_worker_supplied_targets(tmp_path, monkeypatch) -> None:
    """#2688: with xray_targets from the worker context, xray scans those files, not the
    legacy default."""
    from nexus.core.belief_contracts import CapabilityExecutionPlan
    from nexus.core.capability_executor_registry import _exec_xray

    workspace = tmp_path / "ws"
    (workspace / "nexus" / "services").mkdir(parents=True)
    (workspace / "nexus" / "services" / "capability_registry.py").write_text("x = 1\n")
    (workspace / "pkg").mkdir()
    (workspace / "pkg" / "task.py").write_text("import os\n\ndef f():\n    return 1\n")
    monkeypatch.chdir(tmp_path)
    plan = CapabilityExecutionPlan(
        plan_id="p-xray",
        task_id="t-xray",
        constraints={
            "workspace_root": str(workspace),
            "xray_targets": ["pkg/task.py"],
            "target_files": ["nexus/services/capability_registry.py"],
        },
    )

    receipt = _exec_xray(plan, "deep scan")

    targets = receipt.outcome["scan_targets"] if isinstance(receipt.outcome, dict) else []
    assert [Path(t).name for t in targets] == ["task.py"]


def test_xray_never_scans_the_default_when_no_task_file_exists(tmp_path, monkeypatch) -> None:
    """#2700 Codex: an empty xray_targets fell back to an unrelated default target."""
    from nexus.core.belief_contracts import CapabilityExecutionPlan
    from nexus.core.capability_executor_registry import _exec_xray

    workspace = tmp_path / "ws"
    (workspace / "nexus" / "services").mkdir(parents=True)
    (workspace / "nexus" / "services" / "capability_registry.py").write_text("x = 1\n")
    monkeypatch.chdir(tmp_path)
    plan = CapabilityExecutionPlan(
        plan_id="p-xray",
        task_id="t-xray",
        # target_file can arrive from codeintel; an explicit xray_targets must win.
        constraints={
            "workspace_root": str(workspace),
            "xray_targets": [],
            "target_file": "nexus/services/capability_registry.py",
        },
    )

    receipt = _exec_xray(plan, "deep scan")

    assert receipt.gate_passed is False
    assert "no_existing_task_files" in repr(receipt)


def test_belief_reads_the_per_file_confidence_through_the_registry(tmp_path, monkeypatch) -> None:
    """#2721: belief had no constraint allowlist, so on every runtime path its executor
    saw no target file and returned the 0.7 default even with per-file evidence."""
    from nexus.core.belief_engine import BeliefEngine, repair_target_key
    from nexus.services.mainchain_entry import build_mainchain_capability_invokers
    from nexus.services.unified_runtime import materialize_selected_capability_evidence

    monkeypatch.chdir(tmp_path)
    engine = BeliefEngine()
    engine.update_belief("earlier", repair_target_key("pkg/a.py"), 0.2, "ev")
    plan = {"selected_capabilities": ["belief"], "signal_snapshot": {}}

    def confidence(context: dict) -> float:
        results, _ = materialize_selected_capability_evidence(
            planner_output={"plan_payload": plan, "plan_hash": "0" * 64},
            selected_capabilities=["belief"],
            task_id="later",
            task_statement="fix a",
            workspace_revision="w" * 40,
            plan_hash="0" * 64,
            planner_decision_id="d" * 64,
            capability_invokers={
                "belief": build_mainchain_capability_invokers(
                    codeintel={}, include_postflight_gates=True
                )["belief"]
            },
            capability_context={"workspace_root": str(tmp_path), **context},
            codeintel={},
        )
        return results["belief"]["response"]["response"]["outcome"]["confidence"]

    assert confidence({"belief_target_files": ["pkg/a.py"]}) == 0.2
    assert confidence({}) == 0.7
    # several entries are ambiguous: no file key, so a.py's confidence is not borrowed
    assert confidence({"belief_target_files": ["pkg/a.py", "pkg/new.py"]}) == 0.7
