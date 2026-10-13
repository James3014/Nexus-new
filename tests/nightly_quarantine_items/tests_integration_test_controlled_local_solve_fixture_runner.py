"""Nightly quarantine entry: tests/integration/test_controlled_local_solve_fixture_runner.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_controlled_local_solve_fixture_runner.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_fixture_diff_normalization_success",
        "test_fixture_function_return_replacement",
        "test_fixture_missing_evidence_blocked",
        "test_fixture_outside_locked_span_blocked",
        "test_fixture_single_line_replacement",
        "test_fixture_verifier_fail_blocked",
    ),
}
