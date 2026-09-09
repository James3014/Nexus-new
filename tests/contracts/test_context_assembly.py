from __future__ import annotations

from copy import deepcopy

from nexus.contracts.context_assembly import (
    CONTEXT_ASSEMBLY_CONTRACT_SCHEMA,
    build_context_assembly_contract,
    validate_context_assembly_contract,
)
from nexus.contracts.source_materialization import (
    DIRECT_SLICE,
    build_source_materialization_projection,
)


def _sources():
    return [
        {"source_id": "L0:rules", "kind": "L0", "estimated_tokens": 100},
        {"source_id": "L1:index", "kind": "L1", "estimated_tokens": 100},
        {"source_id": "history", "kind": "history", "estimated_tokens": 300, "priority": 20},
        {"source_id": "retrieval", "kind": "retrieval", "estimated_tokens": 250, "priority": 10},
    ]


def _source_materialization():
    return build_source_materialization_projection(
        strategy=DIRECT_SLICE,
        repository="James3014/Nexus-new",
        revision="deadbeef",
        tree="cafebabe",
        source_hash="sha256:source-root",
        selected_sources=[
            {
                "path": "nexus/services/online_nexus_context.py",
                "symbol": "build_online_nexus_context",
                "ranges": [[430, 510]],
                "content_hash": "sha256:source-content",
            }
        ],
    )


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
    assert payload["blockers"] == []
    assert payload["package_hash"]


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
        "context_assembly_package_hash_mismatch",
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


def test_context_assembly_binds_planner_source_and_serialized_lineage() -> None:
    source_materialization = _source_materialization()
    payload = build_context_assembly_contract(
        task_id="ctx-472",
        sources=_sources(),
        token_budget=500,
        planner_decision_id="planner-decision-001",
        plan_hash="sha256:plan",
        selected_capabilities=["codeintel", "memory", "codeintel"],
        serialized_evidence_ids=["evidence:codeintel:1", "evidence:memory:1"],
        source_materialization=source_materialization,
        consumer={"role": "online", "channel": "online"},
    )

    assert payload["status"] == "PASS"
    assert payload["planner_decision_id"] == "planner-decision-001"
    assert payload["plan_hash"] == "sha256:plan"
    assert payload["selected_capabilities"] == ["codeintel", "memory"]
    assert payload["serialized_evidence_ids"] == [
        "evidence:codeintel:1",
        "evidence:memory:1",
    ]
    assert (
        payload["source_materialization"]["materialization_hash"]
        == source_materialization["materialization_hash"]
    )
    assert payload["materialized_source_count"] == 1
    assert payload["serialized_evidence_count"] == 2
    assert payload["package_hash"]
    assert "physically_consumed" not in payload
    assert "outcome_contributed" not in payload


def test_model_context_lineage_requires_planner_identity() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-472",
        sources=_sources(),
        token_budget=500,
        selected_capabilities=["codeintel"],
        source_materialization=_source_materialization(),
    )

    assert payload["status"] == "RETURN"
    assert "missing_planner_decision_id" in payload["blockers"]
    assert "missing_plan_hash" in payload["blockers"]


def test_context_assembly_rejects_nested_source_tamper_and_consumption_claims() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-472",
        sources=_sources(),
        token_budget=500,
        planner_decision_id="planner-decision-001",
        plan_hash="sha256:plan",
        source_materialization=_source_materialization(),
    )
    tampered = deepcopy(payload)
    tampered["source_materialization"]["selected_sources"][0]["content_hash"] = (
        "sha256:substituted"
    )
    tampered["physically_consumed"] = True
    tampered["outcome_contributed"] = True

    blockers = validate_context_assembly_contract(tampered)
    assert "source_materialization:source_materialization_hash_mismatch" in blockers
    assert "context_assembly_package_hash_mismatch" in blockers
    assert "context_assembly_must_not_claim_physical_consumption" in blockers
    assert "context_assembly_must_not_claim_outcome_contribution" in blockers
