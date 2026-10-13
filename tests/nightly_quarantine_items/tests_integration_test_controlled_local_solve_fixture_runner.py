"""Nightly quarantine entry: tests/integration/test_controlled_local_solve_fixture_runner.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_controlled_local_solve_fixture_runner.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "needs planner-owned isolated_solve grant (nexus-runtime) and ISOLATED_TARGET admission (#1886)",
    "tests": (
        "test_fixture_diff_normalization_success",
        "test_fixture_function_return_replacement",
        "test_fixture_outside_locked_span_blocked",
        "test_fixture_single_line_replacement",
        "test_fixture_verifier_fail_blocked",
    ),
}
