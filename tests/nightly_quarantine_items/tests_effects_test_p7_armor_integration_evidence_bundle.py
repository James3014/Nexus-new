"""Nightly quarantine entry: tests/effects/test_p7_armor_integration_evidence_bundle.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/effects/test_p7_armor_integration_evidence_bundle.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "capability-phase e2e expectations (plan membership, invoked/gate_passed/wall_time) drifted from the current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": ("test_safety_assertions_all_safe",),
}
