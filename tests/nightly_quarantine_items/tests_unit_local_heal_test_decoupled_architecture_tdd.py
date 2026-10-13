"""Nightly quarantine entry: tests/unit/local_heal/test_decoupled_architecture_tdd.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_decoupled_architecture_tdd.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_behavior_collapse_guard_during_retry",
        "test_cross_file_search_fallback",
        "test_localization_phase_execute_injects_target_file_hint",
        "test_patch_protocol_guard_during_retry",
        "test_planning_phase_execute_prioritizes_route_context_target_symbol",
        "test_planning_phase_stateless_run",
    ),
}
