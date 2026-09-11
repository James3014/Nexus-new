from __future__ import annotations

from nexus.contracts.context_assembly import (
    build_context_assembly_contract,
    validate_context_assembly_contract,
)


def _sources():
    return [
        {"source_id": "L0:rules", "kind": "L0", "estimated_tokens": 10},
        {"source_id": "L1:index", "kind": "L1", "estimated_tokens": 10},
    ]


def _planner_context():
    return {
        "planner_decision_id": "planner-decision-472",
        "planner_plan_hash": "c" * 64,
        "selected_capability_ids": ("prompt_compression",),
        "materialized_evidence_ids": ("evidence:ri",),
    }


def test_g1_semantic_context_requires_package_hash() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-472-hash",
        sources=_sources(),
        token_budget=100,
        **_planner_context(),
    )
    payload.pop("package_hash")

    blockers = validate_context_assembly_contract(payload)

    assert "missing_context_package_hash" in blockers


def test_serialized_consumer_projection_requires_projection_hash() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-472-projection",
        sources=_sources(),
        token_budget=100,
        **_planner_context(),
        serialized_capability_ids=("prompt_compression",),
        consumer_role="main_engineer",
        consumer_channel="online",
    )
    payload.pop("consumer_projection_hash")

    blockers = validate_context_assembly_contract(payload)

    assert "missing_consumer_projection_hash" in blockers
    assert "missing_context_package_hash" not in blockers


def test_legacy_empty_v1_payload_remains_valid_without_hash_fields() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-legacy-no-hash",
        sources=_sources(),
        token_budget=100,
    )
    payload.pop("package_hash")
    payload.pop("consumer_projection_hash")

    blockers = validate_context_assembly_contract(payload)

    assert "missing_context_package_hash" not in blockers
    assert "missing_consumer_projection_hash" not in blockers
    assert blockers == []
