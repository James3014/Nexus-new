"""Nightly quarantine entry: tests/unit/test_pipeline_trace.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/test_pipeline_trace.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_pipeline_trace_has_start_and_end",
        "test_pipeline_trace_written_on_localize_failure",
    ),
}
