"""Nightly quarantine entry: tests/integration/test_abc_local_heal_full_isolated_solve_seam.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_abc_local_heal_full_isolated_solve_seam.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "needs planner-owned isolated_solve grant (nexus-runtime) and ISOLATED_TARGET admission (#1886)",
    "tests": (
        "test_abc_local_heal_full_isolated_solve_seam",
        "test_abc_local_heal_full_isolated_solve_with_fail_closed_guard_enabled",
    ),
}
