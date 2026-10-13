"""Nightly quarantine entry: tests/unit/local_heal/test_localheal_pipeline_seam_truth.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_localheal_pipeline_seam_truth.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "TestPipelineResultProjectionB3::test_pipeline_result_non_empty_final_patch_projects_candidate_hash",
        "TestPipelineResultProjectionB3::test_pipeline_verification_failure_uses_preserved_pre_verification_patch",
    ),
}
