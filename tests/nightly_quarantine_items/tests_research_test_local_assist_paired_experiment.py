"""Nightly quarantine entry: tests/research/test_local_assist_paired_experiment.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/research/test_local_assist_paired_experiment.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "capability-phase e2e expectations (plan membership, invoked/gate_passed/wall_time) drifted from the current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": ("test_paired_arms_share_identity_and_separate_policies",),
}
