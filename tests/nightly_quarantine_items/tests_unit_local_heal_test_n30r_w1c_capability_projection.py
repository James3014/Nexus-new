"""Nightly quarantine entry: tests/unit/local_heal/test_n30r_w1c_capability_projection.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_n30r_w1c_capability_projection.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_classify_single_control_plane",
        "test_control_plane_caps_not_in_executor_selected",
        "test_projection_classifies_control_plane_capabilities",
    ),
}
