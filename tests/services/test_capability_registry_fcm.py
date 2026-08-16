"""FCM F0+F1: wiring matrix + selected-capability full coverage (no new route)."""

from __future__ import annotations

from typing import Any

from nexus.engine.capability_contracts import CapabilityPlan
from nexus.engine.capability_planner import default_capability_nodes
from nexus.services.capability_registry import (
    GAP_CLASSES,
    SKIP_REASONS,
    build_default_mainchain_invokers,
    build_wiring_matrix,
    coverage_counts_from_receipt,
    ensure_selected_coverage_invokers,
    list_planner_capability_names,
)
from nexus.services.mainchain_entry import (
    build_mainchain_capability_invokers,
    run_mainchain,
)
from nexus.services.unified_runtime import (
    UnifiedRuntime,
    UnifiedRuntimeRequest,
    normalize_online_invoker_payload,
)


def test_f0_wiring_matrix_covers_all_planner_nodes() -> None:
    nodes = default_capability_nodes()
    matrix = build_wiring_matrix()
    assert matrix["node_count"] == len(nodes)
    assert matrix["node_count"] == len(list_planner_capability_names())
    assert matrix["routing_surface_changed"] is False
    assert matrix["new_topology_introduced"] is False
    assert matrix["new_route_mode_introduced"] is False
    names = {row["name"] for row in matrix["rows"]}
    assert names == set(nodes.keys())
    for row in matrix["rows"]:
        assert row["gap_class"] in GAP_CLASSES
        assert "has_mainchain_handler" in row
        assert "feeds_online_compact" in row
        assert "escalate_only" in row
        assert "maturity" in row


def test_registry_has_handler_for_every_planner_node() -> None:
    names = list_planner_capability_names()
    invokers = build_default_mainchain_invokers()
    assert set(invokers.keys()) == set(names)
    # escalate-only still has callable (explicit skip)
    assert callable(invokers["swarm"])
    assert callable(invokers["hyper"])
    assert callable(invokers["codeintel"])


def test_explicit_skip_invoker_whitelist_reason() -> None:
    invokers = build_default_mainchain_invokers()
    skip_result = invokers["swarm"]({"task_id": "t-skip"})
    assert skip_result["skipped"] is True
    assert skip_result["invoked"] is False
    assert skip_result["skip_reason"] in SKIP_REASONS
    assert skip_result["evidence_refs"]


class _MultiSelectPlanner:
    def plan(self, **_: object) -> CapabilityPlan:
        return CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            selected_capabilities=[
                "codeintel",
                "artifact_gate",
                "claim_gate",
                "delivery_gate",
                "swarm",  # escalate → explicit skip
                "belief",  # stub invoke
                "hyper",  # escalate skip
                "memory",  # stub
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


def test_unified_runtime_selected_full_coverage_invoked_or_skipped() -> None:
    def online(context: dict[str, Any]) -> dict[str, Any]:
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
        task_id="fcm-cover-001",
        workspace_revision="rev-fcm",
        task_statement="scan impact risk codeintel refactor with governance",
        task_type="codeintel",
        route={
            "recommended_flow": "direct",
            "injected_transport": True,
            "online_policy": "auto",
            "mainchain_entry": True,
        },
        online_enabled=True,
        online_prompt="task",
        codeintel={
            "scan_report_present": True,
            "impact_report_present": True,
            "risk_score": 5,
            "impacted_files_count": 1,
        },
    )
    # Intentionally partial invokers — UR must still cover selected via registry.
    partial = {"codeintel": build_default_mainchain_invokers()["codeintel"]}
    receipt = UnifiedRuntime(planner=_MultiSelectPlanner()).run(
        req,
        online_invoker=online,
        capability_invokers=partial,
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

    selected = set(receipt["context_trace"]["selected_capabilities"])
    rows = {item["name"]: item for item in receipt["capabilities"]}
    assert selected == set(rows.keys())
    for name in selected:
        row = rows[name]
        assert row["status"] in {"INVOKED", "SKIPPED", "SELECTED_NOT_EXECUTED"}
        # F1: no silent missing — every selected has a row
        if row["status"] == "SKIPPED":
            assert row.get("skip_reason") or row.get("reason")
            assert row.get("evidence_refs")
        if row["status"] == "INVOKED":
            assert row.get("invoked") is True
            assert row.get("evidence_refs") or row.get("physical_callable")

    coverage = receipt["capability_coverage"]
    assert coverage["selected_count"] == len(selected)
    assert coverage["missing_count"] == 0
    assert coverage["coverage_ok"] is True
    assert coverage["selected_count"] == coverage["invoked_count"] + coverage["skipped_count"]
    assert receipt["claim_boundary"]["public_claim_allowed"] is False

    # escalate names should be SKIPPED not INVOKED
    assert rows["swarm"]["status"] == "SKIPPED"
    assert rows["hyper"]["status"] == "SKIPPED"
    # codeintel real path INVOKED
    assert rows["codeintel"]["status"] == "INVOKED"


def test_mainchain_entry_uses_full_registry_not_partial_handpick() -> None:
    invokers = build_mainchain_capability_invokers()
    names = list_planner_capability_names()
    assert set(invokers.keys()) == set(names)

    def online(context: dict[str, Any]) -> dict[str, Any]:
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
        task_id="fcm-entry-001",
        workspace_revision="rev-fcm",
        task_statement="scan impact risk codeintel refactor module",
        task_type="codeintel",
        route={
            "recommended_flow": "direct",
            "injected_transport": True,
            "online_policy": "auto",
            "online_invoker_provider": "agy",
            "workforce_bindings": {
                "online": {
                    "worker_id": "agy_flash",
                    "controls": [
                        "task_card",
                        "allowed_files",
                        "mandatory_commands",
                        "independent_verification",
                    ],
                }
            },
        },
        online_enabled=True,
        online_prompt="task",
        codeintel={
            "scan_report_present": True,
            "risk_score": 4,
            "impact_report_present": True,
            "workspace_root": "/tmp",
            "verify_commands": ["echo ok"],
            "verify_timeout_sec": 10,
            "mempalace_tenant_id": "fcm-entry-tenant",
            "mempalace_artifact": {
                "artifact_id": "fcm-entry-001",
                "content": "full registry not partial handpick",
            },
            "mempalace_artifact_type": "task_receipt",
            "mempalace_query": "fcm-entry-001",
        },
    )
    receipt = run_mainchain(
        req,
        online_invoker=online,
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
        with_nexus_armor=True,
    )
    cov = coverage_counts_from_receipt(receipt)
    assert cov["coverage_ok"] is True
    assert cov["missing_count"] == 0
    assert receipt["claim_boundary"]["public_claim_allowed"] is False
    # FREEZE: no product topology on receipt planner
    assert "execution_topology" not in (receipt.get("planner") or {})


def test_ensure_selected_fills_missing_with_auto_skip() -> None:
    filled = ensure_selected_coverage_invokers(
        ["codeintel", "totally_unknown_cap"],
        {"codeintel": build_default_mainchain_invokers()["codeintel"]},
    )
    assert "totally_unknown_cap" in filled
    out = filled["totally_unknown_cap"]({"task_id": "x"})
    assert out["skipped"] is True
    assert out["skip_reason"] in SKIP_REASONS
