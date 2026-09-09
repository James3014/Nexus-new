from __future__ import annotations

from typing import Any

import pytest

from nexus.contracts.context_assembly import (
    CONTEXT_ASSEMBLY_CONTRACT_SCHEMA,
    ContextAssemblyContract,
    build_context_assembly_contract,
    validate_context_assembly_contract,
)


def _sources():
    return [
        {"source_id": "L0:rules", "kind": "L0", "estimated_tokens": 100},
        {"source_id": "L1:index", "kind": "L1", "estimated_tokens": 100},
        {"source_id": "history", "kind": "history", "estimated_tokens": 300, "priority": 20},
        {"source_id": "retrieval", "kind": "retrieval", "estimated_tokens": 250, "priority": 10},
    ]


def _source_ref():
    return {
        "repository": "James3014/Nexus-new",
        "revision": "a" * 40,
        "path": "nexus/contracts/context_assembly.py",
        "ranges": ["1-40"],
        "content_hash": "b" * 64,
    }


def test_context_assembly_contract_preserves_required_context_under_budget() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-001",
        sources=_sources(),
        token_budget=500,
    )

    assert payload["schema"] == CONTEXT_ASSEMBLY_CONTRACT_SCHEMA
    assert payload["status"] == "PASS"
    assert payload["preserved_L0_L1"] is True
    assert payload["kept_source_count"] == 3
    assert payload["dropped_source_count"] == 1
    assert payload["planner_binding_status"] == "NOT_APPLICABLE"
    assert payload["source_mode"] == "NO_SOURCE"
    assert payload["serialization_state"] == "NOT_BOUND"
    assert payload["physical_consumption_state"] == "NOT_PROVEN"
    assert payload["outcome_contribution_state"] == "NOT_PROVEN"
    assert len(payload["package_hash"]) == 64
    assert payload["blockers"] == []


def test_context_assembly_contract_returns_when_required_context_exceeds_budget() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-001",
        sources=_sources(),
        token_budget=150,
    )

    assert payload["status"] == "RETURN"
    assert "receipt:estimated_tokens_exceed_budget" in payload["blockers"]
    assert "receipt_not_pass" in payload["blockers"]


def test_context_assembly_validator_rejects_runtime_or_public_unlock_attempts() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-001",
        sources=_sources(),
        token_budget=500,
    )
    payload["runtime_update_allowed"] = True
    payload["public_benchmark_allowed"] = True

    assert validate_context_assembly_contract(payload) == [
        "context_assembly_must_not_unlock_public_benchmark",
        "context_assembly_must_not_update_runtime",
    ]


def test_context_assembly_blocks_quarantined_skill_sources() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-001",
        sources=[
            *_sources(),
            {
                "source_id": "candidate-skill-from-external/SKILL.md",
                "kind": "skill",
                "estimated_tokens": 10,
                "metadata": {"skill_tier": "candidate_inbox"},
            },
        ],
        token_budget=800,
    )

    assert payload["status"] == "RETURN"
    assert "quarantined_skill_context:candidate-skill-from-external/SKILL.md" in payload["blockers"]


def test_planner_bound_context_materializes_without_claiming_consumption() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-472-g1",
        attempt_id="attempt-1",
        sources=_sources(),
        token_budget=500,
        planner_decision_id="planner-decision-472",
        planner_plan_hash="c" * 64,
        selected_capability_ids=("prompt_compression", "repository_intelligence"),
        source_mode="DIRECT_SLICE",
        source_provenance_refs=(_source_ref(),),
        consumer_role="main_engineer",
        consumer_channel="online",
        worker_binding={
            "worker_id": "codex_luna",
            "provider": "codex",
            "model": "gpt-5.6-luna",
        },
    )

    assert payload["status"] == "PASS"
    assert payload["planner_binding_status"] == "BOUND"
    assert payload["selection_state"] == "SELECTED"
    assert payload["materialization_state"] == "MATERIALIZED"
    assert payload["selected_capability_ids"] == ["prompt_compression", "repository_intelligence"]
    assert payload["serialization_state"] == "NOT_BOUND"
    assert payload["physical_consumption_state"] == "NOT_PROVEN"
    assert payload["outcome_contribution_state"] == "NOT_PROVEN"
    assert payload["blockers"] == []


