"""Nightly quarantine entry: tests/unit/test_patch_synthesis_phase.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/unit/test_patch_synthesis_phase.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "legacy local_heal/capability routing expectations predate the ASSISTED_CANONICAL topology and current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_patch_synthesis_phase_applies_valid_search_replace",
        "test_patch_synthesis_phase_rejects_duplicate_top_level_redefinition",
    ),
}
