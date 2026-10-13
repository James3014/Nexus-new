"""Nightly quarantine entry: tests/integration/test_e2e_regression.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_e2e_regression.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": ("TestE2EHybridGovernance::test_e2e_hallucination_handled",),
}
