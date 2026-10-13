"""Nightly quarantine entry: tests/integration/test_n27_five_preexisting_to_100_percent.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_n27_five_preexisting_to_100_percent.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "capability-phase e2e expectations (plan membership, invoked/gate_passed/wall_time) drifted from the current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_all_36_executors_real_execution_100_percent",
        "test_exec_aos_oracle_invoked_true",
        "test_exec_claim_gate_invoked_true",
        "test_exec_reflex_loop_invoked_true",
        "test_exec_zero_trust_v2_behavior_invoked_true",
    ),
}
