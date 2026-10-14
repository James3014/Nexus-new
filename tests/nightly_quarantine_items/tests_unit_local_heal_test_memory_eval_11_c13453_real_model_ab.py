"""Nightly quarantine entry: tests/unit/local_heal/test_memory_eval_11_c13453_real_model_ab.py (#1926). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_memory_eval_11_c13453_real_model_ab.py",
    "disposition": "delete-candidate",
    "issue": "#1926",
    "cause": "host-only probe: audits cwd-relative, gitignored artifacts/runtime/memory_eval_11_c13453_real_model_ab_v0/ (validation.json, model_call_receipt.json, memory_impact_comparison.json, raw_model_output_memory_{on,off}.txt, runs/C_13453/nexus_memory_{on,off}/) from a real local-model A/B run; a clean runner lacks them and faking them would defeat the audit",
    "tests": (
        "test_both_arm_artifact_directories_exist",
        "test_comparison_file_aligns_with_artifacts",
        "test_memory_on_arm_retrieved_at_least_one_lesson",
        "test_model_call_receipt_exists_and_has_hashes",
        "test_per_arm_artifacts_complete",
        "test_prohibit_public_claim_and_training_export",
        "test_prompt_delta_observed",
        "test_raw_model_outputs_exist_and_nonempty",
        "test_raw_output_sha256_matches_receipt",
        "test_real_model_call_executed",
        "test_synthetic_delta_false",
        "test_validation_file_exists",
    ),
}
