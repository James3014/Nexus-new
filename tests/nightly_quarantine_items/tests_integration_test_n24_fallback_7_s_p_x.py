"""Nightly quarantine entry: tests/integration/test_n24_fallback_7_S_P_X.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_n24_fallback_7_S_P_X.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "capability-phase e2e expectations (plan membership, invoked/gate_passed/wall_time) drifted from the current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_exec_codeintel_runs",
        "test_exec_decision_formula_engine_runs",
        "test_exec_nightshift_runner_service_runs",
        "test_exec_policy_capability_gate_runs",
        "test_exec_research_runs",
    ),
}
