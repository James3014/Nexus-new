"""Nightly quarantine entry: tests/research/test_local_assist_paired_experiment.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/research/test_local_assist_paired_experiment.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "harness gap: run_arm_injected builds arm B without a Workforce admission (planner workforce_demands + policy loader), so UnifiedRuntime blocks the local call with workforce_admission_demands_malformed",
    "tests": ("test_paired_arms_share_identity_and_separate_policies",),
}
