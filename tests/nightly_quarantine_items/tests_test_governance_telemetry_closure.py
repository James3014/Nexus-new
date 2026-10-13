"""Nightly quarantine entry: tests/test_governance_telemetry_closure.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/test_governance_telemetry_closure.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "capability-phase e2e expectations (plan membership, invoked/gate_passed/wall_time) drifted from the current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": ("test_evidence_replay_artifact_generation",),
}
