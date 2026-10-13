"""Nightly quarantine entry: tests/benchmark/test_local_model_executor_two_task_armor_smoke.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/benchmark/test_local_model_executor_two_task_armor_smoke.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_finalize_with_nexus_row_capability_execution_smoke",
        "test_two_task_local_model_armor_smoke_locked_search_and_ast_boundary",
    ),
}
