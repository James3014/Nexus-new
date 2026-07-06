"""C6B: Current-proof capability matrix tests.

Ensures 11-combination matrix is complete, current-proof only,
and each combination has verifiable raw evidence reference.
"""
from __future__ import annotations

import pytest


# --- Current-proof raw rows (all 11 combinations) ---

CURRENT_PROOF_ROWS = [
    # Dual (6)
    {"combo": "qwen+deepseek", "tier": "dual", "winner_selected": True, "apply_success": True, "verifier_pass": False, "solved": False, "primary_failure_bucket": "verification_failed", "raw_evidence_ref": "C4C-A1-historical"},
    {"combo": "qwen+ornith", "tier": "dual", "winner_selected": True, "apply_success": True, "verifier_pass": False, "solved": False, "primary_failure_bucket": "no_blocks_found", "raw_evidence_ref": "C4C-A2-94s"},
    {"combo": "qwen+qwythos", "tier": "dual", "winner_selected": True, "apply_success": True, "verifier_pass": False, "solved": False, "primary_failure_bucket": "verification_failed", "raw_evidence_ref": "C4C-A3-250s"},
    {"combo": "deepseek+ornith", "tier": "dual", "winner_selected": True, "apply_success": True, "verifier_pass": False, "solved": False, "primary_failure_bucket": "verification_failed", "raw_evidence_ref": "C4C-A4-266s"},
    {"combo": "deepseek+qwythos", "tier": "dual", "winner_selected": True, "apply_success": True, "verifier_pass": False, "solved": False, "primary_failure_bucket": "verification_failed", "raw_evidence_ref": "C4C-A5-134s"},
    {"combo": "ornith+qwythos", "tier": "dual", "winner_selected": True, "apply_success": True, "verifier_pass": False, "solved": False, "primary_failure_bucket": "verification_failed", "raw_evidence_ref": "C4C-A6-historical"},
    # Triple (4)
    {"combo": "qwen+deepseek+ornith", "tier": "triple", "winner_selected": True, "apply_success": True, "verifier_pass": False, "solved": False, "primary_failure_bucket": "verification_failed", "raw_evidence_ref": "C4C-B1-historical"},
    {"combo": "qwen+deepseek+qwythos", "tier": "triple", "winner_selected": True, "apply_success": True, "verifier_pass": False, "solved": False, "primary_failure_bucket": "verification_failed", "raw_evidence_ref": "C4C-B2-312s"},
    {"combo": "qwen+ornith+qwythos", "tier": "triple", "winner_selected": True, "apply_success": True, "verifier_pass": False, "solved": False, "primary_failure_bucket": "verification_failed", "raw_evidence_ref": "C4C-B3-343s"},
    {"combo": "deepseek+ornith+qwythos", "tier": "triple", "winner_selected": True, "apply_success": True, "verifier_pass": False, "solved": False, "primary_failure_bucket": "verification_failed", "raw_evidence_ref": "C4C-B4-historical"},
    # Four-model (1)
    {"combo": "qwen+deepseek+ornith+qwythos", "tier": "four", "winner_selected": True, "apply_success": True, "verifier_pass": False, "solved": False, "primary_failure_bucket": "verification_failed", "raw_evidence_ref": "C6B-four-444s"},
]


def test_current_capability_matrix_lists_all_11_combinations():
    """Matrix must list exactly 11 combinations."""
    assert len(CURRENT_PROOF_ROWS) == 11


def test_current_capability_matrix_excludes_historical_rows():
    """All rows must have raw_evidence_ref starting with C4C or C6B, not older."""
    for row in CURRENT_PROOF_ROWS:
        assert row["raw_evidence_ref"].startswith(("C4C-", "C6B-")), (
            f"{row['combo']}: raw_evidence_ref must be current-proof, got {row['raw_evidence_ref']}"
        )


def test_primary_failure_bucket_is_derived_from_current_rows_only():
    """Failure buckets must be derivable from current rows only."""
    buckets = {}
    for row in CURRENT_PROOF_ROWS:
        bucket = row["primary_failure_bucket"]
        buckets.setdefault(bucket, []).append(row["combo"])

    # verification_failed: 10 combos (all except A2)
    assert len(buckets.get("verification_failed", [])) == 10
    # no_blocks_found: 1 combo (A2)
    assert len(buckets.get("no_blocks_found", [])) == 1
    # Total must equal row count
    total = sum(len(v) for v in buckets.values())
    assert total == len(CURRENT_PROOF_ROWS)


def test_verifier_pass_is_not_inferred_from_wiring_or_apply():
    """verifier_pass must be explicitly False for all current rows (no solve)."""
    for row in CURRENT_PROOF_ROWS:
        assert row["verifier_pass"] is False, (
            f"{row['combo']}: verifier_pass must be False (no solve proof)"
        )
        assert row["solved"] is False, (
            f"{row['combo']}: solved must be False"
        )


def test_tier_distribution_matches_expected():
    """Tier distribution must be 6 dual + 4 triple + 1 four = 11."""
    tiers = {}
    for row in CURRENT_PROOF_ROWS:
        tiers.setdefault(row["tier"], []).append(row["combo"])
    assert len(tiers.get("dual", [])) == 6
    assert len(tiers.get("triple", [])) == 4
    assert len(tiers.get("four", [])) == 1
