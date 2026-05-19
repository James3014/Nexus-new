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
    assert pregate["claim_verdict"] == "NOT_EVALUATED"
    assert pregate["claim_boundary"][0] == "Route DAG pregate is a read-only planning artifact."
    assert all(node["claim_verdict"] == "NOT_EVALUATED" for node in pregate["demand_nodes"])
    assert pregate["demand_nodes"][0]["decision_origin"]
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
    assert pregate["claim_verdict"] == "NOT_EVALUATED"
    assert "unknown_capability:missing_capability_node" in pregate["blockers"]
    assert "unknown_capability:missing_required_receipts" in pregate["blockers"]


def test_route_dag_pregate_blocks_required_pre_model_rescue_and_serializes_swarm() -> None:
    pregate = build_route_dag_pregate(
        capability_plan={
            "schema_version": "nexus_capability_plan_v1",
            "planner_mode": "dry_run",
            "required_capabilities": ["artifact_gate"],
            "selected_capabilities": ["codeintel"],
        },
        capability_nodes={
            "artifact_gate": {
                "category": "validation",
                "default_state": "required",
                "capability_contract_type": "required",
                "pre_model_rescue_planned": True,
                "forced_swarm": True,
                "parallelizable_with": ["codeintel"],
                "evidence_outputs": ["artifact_receipt"],
            },
            "codeintel": {
                "category": "discovery",
                "parallelizable_with": ["artifact_gate"],
                "evidence_outputs": ["code_scan"],
            },
        },
    )

    assert pregate["status"] == "RETURN"
    assert "artifact_gate:required_capability_pre_model_rescue_planned" in pregate["blockers"]
    assert pregate["nodes"][0]["execution_slot"] == "serial_forced_swarm"
    assert pregate["parallelizable_edges"] == []


def test_route_dag_pregate_serializes_autonomic_router_forced_swarm() -> None:
    pregate = build_route_dag_pregate(
        capability_plan={
            "schema_version": "nexus_capability_plan_v1",
            "planner_mode": "dry_run",
            "selected_capabilities": ["codeintel", "research"],
        },
        capability_nodes={
            "codeintel": {
                "category": "discovery",
                "parallelizable_with": ["research"],
                "evidence_outputs": ["code_scan"],
            },
            "research": {
                "category": "discovery",
                "parallelizable_with": ["codeintel"],
                "evidence_outputs": ["source_receipt"],
            },
        },
        autonomic_pre_route={
            "status": "PASS",
            "mode": "swarm",
            "forced_swarm_capabilities": ["codeintel"],
            "selected_capabilities": ["codeintel"],
        },
    )

    assert pregate["status"] == "PASS"
    assert pregate["nodes"][0]["capability"] == "codeintel"
    assert pregate["nodes"][0]["execution_slot"] == "serial_forced_swarm"
    assert pregate["parallelizable_edges"] == []


def test_route_dag_pregate_blocks_autonomic_pre_route_boundary_crossing() -> None:
    pregate = build_route_dag_pregate(
        capability_plan={
            "schema_version": "nexus_capability_plan_v1",
            "planner_mode": "dry_run",
            "selected_capabilities": ["codeintel"],
        },
        capability_nodes={
            "codeintel": {"category": "discovery", "evidence_outputs": ["code_scan"]},
        },
        autonomic_pre_route={
            "status": "PASS",
            "runtime_dispatch_changed": True,
            "runtime_update_allowed": True,
            "public_benchmark_allowed": True,
        },
    )

    assert pregate["status"] == "RETURN"
    assert "autonomic_pre_route_attempted_dispatch" in pregate["blockers"]
    assert "autonomic_pre_route_attempted_runtime_update" in pregate["blockers"]
    assert "autonomic_pre_route_attempted_public_benchmark_unlock" in pregate["blockers"]
