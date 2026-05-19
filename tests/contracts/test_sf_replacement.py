from __future__ import annotations

from nexus.contracts.optimization_report import ProviderTokenCleanliness
from nexus.contracts.sf_replacement import (
    SF_REPLACEMENT_CLEANLINESS_GATE_SCHEMA,
    build_sf_replacement_cleanliness_gate,
    build_sf_replacement_cleanliness_manifest,
)


def _clean_row(**overrides):
    row = {
        "capability": "repair_loop",
        "current_skill": "tdd",
        "challenger_skill": "sf-systematic-repair_loop-odoo-automated-tests-dad98433",
        "status": "PASS",
        "current_runtime_receipt_chain_ok": True,
        "challenger_runtime_receipt_chain_ok": True,
        "challenger_effective": True,
        "same_provider_cleanliness_window": True,
        "current_provider_token_cleanliness": ProviderTokenCleanliness.MEASURED.value,
        "challenger_provider_token_cleanliness": ProviderTokenCleanliness.MEASURED.value,
        "token_delta": -100,
        "wall_delta_sec": -5.5,
    }
    row.update(overrides)
    return row


def test_replacement_gate_approves_clean_better_challenger() -> None:
    decision = build_sf_replacement_cleanliness_gate(_clean_row())

    assert decision["schema"] == SF_REPLACEMENT_CLEANLINESS_GATE_SCHEMA
    assert decision["decision"] == "REPLACE"
    assert decision["runtime_update_allowed"] is True
    assert decision["public_benchmark_allowed"] is False
    assert decision["blockers"] == []


def test_replacement_gate_keeps_current_when_cost_tradeoff_is_not_better() -> None:
    decision = build_sf_replacement_cleanliness_gate(_clean_row(token_delta=-100, wall_delta_sec=3.2))

    assert decision["decision"] == "NO_REPLACEMENT"
    assert decision["reason"] == "challenger_not_better_on_both_token_and_wall"
    assert decision["runtime_update_allowed"] is False
    assert decision["blockers"] == []


def test_replacement_gate_blocks_when_cost_truth_is_missing() -> None:
    decision = build_sf_replacement_cleanliness_gate(
        _clean_row(challenger_provider_token_cleanliness=ProviderTokenCleanliness.MISSING.value)
    )

    assert decision["decision"] == "HOLD"
    assert decision["reason"] == "blocked_by_missing_cost_truth"
    assert "blocked_by_missing_cost_truth:challenger" in decision["blockers"]


def test_replacement_gate_blocks_cross_window_comparison() -> None:
    decision = build_sf_replacement_cleanliness_gate(_clean_row(same_provider_cleanliness_window=False))

    assert decision["decision"] == "HOLD"
    assert decision["reason"] == "blocked_by_cleanliness_window"
    assert "blocked_by_cleanliness_window" in decision["blockers"]


def test_replacement_gate_requires_runtime_receipt() -> None:
    decision = build_sf_replacement_cleanliness_gate(_clean_row(challenger_runtime_receipt_chain_ok=False))

    assert decision["decision"] == "HOLD"
    assert decision["reason"] == "challenger_runtime_receipt_incomplete"
    assert "challenger_runtime_receipt_incomplete" in decision["blockers"]


def test_replacement_manifest_counts_decisions() -> None:
    manifest = build_sf_replacement_cleanliness_manifest(
        [
            _clean_row(capability="repair_loop"),
            _clean_row(capability="forecast_pregate", wall_delta_sec=3.2),
            _clean_row(capability="research", challenger_provider_token_cleanliness=ProviderTokenCleanliness.ESTIMATED.value),
        ]
    )

    assert manifest["status"] == "RETURN"
    assert manifest["summary"]["replace_count"] == 1
    assert manifest["summary"]["no_replacement_count"] == 1
    assert manifest["summary"]["hold_count"] == 1
    assert manifest["summary"]["runtime_update_allowed"] is False
    assert manifest["summary"]["public_benchmark_allowed"] is False
