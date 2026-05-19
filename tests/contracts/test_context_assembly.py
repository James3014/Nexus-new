from __future__ import annotations

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
