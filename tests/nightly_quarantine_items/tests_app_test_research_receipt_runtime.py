"""Nightly quarantine entry: tests/app/test_research_receipt_runtime.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/app/test_research_receipt_runtime.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "capability-phase e2e expectations (plan membership, invoked/gate_passed/wall_time) drifted from the current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_build_capability_receipt_payloads_marks_runtime_autoreason_safe",
        "test_build_capability_receipt_payloads_preserves_runtime_repair_loop_receipt",
        "test_hyper_runtime_usage_backfill_is_marked_as_supporting_flow",
    ),
}
