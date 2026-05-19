from __future__ import annotations

from nexus.contracts.route_context_seam_freeze import (
    ROUTE_CONTEXT_SEAM_FREEZE_SCHEMA,
    build_route_context_seam_freeze,
    validate_route_context_seam_freeze,
)


def test_route_context_seam_freeze_passes_when_boundaries_are_clean() -> None:
    payload = build_route_context_seam_freeze(
        route_manifest_ref="docs/reports/route_dag_pregate.json",
        context_receipt_ref="docs/reports/context_budget.json",
        runtime_dispatch_changed=False,
        preserved_l0_l1=True,
        claim_read_model_status="PASS",
        allowed_next_work=("context_budget_refactor", "retrieval_receipt_integration"),
    )

    assert payload["schema"] == ROUTE_CONTEXT_SEAM_FREEZE_SCHEMA
    assert payload["status"] == "PASS"
    assert payload["blockers"] == []
    assert "context_budget_refactor" in payload["allowed_next_work"]


def test_route_context_seam_freeze_blocks_runtime_dispatch_or_context_drift() -> None:
    payload = build_route_context_seam_freeze(
        route_manifest_ref="docs/reports/route_dag_pregate.json",
        context_receipt_ref="docs/reports/context_budget.json",
        runtime_dispatch_changed=True,
        preserved_l0_l1=False,
        claim_read_model_status="RETURN",
    )

    assert payload["status"] == "RETURN"
    assert payload["blockers"] == [
        "claim_read_model_not_pass",
        "context_l0_l1_not_preserved",
        "runtime_dispatch_changed",
    ]


def test_route_context_seam_freeze_validator_rejects_unlock_attempts() -> None:
    blockers = validate_route_context_seam_freeze(
        {
            "route_manifest_ref": "docs/reports/route_dag_pregate.json",
            "context_receipt_ref": "docs/reports/context_budget.json",
            "runtime_dispatch_changed": False,
            "preserved_l0_l1": True,
            "claim_read_model_status": "PASS",
            "runtime_update_allowed": True,
            "public_benchmark_allowed": True,
        }
    )

    assert blockers == [
        "freeze_contract_must_not_unlock_public_benchmark",
        "freeze_contract_must_not_update_runtime",
    ]
