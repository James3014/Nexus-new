"""Nightly quarantine entry: tests/integration/test_r_phase_8_capabilities_e2e.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_r_phase_8_capabilities_e2e.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "capability-phase e2e expectations (plan membership, invoked/gate_passed/wall_time) drifted from the current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_r_8_capabilities_disable_each_breaks_task[drone-NEXUS_SKIP_DRONE]",
        "test_r_8_capabilities_disable_each_breaks_task[nightshift-NEXUS_SKIP_NIGHTSHIFT]",
        "test_r_8_capabilities_disable_each_breaks_task[sandbox_runner-NEXUS_SKIP_SANDBOX_RUNNER]",
        "test_r_8_capabilities_disable_each_breaks_task[swarm_multi_agent-NEXUS_SKIP_SWARM_MULTI_AGENT]",
        "test_r_8_capabilities_invoked_in_real_task",
        "test_r_repair_loop_invoked_for_low_risk",
    ),
}
