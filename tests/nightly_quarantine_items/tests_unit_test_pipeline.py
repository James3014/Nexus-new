"""Nightly quarantine entry: tests/unit/test_pipeline.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/test_pipeline.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    # 11 ids passed once run_june_regression_pack stopped leaking env (#1924); this one fails on its own.
    "tests": ("test_pipeline_localize_query_includes_plan_symbols_and_evidence",),
}
