"""Nightly quarantine entry: tests/unit/local_heal/test_p3_cloud_local_assist_shadow.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_p3_cloud_local_assist_shadow.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_p3_shadow_flag_off_preserves_existing_topology",
        "test_p3_shadow_planner_injects_signal_fields",
    ),
}
