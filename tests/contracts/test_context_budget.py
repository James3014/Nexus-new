from __future__ import annotations

import pytest

from nexus.contracts.context_budget import (
    CONTEXT_BUDGET_RECEIPT_SCHEMA,
    ContextBudgetSource,
    build_context_budget_receipt,
    validate_context_budget_receipt,
)


def test_context_budget_preserves_l0_l1_and_keeps_priority_sources() -> None:
    receipt = build_context_budget_receipt(
        [
            ContextBudgetSource("l0-rules", "L0", 100),
            ContextBudgetSource("l1-index", "L1", 120),
            ContextBudgetSource("history", "history", 400, priority=20),
            ContextBudgetSource("research", "research", 600, priority=10),
        ],
        token_budget=850,
    )

    payload = receipt.to_dict()
    assert payload["status"] == "PASS"
    assert payload["preserved_L0_L1"] is True
    assert [source["source_id"] for source in payload["kept_sources"]] == [
        "l0-rules",
        "l1-index",
        "research",
    ]
    assert payload["dropped_sources"] == [
        {
            "source_id": "history",
            "kind": "history",
            "estimated_tokens": 400,
            "drop_reason_code": "budget_exhausted",
        }
    ]


def test_context_budget_returns_when_required_context_exceeds_budget() -> None:
    receipt = build_context_budget_receipt(
        [
            {"source_id": "l0-rules", "kind": "L0", "estimated_tokens": 300},
            {"source_id": "l1-index", "kind": "L1", "estimated_tokens": 300},
            {"source_id": "history", "kind": "history", "estimated_tokens": 100},
        ],
        token_budget=500,
    )

    payload = receipt.to_dict()
    assert payload["status"] == "RETURN"
    assert payload["blockers"] == ["required_context_over_budget"]
    assert payload["dropped_sources"][0]["drop_reason_code"] == "budget_not_evaluated_due_to_blocker"


def test_context_budget_requires_l0_and_l1() -> None:
    receipt = build_context_budget_receipt(
        [ContextBudgetSource("l0-rules", "L0", 100)],
        token_budget=500,
    )

    payload = receipt.to_dict()
    assert payload["status"] == "RETURN"
    assert payload["preserved_L0_L1"] is False
    assert "missing_required_l0_l1" in payload["blockers"]


def test_context_budget_validates_receipt_payload() -> None:
    payload = build_context_budget_receipt(
        [
            ContextBudgetSource("l0-rules", "L0", 100),
            ContextBudgetSource("l1-index", "L1", 100),
        ],
        token_budget=300,
    ).to_dict()

    assert validate_context_budget_receipt(payload) == []
    payload["estimated_tokens"] = 400
    assert validate_context_budget_receipt(payload) == ["estimated_tokens_exceed_budget"]


def test_context_budget_invalid_source_is_fail_closed() -> None:
    with pytest.raises(ValueError, match="missing_source_id"):
        ContextBudgetSource("", "history", 10)
    with pytest.raises(ValueError, match="negative_estimated_tokens"):
        ContextBudgetSource("history", "history", -1)


def test_context_budget_schema_is_stable() -> None:
    receipt = build_context_budget_receipt(
        [
            ContextBudgetSource("l0-rules", "L0", 1),
            ContextBudgetSource("l1-index", "L1", 1),
        ],
        token_budget=10,
    )

    assert receipt.to_dict()["schema"] == CONTEXT_BUDGET_RECEIPT_SCHEMA
