"""Nightly quarantine entry: tests/integration/test_s_phase_5_capabilities_e2e.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_s_phase_5_capabilities_e2e.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "capability-phase e2e expectations (plan membership, invoked/gate_passed/wall_time) drifted from the current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_s_5_capabilities_disable_each_breaks_task[mempalace-NEXUS_SKIP_MEMPALACE]",
        "test_s_5_capabilities_disable_each_breaks_task[nightshift_runner_service-NEXUS_SKIP_NIGHTSHIFT_RUNNER_SERVICE]",
        "test_s_5_capabilities_invoked_in_real_task",
    ),
}
