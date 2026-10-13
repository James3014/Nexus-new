"""Nightly quarantine entry: tests/nexus/orchestrator/test_workflow_repair.py (#1928). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/nexus/orchestrator/test_workflow_repair.py",
    "disposition": "quarantine",
    "issue": "#1928",
    "cause": "fails in isolation too: integrate_approved now requires persisted external acceptance, integration authorization, a consumed one-shot grant and contract identity (a1b77a658+); the minimal synthetic state predates that and the function is in flight in #1884",
    "tests": (
        "test_integrate_approved_accepts_integration_branch_keyword",
        "test_integrate_approved_is_idempotent_after_integration",
        "test_integration_failure_records_failed_without_merge",
    ),
}
