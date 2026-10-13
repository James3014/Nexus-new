"""Nightly quarantine entry: tests/test_skill_memory.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/test_skill_memory.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": ("test_query_failure_patterns",),
}
