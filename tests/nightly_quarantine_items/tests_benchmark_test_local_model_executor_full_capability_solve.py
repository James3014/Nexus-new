"""Nightly quarantine entry: tests/benchmark/test_local_model_executor_full_capability_solve.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/benchmark/test_local_model_executor_full_capability_solve.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": ("test_deterministic_full_capability_solve",),
}
