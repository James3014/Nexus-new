"""Nightly quarantine entry: tests/integration/test_unified_runtime_replan_subprocess.py (#1923). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_unified_runtime_replan_subprocess.py",
    "disposition": "quarantine-product-bug?",
    "issue": "#1923",
    "cause": "assertion encodes a safety/boundary invariant that the product currently violates; possible real product bug, file a new Issue before fixing",
    "tests": (
        "test_physical_subprocess_attempt_one_bytes_remain_unchanged",
        "test_physical_subprocess_invoked_exactly_twice",
        "test_physical_subprocess_light_to_standard_replan_lifecycle",
        "test_physical_subprocess_receipt_does_not_claim_live_model_provider",
        "test_physical_subprocess_receipts_form_strict_valid_lineage",
        "test_physical_subprocess_second_failure_stops_without_third_attempt",
        "test_physical_subprocess_second_verifier_failure_stops_without_third_attempt",
        "test_physical_subprocess_tampered_prior_receipt_blocks_before_second_process",
    ),
}
