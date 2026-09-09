from __future__ import annotations

from copy import deepcopy

from nexus.contracts.context_assembly import (
    CONTEXT_ASSEMBLY_CONTRACT_SCHEMA,
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
    assert payload["source_mode"] == "NO_SOURCE"
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


def test_context_assembly_materializes_planner_lineage_without_claiming_consumption() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-002",
        attempt_id="attempt-7",
        sources=_sources(),
        token_budget=500,
        planner_decision_id="decision-123",
        planner_plan_id="plan-456",
        selected_capability_ids=("cap:retrieval", "cap:local_evidence"),
        materialized_context_ids=("evidence:packet-1",),
        serialized_context_ids=("evidence:packet-1",),
        source_mode="DIRECT_SLICE",
        source_references=(
            {
                "repository": "James3014/Nexus-new",
                "revision": "a" * 40,
                "path": "nexus/services/example.py",
                "ranges": [[10, 30]],
                "content_hash": "b" * 64,
                "claim_ceiling": "SOURCE_BOUNDED_ONLY",
            },
        ),
        consumer_role="primary_implementer",
        consumer_channel="online",
        worker_binding={
            "worker_id": "worker-1",
            "provider": "agy",
            "model": "gemini-3.7-flash-medium",
        },
    )

    assert payload["status"] == "PASS"
    assert payload["planner_decision_id"] == "decision-123"
    assert payload["planner_plan_id"] == "plan-456"
    assert payload["source_mode"] == "DIRECT_SLICE"
    assert payload["selected_capability_ids"] == ["cap:retrieval", "cap:local_evidence"]
    assert payload["materialized_context_ids"] == ["evidence:packet-1"]
    assert payload["serialized_context_ids"] == ["evidence:packet-1"]
    assert payload["source_references"][0]["claim_ceiling"] == "SOURCE_BOUNDED_ONLY"
    assert payload["worker_binding"]["model"] == "gemini-3.7-flash-medium"
    assert "physically_consumed" not in payload
    assert "outcome_contributed" not in payload
    assert payload["blockers"] == []


def test_context_assembly_package_hash_is_deterministic_and_detects_tamper() -> None:
    kwargs = dict(
        task_id="ctx-003",
        sources=_sources(),
        token_budget=500,
        planner_decision_id="decision-123",
        selected_capability_ids=("cap:a",),
        materialized_context_ids=("evidence:1",),
        serialized_context_ids=("evidence:1",),
        consumer_channel="worker",
    )
    first = build_context_assembly_contract(**kwargs)
    second = build_context_assembly_contract(**kwargs)

    assert first["package_hash"] == second["package_hash"]

    tampered = deepcopy(first)
    tampered["serialized_context_ids"] = ["evidence:substituted"]
    assert "context_package_hash_mismatch" in validate_context_assembly_contract(tampered)


def test_context_assembly_source_mode_fails_closed_on_missing_or_unexpected_reference() -> None:
    missing_reference = build_context_assembly_contract(
        task_id="ctx-004",
        sources=_sources(),
        token_budget=500,
        source_mode="REDUCED_CAPSULE",
    )
    assert missing_reference["status"] == "RETURN"
    assert "source_materialization_requires_source_reference" in missing_reference["blockers"]

    no_source_with_reference = build_context_assembly_contract(
        task_id="ctx-005",
        sources=_sources(),
        token_budget=500,
        source_mode="NO_SOURCE",
        source_references=({"path": "should-not-be-here.py", "claim_ceiling": "UNVERIFIED"},),
    )
    assert no_source_with_reference["status"] == "RETURN"
    assert "no_source_mode_must_not_carry_source_references" in no_source_with_reference["blockers"]


def test_context_assembly_rejects_duplicate_lineage_identities() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-006",
        sources=_sources(),
        token_budget=500,
        selected_capability_ids=("cap:a", "cap:a"),
    )

    assert payload["status"] == "RETURN"
    assert "duplicate_selected_capability_ids" in payload["blockers"]


def test_context_assembly_source_reference_requires_bounded_identity_and_claim_ceiling() -> None:
    payload = build_context_assembly_contract(
        task_id="ctx-007",
        sources=_sources(),
        token_budget=500,
        source_mode="DIRECT_SLICE",
        source_references=(
            {
                "path": "nexus/services/example.py",
                "revision": "not-a-sha",
                "ranges": [[0, 5]],
                "content_hash": "not-a-hash",
            },
        ),
    )

    assert payload["status"] == "RETURN"
    assert "source_reference[0]:missing_claim_ceiling" in payload["blockers"]
    assert "source_reference[0]:invalid_revision" in payload["blockers"]
    assert "source_reference[0]:invalid_content_hash" in payload["blockers"]
    assert "source_reference[0]:invalid_range" in payload["blockers"]
