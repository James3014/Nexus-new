"""Nightly quarantine entry: tests/nexus/orchestrator/test_workflow_repair.py (#1928). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/nexus/orchestrator/test_workflow_repair.py",
    "disposition": "quarantine",
    "issue": "#1928",
    "cause": "passes in isolation on macOS at current main but fails in the Linux full-suite run (order-dependent state pollution or Linux-only environment difference); needs bisect",
    "tests": (
        "test_closeout_salvage_failure_preserves_retained_target_and_error",
        "test_failed_dirty_worker_auto_invokes_salvage_and_cleanup",
        "test_integrate_approved_accepts_integration_branch_keyword",
        "test_integrate_approved_is_idempotent_after_integration",
        "test_integration_failure_records_failed_without_merge",
        "test_timeout_dirty_worker_auto_invokes_salvage_and_cleanup",
    ),
}
