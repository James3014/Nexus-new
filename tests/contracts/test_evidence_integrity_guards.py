from __future__ import annotations

from nexus.contracts.evidence_integrity_guards import (
    build_dedup_precision_receipt,
    build_entity_graph_integrity_receipt,
    build_union_merge_guard_receipt,
)


def test_union_merge_guard_enforces_caps() -> None:
    receipt = build_union_merge_guard_receipt(
        merge_driver_status="PASS",
        size_bytes=50_000_001,
        node_count=100_001,
    )

    assert receipt["schema"] == "nexus.union_merge_guard.v1"
    assert receipt["status"] == "RETURN"
    assert receipt["blockers"] == ["union_merge_node_cap_exceeded", "union_merge_size_cap_exceeded"]


def test_entity_graph_integrity_blocks_dangling_edges_and_missing_namespace() -> None:
    receipt = build_entity_graph_integrity_receipt(
        entities=[{"id": "a", "namespace": "nexus", "source_snapshot_id": "snap"}, {"id": "b"}],
        edges=[{"source": "a", "target": "missing"}],
    )

    assert receipt["schema"] == "nexus.entity_graph_integrity.v1"
    assert receipt["status"] == "RETURN"
    assert receipt["blockers"] == [
        "dangling_edge_detected",
        "entity_namespace_missing",
        "entity_source_snapshot_missing",
    ]


def test_dedup_precision_guard_blocks_short_ambiguous_merge() -> None:
    receipt = build_dedup_precision_receipt(
        left_key="skill:a",
        right_key="skill:b",
        label="ui",
        namespace="",
        reversible=False,
    )

    assert receipt["schema"] == "nexus.dedup_precision_guard.v1"
    assert receipt["status"] == "RETURN"
    assert receipt["blockers"] == [
        "dedup_namespace_missing",
        "dedup_not_reversible",
        "low_entropy_merge_detected",
    ]


def test_integrity_guards_pass_clean_inputs() -> None:
    merge = build_union_merge_guard_receipt(merge_driver_status="PASS", size_bytes=100, node_count=2)
    graph = build_entity_graph_integrity_receipt(
        entities=[
            {"id": "a", "namespace": "nexus", "source_snapshot_id": "snap"},
            {"id": "b", "namespace": "nexus", "source_snapshot_id": "snap"},
        ],
        edges=[{"source": "a", "target": "b"}],
    )
    dedup = build_dedup_precision_receipt(
        left_key="skill:a",
        right_key="skill:b",
        label="research verifier",
        namespace="nexus.skills",
    )

    assert merge["status"] == "PASS"
    assert graph["status"] == "PASS"
    assert dedup["status"] == "PASS"
