"""Nightly quarantine entry: tests/integration/test_adapter_hardening.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_adapter_hardening.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": ("TestAdapterFailClosed::test_consistency_drift_detection_mock",),
}
