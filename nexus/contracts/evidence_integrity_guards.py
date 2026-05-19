from __future__ import annotations

import math
from typing import Any, Mapping


def build_union_merge_guard_receipt(
    *,
    merge_driver_status: str,
    size_bytes: int,
    node_count: int,
    max_size_bytes: int = 50_000_000,
    max_node_count: int = 100_000,
) -> dict[str, Any]:
    blockers: list[str] = []
    if str(merge_driver_status).upper() != "PASS":
        blockers.append("union_merge_driver_not_pass")
    if int(size_bytes) > int(max_size_bytes):
        blockers.append("union_merge_size_cap_exceeded")
    if int(node_count) > int(max_node_count):
        blockers.append("union_merge_node_cap_exceeded")
    return _receipt("nexus.union_merge_guard.v1", blockers, {
        "merge_driver_status": str(merge_driver_status).upper(),
        "size_bytes": int(size_bytes),
        "node_count": int(node_count),
        "max_size_bytes": int(max_size_bytes),
        "max_node_count": int(max_node_count),
    })


def build_entity_graph_integrity_receipt(
    *,
    entities: list[Mapping[str, Any]],
    edges: list[Mapping[str, Any]],
) -> dict[str, Any]:
    blockers: list[str] = []
    entity_ids = {str(entity.get("id") or "") for entity in entities}
    for entity in entities:
        if not str(entity.get("namespace") or ""):
            blockers.append("entity_namespace_missing")
        if not str(entity.get("source_snapshot_id") or ""):
            blockers.append("entity_source_snapshot_missing")
    for edge in edges:
        if str(edge.get("source") or "") not in entity_ids or str(edge.get("target") or "") not in entity_ids:
            blockers.append("dangling_edge_detected")
    return _receipt("nexus.entity_graph_integrity.v1", blockers, {
        "entity_count": len(entities),
        "edge_count": len(edges),
    })


def build_dedup_precision_receipt(
    *,
    left_key: str,
    right_key: str,
    label: str,
    namespace: str = "",
    reversible: bool = True,
) -> dict[str, Any]:
    blockers: list[str] = []
    if not namespace:
        blockers.append("dedup_namespace_missing")
    if not reversible:
        blockers.append("dedup_not_reversible")
    if _low_information_label(label):
        blockers.append("low_entropy_merge_detected")
    if str(left_key) == str(right_key):
        blockers.append("dedup_self_merge")
    return _receipt("nexus.dedup_precision_guard.v1", blockers, {
        "left_key": str(left_key),
        "right_key": str(right_key),
        "label": str(label),
        "namespace": str(namespace),
        "reversible": bool(reversible),
    })


def _receipt(schema: str, blockers: list[str], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": schema,
        "status": "PASS" if not blockers else "RETURN",
        **payload,
        "runtime_update_allowed": False,
        "public_benchmark_allowed": False,
        "blockers": sorted(set(blockers)),
    }


def _low_information_label(value: str) -> bool:
    text = str(value or "").strip().lower()
    if len(text) < 4:
        return True
    counts = {char: text.count(char) for char in set(text)}
    entropy = -sum((count / len(text)) * math.log2(count / len(text)) for count in counts.values())
    return entropy < 1.5
