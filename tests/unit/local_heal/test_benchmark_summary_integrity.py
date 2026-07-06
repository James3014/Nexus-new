"""C6A: Benchmark summary integrity tests.

Ensures ability matrix counts are consistent with raw rows,
and wiring/telemetry/solve/historical evidence layers are clearly separated.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path


# --- Raw row fixtures representing C4C execution results ---

RAW_ROWS_CURRENT = [
    {"combination": "A2", "models": "qwen+ornith", "duration_sec": 94, "solved": False, "winner_selected": True, "apply_status": "applied", "verifier_result": "fail", "failure_class": "no_blocks_found", "source": "current"},
    {"combination": "A3", "models": "qwen+qwythos", "duration_sec": 250, "solved": False, "winner_selected": True, "apply_status": "applied", "verifier_result": "fail", "failure_class": "verification_failed", "source": "current"},
    {"combination": "A4", "models": "deepseek+ornith", "duration_sec": 266, "solved": False, "winner_selected": True, "apply_status": "applied", "verifier_result": "fail", "failure_class": "verification_failed", "source": "current"},
    {"combination": "A5", "models": "deepseek+qwythos", "duration_sec": 134, "solved": False, "winner_selected": True, "apply_status": "applied", "verifier_result": "fail", "failure_class": "verification_failed", "source": "current"},
    {"combination": "B2", "models": "qwen+deepseek+qwythos", "duration_sec": 312, "solved": False, "winner_selected": True, "apply_status": "applied", "verifier_result": "fail", "failure_class": "verification_failed", "source": "current"},
    {"combination": "B3", "models": "qwen+ornith+qwythos", "duration_sec": 343, "solved": False, "winner_selected": True, "apply_status": "applied", "verifier_result": "fail", "failure_class": "verification_failed", "source": "current"},
]

RAW_ROWS_HISTORICAL = [
    {"combination": "A1", "models": "qwen+deepseek", "duration_sec": None, "solved": False, "winner_selected": True, "apply_status": "applied", "verifier_result": "fail", "failure_class": "verification_failed", "source": "historical"},
    {"combination": "A6", "models": "ornith+qwythos", "duration_sec": None, "solved": False, "winner_selected": True, "apply_status": "applied", "verifier_result": "fail", "failure_class": "verification_failed", "source": "historical"},
    {"combination": "B1", "models": "qwen+deepseek+ornith", "duration_sec": None, "solved": False, "winner_selected": True, "apply_status": "applied", "verifier_result": "fail", "failure_class": "verification_failed", "source": "historical"},
    {"combination": "B4", "models": "deepseek+ornith+qwythos", "duration_sec": None, "solved": False, "winner_selected": True, "apply_status": "applied", "verifier_result": "fail", "failure_class": "verification_failed", "source": "historical"},
]

ALL_ROWS = RAW_ROWS_CURRENT + RAW_ROWS_HISTORICAL


def _compute_failure_taxonomy(rows: list[dict]) -> dict[str, list[str]]:
    """Compute failure taxonomy from raw rows."""
    taxonomy: dict[str, list[str]] = {}
    for row in rows:
        fc = row["failure_class"]
        taxonomy.setdefault(fc, []).append(row["combination"])
    return taxonomy


def _compute_evidence_layers(rows: list[dict]) -> dict[str, dict]:
    """Compute evidence layer counts from raw rows."""
    current = [r for r in rows if r["source"] == "current"]
    historical = [r for r in rows if r["source"] == "historical"]
    return {
        "wiring_current": len(current),
        "wiring_historical": len(historical),
        "wiring_total": len(rows),
        "solve_current": sum(1 for r in current if r["solved"]),
        "solve_historical": sum(1 for r in historical if r["solved"]),
        "solve_total": sum(1 for r in rows if r["solved"]),
        "winner_current": sum(1 for r in current if r["winner_selected"]),
        "winner_historical": sum(1 for r in historical if r["winner_selected"]),
        "apply_current": sum(1 for r in current if r["apply_status"] == "applied"),
        "apply_historical": sum(1 for r in historical if r["apply_status"] == "applied"),
        "verifier_fail_current": sum(1 for r in current if r["verifier_result"] == "fail"),
        "verifier_fail_historical": sum(1 for r in historical if r["verifier_result"] == "fail"),
    }


# --- Tests ---

def test_ability_matrix_counts_match_rows():
    """Grouped failure counts must be computable from raw rows."""
    taxonomy = _compute_failure_taxonomy(ALL_ROWS)

    # verification_failed: A1, A3, A4, A5, A6, B1, B2, B3, B4 = 9
    assert len(taxonomy.get("verification_failed", [])) == 9
    assert set(taxonomy["verification_failed"]) == {"A1", "A3", "A4", "A5", "A6", "B1", "B2", "B3", "B4"}

    # no_blocks_found: A2 = 1
    assert len(taxonomy.get("no_blocks_found", [])) == 1
    assert taxonomy["no_blocks_found"] == ["A2"]

    # Total must equal row count
    total_counted = sum(len(v) for v in taxonomy.values())
    assert total_counted == len(ALL_ROWS)


def test_current_proof_and_historical_reference_are_separated():
    """Current and historical rows must be explicitly separated in evidence layers."""
    layers = _compute_evidence_layers(ALL_ROWS)

    # Current: 6 rows (A2, A3, A4, A5, B2, B3)
    assert layers["wiring_current"] == 6
    # Historical: 4 rows (A1, A6, B1, B4)
    assert layers["wiring_historical"] == 4
    # Total: 10
    assert layers["wiring_total"] == 10

    # Current and historical must not be mixed in same count
    assert layers["wiring_current"] + layers["wiring_historical"] == layers["wiring_total"]


def test_apply_success_verifier_fail_classified_as_unsolved_not_wiring_failure():
    """apply_success + verifier_fail must be classified as unsolved, not wiring failure."""
    for row in ALL_ROWS:
        if row["apply_status"] == "applied" and row["verifier_result"] == "fail":
            # This is a model capability failure, not a wiring failure
            assert row["solved"] is False, f"{row['combination']}: apply+verifier_fail must be unsolved"
            # failure_class must be a semantic failure, not a wiring/connectivity failure
            wiring_failure_classes = ("wiring_broken", "route_missing", "topology_missing")
            assert row["failure_class"] not in wiring_failure_classes, (
                f"{row['combination']}: apply+verifier_fail should not be {row['failure_class']}"
            )


def test_empty_patch_and_search_mismatch_do_not_count_as_solved():
    """EMPTY_PATCH and SEARCH_MISMATCH must never count as solved."""
    for row in ALL_ROWS:
        if row["failure_class"] in ("EMPTY_PATCH", "SEARCH_MISMATCH", "no_blocks_found"):
            assert row["solved"] is False, (
                f"{row['combination']}: {row['failure_class']} must not be solved"
            )


def test_no_blocks_found_is_unique_to_a2():
    """no_blocks_found should only appear for A2 in current data."""
    current_no_blocks = [r for r in RAW_ROWS_CURRENT if r["failure_class"] == "no_blocks_found"]
    assert len(current_no_blocks) == 1
    assert current_no_blocks[0]["combination"] == "A2"
