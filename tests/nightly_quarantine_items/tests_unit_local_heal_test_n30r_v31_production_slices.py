"""Nightly quarantine entry: tests/unit/local_heal/test_n30r_v31_production_slices.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/local_heal/test_n30r_v31_production_slices.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_slice_a_lite_success",
        "test_slice_b_lite_to_standard_recovery",
        "test_slice_c_full_profile_resolved",
    ),
}