def test_selected_context_requires_complete_planner_binding() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-472-g1",
        sources=_sources(),
        token_budget=500,
        selected_capability_ids=("prompt_compression",),
    )

    assert payload["status"] == "RETURN"
    assert payload["planner_binding_status"] == "INCOMPLETE"
    assert payload["blockers"] == [
        "selected_context_missing_planner_decision_id",
        "selected_context_missing_planner_plan_hash",
    ]


def test_source_materialization_requires_bound_provenance() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-472-g1",
        sources=_sources(),
        token_budget=500,
        source_mode="REDUCED_CAPSULE",
    )

    assert payload["status"] == "RETURN"
    assert "source_mode_missing_provenance_refs" in payload["blockers"]

    no_source_with_ref = build_context_assembly_contract(
        task_id="ctx-472-g1",
        sources=_sources(),
        token_budget=500,
        source_mode="NO_SOURCE",
        source_provenance_refs=(_source_ref(),),
    )
    assert no_source_with_ref["status"] == "RETURN"
    assert "source_refs_with_no_source_mode" in no_source_with_ref["blockers"]


def test_context_package_hash_is_deterministic_and_detects_drift() -> None:
    kwargs = {
        "task_id": "ctx-472-g1",
        "attempt_id": "attempt-1",
        "sources": _sources(),
        "token_budget": 500,
        "planner_decision_id": "planner-decision-472",
        "planner_plan_hash": "c" * 64,
        "selected_capability_ids": ("repository_intelligence", "prompt_compression"),
        "source_mode": "DIRECT_SLICE",
        "source_provenance_refs": (_source_ref(),),
        "consumer_role": "main_engineer",
        "consumer_channel": "online",
    }
    first = build_context_assembly_contract(**kwargs)
    second = build_context_assembly_contract(**kwargs)

    assert first["package_hash"] == second["package_hash"]

    tampered = dict(first)
    tampered["consumer_channel"] = "worker_registry"
    assert "context_package_hash_mismatch" in validate_context_assembly_contract(tampered)


def test_selected_capability_ids_fail_closed_when_malformed() -> None:
    malformed_values: tuple[Any, ...] = ("prompt_compression", (None,), ("",))
    for malformed in malformed_values:
        with pytest.raises(ValueError, match="invalid_selected_capability_ids"):
            build_context_assembly_contract(
                task_id="ctx-472-g1",
                sources=_sources(),
                token_budget=500,
                selected_capability_ids=malformed,
            )

    payload = build_context_assembly_contract(
        task_id="ctx-472-g1",
        sources=_sources(),
        token_budget=500,
    )
    payload["selected_capability_ids"] = "prompt_compression"
    assert "invalid_selected_capability_ids" in validate_context_assembly_contract(payload)


def test_legacy_positional_schema_constructor_remains_compatible() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-legacy",
        sources=_sources(),
        token_budget=500,
    )
    legacy = ContextAssemblyContract(
        "ctx-legacy",
        payload["receipt"],
        "preserve_l0_l1_hard_budget",
        CONTEXT_ASSEMBLY_CONTRACT_SCHEMA,
    ).to_dict()

    assert legacy["schema"] == CONTEXT_ASSEMBLY_CONTRACT_SCHEMA
    assert legacy["attempt_id"] == ""
    assert legacy["status"] == "PASS"


def test_worker_binding_does_not_stringify_missing_identity() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-472-g1",
        sources=_sources(),
        token_budget=500,
        worker_binding={
            "worker_id": "worker-1",
            "provider": None,
            "model": "model-1",
        },
    )

    assert payload["status"] == "RETURN"
    assert "incomplete_worker_binding:provider" in payload["blockers"]
