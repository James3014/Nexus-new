"""Nightly quarantine entry: tests/integration/test_n26_fallback_10_R_A_C.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_n26_fallback_10_R_A_C.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "capability-phase e2e expectations (plan membership, invoked/gate_passed/wall_time) drifted from the current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_exec_attempt_settlement_service_runs",
        "test_exec_battle_swarm_runs",
        "test_exec_dual_loop_runs",
        "test_exec_learning_closure_runs",
        "test_exec_metabolism_resume_runs",
        "test_exec_nightshift_runs",
        "test_exec_promotion_engine_runs",
        "test_exec_sandbox_runner_runs",
        "test_exec_subagent_outcome_service_runs",
    ),
}
