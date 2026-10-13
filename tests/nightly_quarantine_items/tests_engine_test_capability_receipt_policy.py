"""Nightly quarantine entry: tests/engine/test_capability_receipt_policy.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/engine/test_capability_receipt_policy.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "capability-phase e2e expectations (plan membership, invoked/gate_passed/wall_time) drifted from the current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": ("test_receipt_backed_capabilities_match_adapter_registry_after_alias_normalization",),
}
