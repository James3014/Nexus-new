from __future__ import annotations

from nexus.contracts.context_assembly import (
    CONTEXT_ASSEMBLY_CONTRACT_SCHEMA,
    build_context_assembly_contract,
    compute_context_assembly_package_hash,
    validate_context_assembly_contract,
)


def _sources():
    return [
        {"source_id": "L0:rules", "kind": "L0", "estimated_tokens": 100},
        {"source_id": "L1:index", "kind": "L1", "estimated_tokens": 100},
        {"source_id": "history", "kind": "history", "estimated_tokens": 300, "priority": 20},
        {"source_id": "retrieval", "kind": "retrieval", "estimated_tokens": 250, "priority": 10},
    ]


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
    assert payload["package_hash"] == compute_context_assembly_package_hash(payload)


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


def test_context_assembly_binds_planner_lineage_and_direct_slice_without_selecting() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-472",
        attempt_id="attempt-1",
        sources=_sources(),
        token_budget=800,
        planner_decision_id="planner-decision-1",
        plan_hash="plan-sha256",
        selected_capabilities=["code_intelligence", "prompt_compression"],
        materialized_evidence_ids=["ev-2", "ev-1"],
        serialized_evidence_ids=["ev-1"],
        source_materialization={
            "mode": "DIRECT_SLICE",
            "repository": "James3014/Nexus-new",
            "revision": "deadbeef",
            "path": "nexus/services/example.py",
            "ranges": [[10, 30]],
            "content_hash": "slice-hash",
        },
        consumer_role="online_primary",
        consumer_channel="online_prompt",
    )

    assert payload["status"] == "PASS"
    assert payload["selected_capabilities"] == ["code_intelligence", "prompt_compression"]
    assert payload["materialized_evidence_ids"] == ["ev-1", "ev-2"]
    assert payload["serialized_evidence_ids"] == ["ev-1"]
    assert payload["source_materialization"]["mode"] == "DIRECT_SLICE"
    assert payload["package_hash"] == compute_context_assembly_package_hash(payload)


def test_context_assembly_hash_is_deterministic_across_identity_input_order() -> None:
    common = dict(
        task_id="ctx-472",
        sources=_sources(),
        token_budget=800,
        planner_decision_id="planner-decision-1",
        plan_hash="plan-sha256",
    )
    first = build_context_assembly_contract(
        **common,
        selected_capabilities=["b", "a"],
        materialized_evidence_ids=["ev-2", "ev-1"],
        serialized_evidence_ids=["ev-2", "ev-1"],
    )
    second = build_context_assembly_contract(
        **common,
        selected_capabilities=["a", "b"],
        materialized_evidence_ids=["ev-1", "ev-2"],
        serialized_evidence_ids=["ev-1", "ev-2"],
    )

    assert first["package_hash"] == second["package_hash"]


def test_context_assembly_fails_closed_on_serialized_materialization_substitution() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-472",
        sources=_sources(),
        token_budget=800,
        materialized_evidence_ids=["ev-1"],
        serialized_evidence_ids=["ev-2"],
    )

    assert payload["status"] == "RETURN"
    assert "serialized_evidence_not_materialized" in payload["blockers"]


def test_context_assembly_fails_closed_on_invalid_source_materialization() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-472",
        sources=_sources(),
        token_budget=800,
        source_materialization={
            "mode": "REDUCED_CAPSULE",
            "revision": "deadbeef",
            "path": "nexus/services/example.py",
        },
    )

    assert payload["status"] == "RETURN"
    assert "reduced_capsule_missing_uncertainties" in payload["blockers"]


def test_context_assembly_cannot_self_attest_consumption_or_contribution() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-472",
        sources=_sources(),
        token_budget=800,
    )
    payload["physically_consumed"] = True
    payload["outcome_contributed"] = True

    assert validate_context_assembly_contract(payload) == [
        "context_assembly_must_not_self_attest_outcome_contribution",
        "context_assembly_must_not_self_attest_physical_consumption",
    ]
