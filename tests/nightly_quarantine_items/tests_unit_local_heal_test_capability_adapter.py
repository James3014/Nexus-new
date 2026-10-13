"""Nightly quarantine entry: tests/unit/local_heal/test_capability_adapter.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_capability_adapter.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_capability_adapter_advisory_enabled_by_env",
        "test_capability_adapter_candidate_enabled_with_call",
        "test_capability_adapter_disabled",
        "test_capability_adapter_dry_run_default",
        "test_capability_adapter_fail_closed_guard_blocked",
        "test_capability_adapter_isolated_solve_missing_control",
        "test_capability_adapter_isolated_solve_success",
        "test_capability_adapter_pipeline_enabled_by_env_but_mutation_blocked",
        "test_capability_adapter_shadow_only_missing_evidence",
        "test_capability_adapter_shadow_only_with_evidence",
    ),
}
