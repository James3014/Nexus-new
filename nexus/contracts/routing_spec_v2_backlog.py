from __future__ import annotations

from typing import Any, Mapping


ROUTING_SPEC_V2_BACKLOG_GATE_SCHEMA = "nexus.routing_spec_v2_backlog_gate.v1"

FORBIDDEN_PATH_MARKERS = (
    "nexus_swarm/",
    "nexus-swarm/",
    "benchmarks/",
    "logs/",
    "packages/",
)


def build_routing_spec_v2_backlog_gate(
    entries: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Gate routing-spec-v2 backlog items without mutating forbidden paths."""

    items = [_entry_readout(entry) for entry in (entries or _default_entries())]
    blockers = _blockers(items)
    return {
        "schema": ROUTING_SPEC_V2_BACKLOG_GATE_SCHEMA,
        "status": "PASS" if not blockers else "RETURN",
        "implementation_complete": False,
        "production_boundary_ready": not blockers,
        "public_benchmark_allowed": False,
        "runtime_update_allowed": False,
        "items": items,
        "blockers": blockers,
        "claim_boundary": [
            "Routing spec v2 backlog gates track deploy boundaries only.",
            "They do not implement forbidden-path swarm code or unlock public benchmark claims.",
            "Sidecar and NSP work require a separate scoped task with explicit path permission.",
        ],
    }


def _entry_readout(entry: Mapping[str, Any]) -> dict[str, Any]:
    target_paths = [str(item) for item in entry.get("target_paths", []) or [] if str(item)]
    forbidden_paths = [path for path in target_paths if _is_forbidden(path)]
    status = str(entry.get("status") or "").strip() or (
        "FORBIDDEN_PATH_BOUNDARY" if forbidden_paths else "READY_FOR_ALLOWED_PATH_IMPLEMENTATION"
    )
    return {
        "id": str(entry.get("id") or "unknown"),
        "title": str(entry.get("title") or ""),
        "status": status,
        "target_paths": target_paths,
        "forbidden_paths": forbidden_paths,
        "allowed_adapter_path": str(entry.get("allowed_adapter_path") or ""),
        "next_gate": str(entry.get("next_gate") or "separate_scoped_implementation"),
        "runtime_update_allowed": bool(entry.get("runtime_update_allowed", False)),
        "public_benchmark_allowed": bool(entry.get("public_benchmark_allowed", False)),
    }


def _blockers(items: list[Mapping[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for item in items:
        item_id = str(item.get("id") or "unknown")
        if not item.get("id"):
            blockers.append("missing_backlog_item_id")
        if item.get("runtime_update_allowed"):
            blockers.append(f"{item_id}:runtime_update_allowed")
        if item.get("public_benchmark_allowed"):
            blockers.append(f"{item_id}:public_benchmark_allowed")
        if item.get("forbidden_paths") and str(item.get("status")) != "FORBIDDEN_PATH_BOUNDARY":
            blockers.append(f"{item_id}:forbidden_path_without_boundary")
    return sorted(set(blockers))


def _is_forbidden(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(marker in normalized for marker in FORBIDDEN_PATH_MARKERS)


def _default_entries() -> list[dict[str, Any]]:
    return [
        {
            "id": "service_mesh_sidecar",
            "title": "Envoy sidecar injection and traffic controller",
            "target_paths": ["nexus-swarm/webhook/mutating_webhook.go", "manager/traffic_controller.go"],
            "status": "FORBIDDEN_PATH_BOUNDARY",
            "allowed_adapter_path": "docs/plans/NEXUS_ROUTING_SPEC_V2_DEPLOY_BOUNDARY.md",
        },
        {
            "id": "registry_board_nsp_v2",
            "title": "Registry Board 2.0 and NSP v0.2 dual stream",
            "target_paths": ["nexus-swarm/pb/nsp_v2.proto", "manager/registry_board_20.go"],
            "status": "FORBIDDEN_PATH_BOUNDARY",
            "allowed_adapter_path": "docs/plans/NEXUS_ROUTING_SPEC_V2_DEPLOY_BOUNDARY.md",
        },
        {
            "id": "rlm_recursive_orchestration",
            "title": "Full X/R-loop recursive execution orchestration",
            "target_paths": ["nexus/app/research_flow_service.py", "nexus/engine/rlm_controller.py"],
            "status": "READY_FOR_ALLOWED_PATH_IMPLEMENTATION",
            "allowed_adapter_path": "nexus/engine/rlm_controller.py",
        },
    ]
