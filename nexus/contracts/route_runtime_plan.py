from __future__ import annotations

from typing import Any, Mapping


ROUTE_RUNTIME_PLAN_SCHEMA = "nexus.route_runtime_plan.v1"


def build_route_runtime_plan_from_pregate(pregate: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a read-only route DAG pregate into a non-dispatch runtime plan."""

    nodes = [dict(node) for node in _list_of_mappings(pregate.get("nodes"))]
    blockers = _blockers(pregate)
    return {
        "schema": ROUTE_RUNTIME_PLAN_SCHEMA,
        "status": "PASS" if not blockers else "RETURN",
        "source_schema": str(pregate.get("schema") or ""),
        "dispatch_mode": "read_only_plan",
        "runtime_dispatch_changed": False,
        "claim_verdict": "NOT_EVALUATED",
        "public_benchmark_allowed": False,
        "runtime_update_allowed": False,
        "execution_slots": _execution_slots(nodes),
        "parallelizable_edges": list(_list_of_mappings(pregate.get("parallelizable_edges"))),
        "isolated_serial_capabilities": [
            str(node.get("capability"))
            for node in nodes
            if str(node.get("execution_slot") or "") == "serial_forced_swarm"
        ],
        "required_receipts": dict(pregate.get("required_receipts") or {}),
        "blockers": blockers,
        "claim_boundary": [
            "Route runtime plans consume route DAG pregate artifacts without dispatching work.",
            "They must not decide delivery, promotion, public readiness, or claim verdicts.",
        ],
    }


def _blockers(pregate: Mapping[str, Any]) -> list[str]:
    blockers = list(pregate.get("blockers", []) or [])
    if pregate.get("status") != "PASS":
        blockers.append("route_dag_pregate_not_pass")
    if bool(pregate.get("runtime_dispatch_changed", False)):
        blockers.append("runtime_dispatch_changed")
    if bool(pregate.get("public_benchmark_allowed", False)):
        blockers.append("public_benchmark_allowed_in_pregate")
    if str(pregate.get("claim_verdict") or "NOT_EVALUATED") != "NOT_EVALUATED":
        blockers.append("claim_verdict_evaluated_in_pregate")
    return sorted(set(str(blocker) for blocker in blockers if str(blocker)))


def _execution_slots(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "capability": str(node.get("capability") or ""),
            "slot": str(node.get("execution_slot") or "standard"),
            "state": str(node.get("state") or ""),
            "decision_origin": str(node.get("decision_origin") or ""),
            "required_receipts": list(node.get("required_receipts") or []),
        }
        for node in nodes
    ]


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]
