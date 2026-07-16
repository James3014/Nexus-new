"""P6: formal callers converge on MainchainEntry → CapabilityPlanner → UnifiedRuntime.

Contract tests + source-surface freeze for Gateway / PipelineRepair / CLI and
related formal runtime entry modules. Does not invent a second planner or route.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from nexus.engine.capability_contracts import CapabilityPlan
from nexus.services.mainchain_entry import run_mainchain, stamp_mainchain_route
from nexus.services.mainchain_route_freeze import (
    MAINCHAIN_AUTHORITY,
    single_planner_decision_id,
)
from nexus.services.unified_runtime import (
    UnifiedRuntimeRequest,
    normalize_online_invoker_payload,
)

REPO = Path(__file__).resolve().parents[2]

# Formal product entry surfaces (relative to repo root).
FORMAL_CALLER_PATHS: tuple[str, ...] = (
    "nexus/services/gateway.py",
    "nexus/engine/pipeline_repair.py",
    "scripts/engine/nexus_cli.py",
    "nexus/services/mainchain_entry.py",
    "nexus/services/unified_runtime.py",
)

# Modules that may retain compatibility shims — must still fail closed / not select.
COMPAT_LABELS: frozenset[str] = frozenset(
    {
        "compatibility",
        "legacy_shim",
        "non_formal",
        "fail_closed",
    }
)


class _Planner:
    def plan(self, **_: object) -> CapabilityPlan:
        return CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            selected_capabilities=[
                "codeintel",
                "artifact_gate",
                "claim_gate",
                "delivery_gate",
            ],
            required_capabilities=["codeintel"],
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


def _online(context: dict[str, Any]) -> dict[str, Any]:
    return normalize_online_invoker_payload(
        provider="fixture",
        task_id=str(context.get("task_id") or ""),
        invoked=True,
        output_delivered=True,
        gate_passed=True,
        provider_call_count=1,
        response={"ok": True},
        raw_response="ok",
        evidence_refs=[f"online:{context.get('task_id')}"],
    )


def _verifier(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": c["task_id"],
        "invoked": True,
        "gate_passed": True,
        "evidence_refs": [f"v:{c['task_id']}"],
    }


def _learning(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": c["task_id"],
        "invoked": True,
        "gate_passed": True,
        "evidence_refs": [f"l:{c['task_id']}"],
    }


def test_formal_caller_sources_import_unified_runtime_or_mainchain() -> None:
    """Each formal caller module references UnifiedRuntime / MainchainEntry path."""
    required_tokens = (
        "UnifiedRuntime",
        "ask_unified",
        "run_mainchain",
        "MainchainEntry",
        "UnifiedRuntimeRequest",
    )
    missing: list[str] = []
    for rel in FORMAL_CALLER_PATHS:
        path = REPO / rel
        assert path.is_file(), rel
        text = path.read_text(encoding="utf-8")
        if not any(tok in text for tok in required_tokens):
            missing.append(rel)
    assert missing == [], missing


def test_formal_caller_sources_do_not_define_second_planner_class() -> None:
    """No ClassDef named CapabilityPlanner outside engine/capability_planner.py."""
    hits: list[str] = []
    for rel in FORMAL_CALLER_PATHS:
        path = REPO / rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "CapabilityPlanner":
                hits.append(f"{rel}:{node.lineno}")
            if isinstance(node, ast.ClassDef) and node.name == "RouteMode":
                hits.append(f"{rel}:RouteMode:{node.lineno}")
    assert hits == [], hits


def test_gateway_ask_unified_single_planner_decision(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", "gemini")
    from nexus.services.gateway import BattlesuitGateway

    gateway = BattlesuitGateway(project_root=tmp_path)
    monkeypatch.setattr(
        gateway,
        "ask_structured",
        lambda *_a, **_k: ({"summary": "online"}, "online-response"),
    )
    req = UnifiedRuntimeRequest(
        task_id="gw-formal-1",
        workspace_revision="r",
        task_statement="scan impact risk codeintel",
        task_type="codeintel",
        route={
            "recommended_flow": "direct",
            "injected_transport": True,
            "online_policy": "auto",
            "mainchain_entry": True,
        },
        online_enabled=True,
        online_prompt="task",
        codeintel={"scan_report_present": True, "risk_score": 2},
    )
    receipt = gateway.ask_unified(
        req,
        verifier=_verifier,
        learning=_learning,
        receipt_path=tmp_path / "gw.json",
    )
    check = single_planner_decision_id(receipt)
    assert check["ok"] is True
    assert check["selection_authority"] == MAINCHAIN_AUTHORITY
    assert receipt["claim_boundary"]["public_claim_allowed"] is False
    assert receipt.get("planner_decision_id")


def test_mainchain_entry_run_mainchain_contract() -> None:
    route = stamp_mainchain_route(
        {"recommended_flow": "direct"}, product_entry="pipeline_repair"
    )
    assert route["mainchain_entry"] is True
    receipt = run_mainchain(
        UnifiedRuntimeRequest(
            task_id="mc-formal-1",
            workspace_revision="r",
            task_statement="scan impact risk codeintel",
            task_type="codeintel",
            route={
                "recommended_flow": "direct",
                "injected_transport": True,
                "online_policy": "auto",
                "mainchain_entry": True,
            },
            online_enabled=True,
            online_prompt="task",
            codeintel={"scan_report_present": True, "risk_score": 1},
        ),
        online_invoker=_online,
        planner=_Planner(),
        verifier=_verifier,
        learning=_learning,
    )
    assert single_planner_decision_id(receipt)["ok"] is True
    assert receipt["capability_evidence_bundle"]["planner_decision_id"] == receipt[
        "planner_decision_id"
    ]


def test_pipeline_repair_module_wires_unified_runtime() -> None:
    text = (REPO / "nexus/engine/pipeline_repair.py").read_text(encoding="utf-8")
    assert "UnifiedRuntime" in text
    assert "UnifiedRuntimeRequest" in text
    # Must not invent a parallel Online+Local product route string
    assert "online_local_v2" not in text
    assert "nexus_full_stack" not in text or "pop" in text or "strip" in text


def test_pipeline_repair_runtime_single_planner_decision_id(monkeypatch, tmp_path: Path) -> None:
    """Runtime: PipelineRepair composition enters UnifiedRuntime with one planner id."""
    from nexus.services.mainchain_entry import (
        build_mainchain_capability_invokers,
        stamp_mainchain_route,
        wrap_mainchain_online_invoker,
    )
    from nexus.services.unified_runtime import UnifiedRuntime, UnifiedRuntimeRequest

    # Source contract: pipeline_repair.py uses these exact composition symbols.
    pr_src = (REPO / "nexus/engine/pipeline_repair.py").read_text(encoding="utf-8")
    assert "build_mainchain_capability_invokers" in pr_src or "stamp_mainchain_route" in pr_src
    assert "UnifiedRuntime" in pr_src

    def online(context: dict[str, Any]) -> dict[str, Any]:
        return _online(context)

    route = stamp_mainchain_route(
        {
            "recommended_flow": "direct",
            "injected_transport": True,
            "online_policy": "auto",
            "mainchain_entry": True,
        },
        product_entry="pipeline_repair",
    )
    assert route.get("mainchain_entry") is True
    invokers = build_mainchain_capability_invokers(
        codeintel={"scan_report_present": True, "risk_score": 1}
    )
    wrapped = wrap_mainchain_online_invoker(online)
    req = UnifiedRuntimeRequest(
        task_id="pr-runtime-1",
        workspace_revision="r",
        task_statement="scan impact risk codeintel",
        task_type="codeintel",
        route=route,
        online_enabled=True,
        online_prompt="task",
        codeintel={"scan_report_present": True, "risk_score": 1},
    )
    receipt = UnifiedRuntime(planner=_Planner()).run(
        req,
        capability_invokers=invokers,
        online_invoker=wrapped,
        verifier=_verifier,
        learning=_learning,
    )
    check = single_planner_decision_id(receipt)
    assert check["ok"] is True
    assert check["selection_authority"] == MAINCHAIN_AUTHORITY
    assert receipt["capability_evidence_bundle"]["planner_decision_id"] == receipt[
        "planner_decision_id"
    ]
    assert receipt["claim_boundary"]["public_claim_allowed"] is False


def test_cli_module_uses_gateway_ask_unified() -> None:
    text = (REPO / "scripts/engine/nexus_cli.py").read_text(encoding="utf-8")
    assert "ask_unified" in text
    assert "UnifiedRuntimeRequest" in text


def test_cli_runtime_gateway_ask_unified_single_planner(monkeypatch, tmp_path: Path) -> None:
    """Runtime: CLI-equivalent Gateway.ask_unified path shares one planner_decision_id."""
    monkeypatch.setenv("NEXUS_OAUTH_PROVIDER", "gemini")
    from nexus.services.gateway import BattlesuitGateway
    from nexus.services.mainchain_entry import stamp_mainchain_route

    gateway = BattlesuitGateway(project_root=tmp_path)
    monkeypatch.setattr(
        gateway,
        "ask_structured",
        lambda *_a, **_k: ({"summary": "online"}, "online-response"),
    )
    route = stamp_mainchain_route(
        {
            "recommended_flow": "direct",
            "injected_transport": True,
            "online_policy": "auto",
            "mainchain_entry": True,
            "with_nexus_armor": True,
        },
        product_entry="nexus_cli",
    )
    req = UnifiedRuntimeRequest(
        task_id="cli-runtime-1",
        workspace_revision="r",
        task_statement="scan impact risk codeintel",
        task_type="codeintel",
        route=route,
        online_enabled=True,
        online_prompt="task",
        codeintel={"scan_report_present": True, "risk_score": 2},
    )
    receipt = gateway.ask_unified(
        req,
        verifier=_verifier,
        learning=_learning,
        receipt_path=tmp_path / "cli.json",
    )
    check = single_planner_decision_id(receipt)
    assert check["ok"] is True
    assert receipt["planner_decision_id"]
    assert receipt["capability_evidence_bundle"]["planner_decision_id"] == receipt[
        "planner_decision_id"
    ]
    assert receipt["claim_boundary"]["public_claim_allowed"] is False


def test_sprint_nightshift_dayshift_research_entries_if_present() -> None:
    """When formal Sprint/Nightshift/DayShift/Research entry modules exist, they
    must reference UnifiedRuntime / mainchain — not a second planner."""
    candidates = [
        "nexus/engine/hyper_sprint.py",
        "nexus/services/local_heal/hybrid_cloud_assist_runtime.py",
        "nexus/research/learn_mode.py",
        "nexus/engine/phases/research.py",
        "nexus/services/nightshift_runner.py",
        "nexus/engine/nightshift.py",
    ]
    found = 0
    bad: list[str] = []
    for rel in candidates:
        path = REPO / rel
        if not path.is_file():
            continue
        found += 1
        text = path.read_text(encoding="utf-8")
        # Soft contract: if they select capabilities themselves via a new planner class, fail
        if "class CapabilityPlanner" in text:
            bad.append(f"{rel}:defines_CapabilityPlanner")
        if 'RouteMode(' in text and "from nexus.contracts.hybrid_route import" not in text:
            # new RouteMode definition, not import
            if "class RouteMode" in text:
                bad.append(f"{rel}:defines_RouteMode")
    # At least some formal-adjacent modules exist in this repo
    assert found >= 1
    assert bad == [], bad


def test_bypass_allowlist_empty_for_mainchain_authority() -> None:
    """No second selection authority allowlist on freeze contract."""
    from nexus.services.mainchain_route_freeze import (
        ROUTE_AUTHORITY_FORBIDDEN,
        freeze_summary,
    )

    assert "CapabilitySelector" in ROUTE_AUTHORITY_FORBIDDEN
    summary = freeze_summary(repo_root=REPO)
    assert summary["route_authority"] == MAINCHAIN_AUTHORITY
    assert summary["routing_surface_changed"] is False
