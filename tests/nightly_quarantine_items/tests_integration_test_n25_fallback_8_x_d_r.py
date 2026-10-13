"""Nightly quarantine entry: tests/integration/test_n25_fallback_8_X_D_R.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_n25_fallback_8_X_D_R.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "capability-phase e2e expectations (plan membership, invoked/gate_passed/wall_time) drifted from the current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_exec_autoreason_runs",
        "test_exec_belief_runs",
        "test_exec_drone_runs",
        "test_exec_hyper_sprint_runs",
        "test_exec_learn_refresh_service_runs",
        "test_exec_learn_scheduler_service_runs",
        "test_exec_repair_loop_runs",
        "test_exec_swarm_multi_agent_runs",
    ),
}
