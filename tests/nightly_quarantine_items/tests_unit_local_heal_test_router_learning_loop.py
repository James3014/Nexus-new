"""Nightly quarantine entry: tests/unit/local_heal/test_router_learning_loop.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_router_learning_loop.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_router_empty_receipts_are_unverified_not_success",
        "test_router_existing_learning_closure_unchanged",
        "test_router_outcome_memory_disabled_with_env",
        "test_router_outcome_memory_episode_data_correct",
        "test_router_outcome_memory_failure_does_not_block",
        "test_router_writes_outcome_memory_after_routing",
    ),
}
