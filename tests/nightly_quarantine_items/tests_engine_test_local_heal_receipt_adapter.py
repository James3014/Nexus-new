"""Nightly quarantine entry: tests/engine/test_local_heal_receipt_adapter.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/engine/test_local_heal_receipt_adapter.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_local_heal_receipt_adapter_hybrid_route_blocked",
        "test_local_heal_receipt_adapter_hybrid_route_dict_success",
    ),
}
