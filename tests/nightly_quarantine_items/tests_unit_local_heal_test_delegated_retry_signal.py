"""Nightly quarantine entry: tests/unit/local_heal/test_delegated_retry_signal.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_delegated_retry_signal.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_capability_planner_injects_committee_model_specs",
        "test_capability_planner_injects_delegated_retry_candidates",
    ),
}
