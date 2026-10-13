"""Nightly quarantine entry: tests/app/test_research_flow_service.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/app/test_research_flow_service.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "capability-phase e2e expectations (plan membership, invoked/gate_passed/wall_time) drifted from the current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_auto_flow_writes_semantic_research_runtime_receipts",
        "test_run_auto_flow_populates_autoreason_from_candidate_summaries",
    ),
}
