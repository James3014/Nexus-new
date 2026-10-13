"""Nightly quarantine entry: tests/integration/test_a_c_phases_9_capabilities_e2e.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_a_c_phases_9_capabilities_e2e.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "capability-phase e2e expectations (plan membership, invoked/gate_passed/wall_time) drifted from the current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_a_c_9_capabilities_disable_each_breaks_task[artifact_gate-NEXUS_SKIP_ARTIFACT_GATE]",
        "test_a_c_9_capabilities_disable_each_breaks_task[claim_gate-NEXUS_SKIP_CLAIM_GATE]",
        "test_a_c_9_capabilities_disable_each_breaks_task[ultra_review-NEXUS_SKIP_ULTRA_REVIEW]",
        "test_a_c_9_capabilities_invoked_in_real_task",
    ),
}
