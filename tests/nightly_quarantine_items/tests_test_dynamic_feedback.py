"""Nightly quarantine entry: tests/test_dynamic_feedback.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/test_dynamic_feedback.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": ("test_pipeline_injects_audit_failure_to_repairer",),
}
