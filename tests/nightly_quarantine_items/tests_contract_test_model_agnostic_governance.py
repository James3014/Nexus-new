"""Nightly quarantine entry: tests/contract/test_model_agnostic_governance.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/contract/test_model_agnostic_governance.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "capability-phase e2e expectations (plan membership, invoked/gate_passed/wall_time) drifted from the current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": ("TestModelAgnosticGovernance::test_hallucination_protection_is_constant",),
}
