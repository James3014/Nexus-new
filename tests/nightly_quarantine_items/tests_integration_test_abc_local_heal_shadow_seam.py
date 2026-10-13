"""Nightly quarantine entry: tests/integration/test_abc_local_heal_shadow_seam.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/integration/test_abc_local_heal_shadow_seam.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_abc_local_heal_advisory_seam",
        "test_abc_local_heal_candidate_seam",
        "test_abc_local_heal_fail_closed_seam",
        "test_abc_local_heal_shadow_seam",
    ),
}
