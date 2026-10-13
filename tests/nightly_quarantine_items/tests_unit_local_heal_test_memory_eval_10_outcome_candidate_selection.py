"""Nightly quarantine entry: tests/unit/local_heal/test_memory_eval_10_outcome_candidate_selection.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_memory_eval_10_outcome_candidate_selection.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "host-only probe: audits generated, gitignored artifacts/runtime evidence (real model call receipts, selected candidates, evidence bundles) that a clean runner lacks; faking them would defeat the audit",
    "tests": (
        "test_c12481_excluded_from_selected",
        "test_memory_availability_matrix_exists",
        "test_rejected_candidates_file_exists",
        "test_selected_candidate_count_matches",
        "test_selected_candidates_file_exists",
        "test_selected_candidates_have_evidence_paths",
        "test_selected_candidates_no_eval_stub_ids",
        "test_selection_criteria_exists",
        "test_validation_pool_size_positive",
        "test_validation_prohibits_uplift_public_product_training_claims",
        "test_validation_status_correct",
    ),
}
