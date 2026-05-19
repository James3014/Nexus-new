from __future__ import annotations

from typing import Any, Mapping


ROUTE_DAG_PREGATE_SCHEMA = "nexus.route_dag_pregate.v1"


def build_route_dag_pregate(
    *,
    capability_plan: Mapping[str, Any],
    capability_nodes: Mapping[str, Any],
) -> dict[str, Any]:
    planned = _planned_capabilities(capability_plan)
    nodes = [_node_readout(capability, state, capability_nodes.get(capability)) for capability, state in planned.items()]
    blockers = _blockers(nodes)
    return {
        "schema": ROUTE_DAG_PREGATE_SCHEMA,
        "status": "PASS" if not blockers else "RETURN",
        "planner_mode": str(capability_plan.get("planner_mode") or ""),
        "plan_schema_version": str(capability_plan.get("schema_version") or ""),
        "dependency_edges": _dependency_edges(nodes),
        "parallelizable_edges": _parallelizable_edges(nodes),
        "required_receipts": {
            node["capability"]: node["required_receipts"]
            for node in nodes
            if node["required_receipts"]
        },
        "fallback_policy_by_capability": {
            node["capability"]: node["fallback_policy"]
            for node in nodes
        },
        "retry_policy_by_capability": {
            node["capability"]: node["retry_policy"]
            for node in nodes
        },
        "nodes": nodes,
        "blockers": blockers,
        "claim_boundary": [
            "Route DAG pregate is a read-only planning artifact.",
            "It exposes dependencies, parallelizable work, required receipts, fallback policy, and retry policy.",
            "It must not decide delivery, promotion, public readiness, or runtime dispatch by itself.",
        ],
    }


def _planned_capabilities(plan: Mapping[str, Any]) -> dict[str, str]:
    buckets = (
        ("required_capabilities", "required"),
        ("selected_capabilities", "selected"),
        ("conditional_capabilities", "conditional"),
        ("optional_capabilities", "optional"),
        ("pending_capabilities", "pending"),
    )
    planned: dict[str, str] = {}
    for key, state in buckets:
        for capability in _strings(plan.get(key)):
            planned.setdefault(capability, state)
    return dict(sorted(planned.items()))


def _node_readout(capability: str, state: str, raw_node: Any) -> dict[str, Any]:
    node = _node_dict(raw_node)
    category = str(node.get("category") or "")
    default_state = str(node.get("default_state") or "")
    return {
        "capability": capability,
        "state": state,
        "category": category,
        "maturity": str(node.get("maturity") or ""),
        "dependencies": _strings(node.get("dependencies")),
        "parallelizable_with": _strings(node.get("parallelizable_with")),
        "required_receipts": _strings(node.get("evidence_outputs")),
        "fallback_policy": _fallback_policy(state=state, category=category, default_state=default_state),
        "retry_policy": _retry_policy(state=state, category=category, default_state=default_state),
        "node_present": bool(node),
    }


def _node_dict(raw_node: Any) -> dict[str, Any]:
    if raw_node is None:
        return {}
    if hasattr(raw_node, "to_dict"):
        data = raw_node.to_dict()
        return data if isinstance(data, dict) else {}
    if isinstance(raw_node, Mapping):
        return dict(raw_node)
    return {}


def _fallback_policy(*, state: str, category: str, default_state: str) -> str:
    if state == "required" or default_state == "required":
        return "fail_closed"
    if category in {"governance", "validation"}:
        return "fail_closed"
    if state in {"conditional", "pending"}:
        return "defer_or_degrade_to_baseline"
    return "degrade_to_baseline"


def _retry_policy(*, state: str, category: str, default_state: str) -> str:
    if state == "required" or default_state == "required":
        return "no_retry_fail_closed"
    if category in {"governance", "validation"}:
        return "single_targeted_replay_then_return"
    if state in {"conditional", "pending"}:
        return "defer_without_retry"
    return "bounded_retry_once"


def _dependency_edges(nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    planned = {node["capability"] for node in nodes}
    edges: list[dict[str, str]] = []
    for node in nodes:
        for dependency in node["dependencies"]:
            edges.append(
                {
                    "from": dependency,
                    "to": node["capability"],
                    "dependency_planned": str(dependency in planned).lower(),
                }
            )
    return sorted(edges, key=lambda item: (item["to"], item["from"]))


def _parallelizable_edges(nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    planned = {node["capability"] for node in nodes}
    pairs: set[tuple[str, str]] = set()
    for node in nodes:
        for peer in node["parallelizable_with"]:
            if peer in planned:
                pairs.add(tuple(sorted((node["capability"], peer))))
    return [{"a": left, "b": right} for left, right in sorted(pairs)]


def _blockers(nodes: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for node in nodes:
        if not node["node_present"]:
            blockers.append(f"{node['capability']}:missing_capability_node")
        if node["state"] in {"required", "selected"} and not node["required_receipts"]:
            blockers.append(f"{node['capability']}:missing_required_receipts")
    return sorted(set(blockers))


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item)]
    return []
