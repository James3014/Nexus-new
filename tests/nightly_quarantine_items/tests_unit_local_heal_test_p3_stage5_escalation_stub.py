"""Nightly quarantine entry: tests/unit/local_heal/test_p3_stage5_escalation_stub.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_p3_stage5_escalation_stub.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": ("test_executor_includes_stage5_in_flow",),
}
