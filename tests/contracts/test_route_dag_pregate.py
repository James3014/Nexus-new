from __future__ import annotations

from nexus.contracts.route_dag_pregate import ROUTE_DAG_PREGATE_SCHEMA, build_route_dag_pregate
from nexus.engine.capability_planner import CapabilityPlanner, default_capability_nodes


def test_route_dag_pregate_exposes_dependencies_receipts_and_fallbacks() -> None:
    plan = CapabilityPlanner().plan(
        task_desc="Fix cross-module bug with research and claim-safe evidence",
        task_type="bug",
        route={
            "should_research": True,
            "route_features": {
                "risk_score": 80,
                "is_cross_module_task": True,
                "candidate_count": 3,
                "has_hard_signal": True,
            },
        },
        codeintel={"impact_report_present": True},
    ).to_dict()

    pregate = build_route_dag_pregate(
        capability_plan=plan,
        capability_nodes=default_capability_nodes(),
    )

    assert pregate["schema"] == ROUTE_DAG_PREGATE_SCHEMA
    assert pregate["status"] == "PASS"
    assert pregate["claim_boundary"][0] == "Route DAG pregate is a read-only planning artifact."
    assert pregate["required_receipts"]["codeintel"] == ["code_scan", "code_impact", "related_tests"]
    assert pregate["fallback_policy_by_capability"]["artifact_gate"] == "fail_closed"
    assert pregate["retry_policy_by_capability"]["artifact_gate"] == "no_retry_fail_closed"
    assert pregate["retry_policy_by_capability"]["codeintel"] == "bounded_retry_once"
    assert {"from": "artifact_gate", "to": "codeintel", "dependency_planned": "true"} in pregate["dependency_edges"]
    assert {"a": "codeintel", "b": "research"} in pregate["parallelizable_edges"]


def test_route_dag_pregate_returns_when_selected_node_is_unknown() -> None:
    pregate = build_route_dag_pregate(
        capability_plan={
            "schema_version": "nexus_capability_plan_v1",
            "planner_mode": "dry_run",
            "selected_capabilities": ["unknown_capability"],
        },
        capability_nodes={},
    )

    assert pregate["status"] == "RETURN"
    assert "unknown_capability:missing_capability_node" in pregate["blockers"]
    assert "unknown_capability:missing_required_receipts" in pregate["blockers"]
